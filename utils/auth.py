# -*- coding: utf-8 -*-
"""Google OAuth 登入權限模組

職責：
1. 校驗 Google ID token 簽章與 email
2. 依 email 決定角色：admin / viewer / None（拒絕）
3. 提供 decorator：require_viewer（網頁）、require_admin（寫入 API）

角色對應：
- admin（可編輯）：academy@hlbh.hlc.edu.tw、aca_sec@hlbh.hlc.edu.tw、walala@hlbh.hlc.edu.tw
- viewer（可看）：其他 @hlbh.hlc.edu.tw 的 email
- None：非校內 email，不能看也不能改

環境變數：
    GOOGLE_CLIENT_ID  — Google Cloud Console 拿到的 OAuth Client ID
"""

from __future__ import annotations

import os
from functools import wraps

from flask import jsonify, redirect, request, session, url_for


# ============================================================
# 白名單與域名
# ============================================================

ADMIN_EMAILS = {
    'academy@hlbh.hlc.edu.tw',
    'aca_sec@hlbh.hlc.edu.tw',
    'walala@hlbh.hlc.edu.tw',
}

ALLOWED_DOMAIN = '@hlbh.hlc.edu.tw'


def role_for_email(email):
    """依 email 回角色：'admin' / 'viewer' / None"""
    if not email:
        return None
    email = email.strip().lower()
    if email in ADMIN_EMAILS:
        return 'admin'
    if email.endswith(ALLOWED_DOMAIN):
        return 'viewer'
    return None


# ============================================================
# Google ID token 驗證
# ============================================================

def verify_google_id_token(token_str):
    """驗證前端傳來的 Google ID token。

    成功回 (email, name)；失敗回 (None, None)。
    需要 google-auth 套件；若沒裝或沒設 GOOGLE_CLIENT_ID，回 (None, None)。
    """
    client_id = os.environ.get('GOOGLE_CLIENT_ID', '').strip()
    if not client_id:
        print('[auth] GOOGLE_CLIENT_ID 未設定，拒絕登入')
        return None, None
    if not token_str:
        return None, None
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests
    except ImportError:
        print('[auth] 缺 google-auth 套件：pip install google-auth')
        return None, None

    try:
        payload = google_id_token.verify_oauth2_token(
            token_str,
            google_requests.Request(),
            client_id,
        )
    except ValueError as e:
        print(f'[auth] token 驗證失敗：{e}')
        return None, None

    email = (payload.get('email') or '').strip().lower()
    email_verified = payload.get('email_verified')
    if not email or not email_verified:
        return None, None
    name = payload.get('name') or email.split('@')[0]
    return email, name


# ============================================================
# Session helpers
# ============================================================

def current_user():
    """回傳目前 session 裡的使用者，格式：{email, name, role} 或 None"""
    if not session.get('user_email'):
        return None
    return {
        'email': session.get('user_email'),
        'name':  session.get('user_name'),
        'role':  session.get('user_role'),
    }


def is_logged_in():
    return bool(session.get('user_email'))


def is_admin():
    return session.get('user_role') == 'admin'


def is_viewer():
    """viewer 以上（admin 也算 viewer）"""
    return session.get('user_role') in ('admin', 'viewer')


def login(email, name):
    """登入成功後呼叫：把角色寫進 session"""
    role = role_for_email(email)
    if role is None:
        return False
    session['user_email'] = email
    session['user_name'] = name or email.split('@')[0]
    session['user_role'] = role
    session.permanent = True
    return True


def logout():
    session.pop('user_email', None)
    session.pop('user_name', None)
    session.pop('user_role', None)


# ============================================================
# Decorators
# ============================================================

def _wants_json():
    """判斷請求是否期望 JSON（API endpoint 走 JSON 回應，網頁走 redirect）"""
    if request.path.startswith('/api/'):
        return True
    accept = request.headers.get('Accept', '')
    return 'application/json' in accept


def require_viewer(view_func):
    """網頁/讀 API：必須登入 + email 在 allow 範圍"""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not is_viewer():
            if _wants_json():
                return jsonify({'success': False, 'message': '需要登入（校內帳號）'}), 401
            return redirect(url_for('login_page', next=request.path))
        return view_func(*args, **kwargs)
    return wrapper


def require_admin(view_func):
    """寫入 API：必須是三個指定 email 之一"""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not is_admin():
            if _wants_json():
                return jsonify({'success': False, 'message': '需要管理員權限'}), 403
            return redirect(url_for('login_page', next=request.path))
        return view_func(*args, **kwargs)
    return wrapper
