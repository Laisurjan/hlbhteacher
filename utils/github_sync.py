# -*- coding: utf-8 -*-
"""GitHub 自動同步模組

功能：每次 data/school_data.json 被寫入，在背景把內容 commit + push 回 GitHub。
- 用 GitHub Contents API（不需要 git CLI、不需要 ssh key）
- Debounce：5 秒內多次儲存只會產生一次 commit，避免連點產生大量歷史
- 啟動時會先拉 GitHub 上最新版覆蓋本地（Render 重啟時自動回復資料）

環境變數設定（Render 環境變數頁 or 本機 .env）：
    GITHUB_SYNC_ENABLED=1              # 預設關；設 1 才啟用
    GITHUB_TOKEN=ghp_xxx...            # Personal Access Token（repo 權限）
    GITHUB_REPO=Laisurjan/hlbhteacher  # owner/repo
    GITHUB_BRANCH=main                 # 目標分支
    GITHUB_SYNC_PATH=data/school_data.json  # 要同步的檔（單檔）
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
from typing import Optional

import urllib.request
import urllib.error


# ============================================================
# 設定（從環境變數讀）
# ============================================================

def _env(name, default=''):
    return os.environ.get(name, default).strip()


SYNC_ENABLED = _env('GITHUB_SYNC_ENABLED', '0') == '1'
TOKEN        = _env('GITHUB_TOKEN')
REPO         = _env('GITHUB_REPO', 'Laisurjan/hlbhteacher')
BRANCH       = _env('GITHUB_BRANCH', 'main')
SYNC_PATH    = _env('GITHUB_SYNC_PATH', 'data/school_data.json')
DEBOUNCE_SEC = float(_env('GITHUB_SYNC_DEBOUNCE', '5'))


# ============================================================
# 內部狀態
# ============================================================

_lock = threading.Lock()
_timer: Optional[threading.Timer] = None
_pending_message = '自動儲存：教師員額資料更新'
_last_sha_cache: Optional[str] = None


def is_enabled():
    """回傳 True 表示 sync 目前可用（env 齊全且開關打開）"""
    return SYNC_ENABLED and bool(TOKEN) and bool(REPO)


# ============================================================
# GitHub API 呼叫
# ============================================================

def _gh_request(method, url, body=None):
    """呼叫 GitHub API，回 (status, json_dict)"""
    headers = {
        'Authorization': f'Bearer {TOKEN}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'teacher-quota-system',
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = resp.read().decode('utf-8')
            return resp.status, (json.loads(payload) if payload else {})
    except urllib.error.HTTPError as e:
        payload = e.read().decode('utf-8', errors='replace')
        try:
            js = json.loads(payload)
        except Exception:
            js = {'message': payload}
        return e.code, js
    except Exception as e:
        return 0, {'message': str(e)}


def _get_remote_sha(path):
    """查 GitHub 上某檔案目前的 sha（PUT 時必需）。找不到回 None。"""
    url = f'https://api.github.com/repos/{REPO}/contents/{path}?ref={BRANCH}'
    status, payload = _gh_request('GET', url)
    if status == 200:
        return payload.get('sha')
    return None


def _put_contents(path, content_bytes, sha, message):
    """用 Contents API 覆寫一個檔案"""
    url = f'https://api.github.com/repos/{REPO}/contents/{path}'
    body = {
        'message': message,
        'content': base64.b64encode(content_bytes).decode('ascii'),
        'branch': BRANCH,
    }
    if sha:
        body['sha'] = sha
    return _gh_request('PUT', url, body)


def _fetch_remote_raw(path):
    """抓遠端檔案內容（bytes）。找不到回 None。"""
    url = f'https://api.github.com/repos/{REPO}/contents/{path}?ref={BRANCH}'
    status, payload = _gh_request('GET', url)
    if status != 200:
        return None
    encoded = (payload.get('content') or '').replace('\n', '')
    if not encoded:
        return None
    try:
        return base64.b64decode(encoded)
    except Exception:
        return None


# ============================================================
# 對外：啟動時同步、修改後觸發
# ============================================================

def pull_latest_on_boot(local_path):
    """Render 容器啟動時呼叫一次：把 GitHub 上的最新版覆蓋本地。

    本機開發時通常不會設 GITHUB_SYNC_ENABLED=1，所以不會跑到這裡。
    若 GitHub 上沒有這檔（第一次），不動本地。
    """
    if not is_enabled():
        return False
    remote = _fetch_remote_raw(SYNC_PATH)
    if remote is None:
        print(f'[github_sync] 啟動同步：遠端 {SYNC_PATH} 不存在或抓取失敗，保留本地版本')
        return False
    try:
        with open(local_path, 'wb') as f:
            f.write(remote)
        print(f'[github_sync] 啟動同步：從 GitHub 拉到 {local_path}（{len(remote)} bytes）')
        return True
    except Exception as e:
        print(f'[github_sync] 啟動同步：寫入本地失敗 {e}')
        return False


def schedule_push(local_path, message=None):
    """觸發一次（debounced）push：5 秒內多次呼叫只會 commit 一次。"""
    global _timer, _pending_message
    if not is_enabled():
        return
    with _lock:
        if message:
            _pending_message = message
        # 取消之前的 timer
        if _timer is not None:
            try:
                _timer.cancel()
            except Exception:
                pass
        _timer = threading.Timer(DEBOUNCE_SEC, _flush, args=(local_path,))
        _timer.daemon = True
        _timer.start()


def _flush(local_path):
    """實際執行 push（在背景 thread 跑）"""
    global _timer, _last_sha_cache
    try:
        with open(local_path, 'rb') as f:
            content = f.read()
    except Exception as e:
        print(f'[github_sync] 讀本地失敗 {e}')
        return
    # 先拿最新 sha（避免被其他人改過）
    sha = _get_remote_sha(SYNC_PATH)
    status, payload = _put_contents(SYNC_PATH, content, sha, _pending_message)
    if status in (200, 201):
        new_sha = (payload.get('content') or {}).get('sha')
        _last_sha_cache = new_sha
        commit_sha = (payload.get('commit') or {}).get('sha', '')
        print(f'[github_sync] 推送成功：{commit_sha[:7]} {_pending_message}')
    elif status == 409:
        # Conflict：再抓一次 sha 重試一次
        time.sleep(0.5)
        sha = _get_remote_sha(SYNC_PATH)
        status2, payload2 = _put_contents(SYNC_PATH, content, sha, _pending_message)
        if status2 in (200, 201):
            print(f'[github_sync] 推送成功（重試）')
        else:
            print(f'[github_sync] 推送失敗（重試仍衝突）：{status2} {payload2.get("message")}')
    else:
        print(f'[github_sync] 推送失敗：{status} {payload.get("message")}')


def flush_now(local_path):
    """立刻推送（不走 debounce）。測試或關機前可呼叫。"""
    if not is_enabled():
        return
    with _lock:
        if _timer is not None:
            try:
                _timer.cancel()
            except Exception:
                pass
    _flush(local_path)
