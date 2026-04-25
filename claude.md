# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概述

國立花蓮高商「教師員額控管」網頁系統。把學校原本一張寬表（`data/teacher.xlsx`）換成可瀏覽、可即時改算、可多年比較的 Web 應用。教務主任可改人數/節數/備註並自動回算員額差。

部署：Render（`https://hlbhteacher-1.onrender.com`），repo `Laisurjan/hlbhteacher`。

## 常用指令

```bash
# 本機啟動（必須先設 GOOGLE_CLIENT_ID 才能登入）
set GOOGLE_CLIENT_ID=585142859090-...apps.googleusercontent.com   # cmd
$env:GOOGLE_CLIENT_ID="..."                                        # PowerShell
python app.py
# http://localhost:5000

# 從 teacher.xlsx 重建 data/school_data.json
python utils/excel_parser.py

# 驗證套件
python scripts/verify_against_excel.py     # 算出來的數字必須完全等於 Excel data_only 值
python scripts/verify_auth.py              # Google 登入 + 角色權限（未登入/viewer/admin）
python scripts/verify_phase_2_2_a1.py      # cell 編輯 + 建新學年 API
python scripts/verify_phase_2_2_a2.py      # 進修部 cell + 日校科目 CRUD + class_count 係數
python scripts/verify_schedule.py          # schedule recompute 純函數
```

## 架構重點

### 資料是單一檔，不是多檔

**`data/school_data.json` 是這個系統的單一資料來源**。`courses.json`、`teachers.json` 是 Phase 1 舊檔，已不再被讀寫（API 改回 410 Gone），保留只是備份。

`school_data.json` 頂層結構：
- `domains` — 12 個領域的職務節點規則（C/G 公式字串、職務節數對應）
- `years.<year>.<domain_id>` — 每學年每領域的 positions（W..AG）+ substitute_count（AK）+ remark + required_day/evening
- `schedule.<year>.day` — 日校課程節數表（domain → subject → cells[col] + weighted_up/down + sum_up/down）
- `schedule.<year>.evening` — 進修部課程節數表（section → subject → cells + subtotal_J/total_K）
- `excel_raw_snapshot` — 從 Excel `data_only` 抽出的計算值，作為 verify 基準

要新增欄位前先想清楚會被哪幾隻 verify_*.py 卡到。

### 三層 roll-up

`utils/schedule_eval.py` 實作 cell 編輯的重算引擎：

1. **cell → subject**: `weighted_up = Σ cells[col] × coef[col] + const`（`compute_subject_weighted`）
2. **subject → domain**: `sum_up = Σ subjects.weighted_up + range.tail`（`compute_domain_sum`）
3. **domain → required_day**: 套用 Excel D 欄公式（保留在 `domains[].required_day_formula`）

`apply_cell_edit()` 是入口：只接 `(year, domain_id, row, col, value)`，內部跑完三層並寫回 `school_data.json`。前端只負責呼叫，不要在前端複算。

### 員額計算（`utils/calculator.py`）

`calc_summary()` 把 `years[year][domain]` 的 positions/substitute 套進 Excel C/G 公式（保留為字串），算出每領域兩種「基本節數」與「員額差」。公式裡 `AH5/AI5/AK5` 這類儲存格參考會先被 `_strip_row` 拔掉行號再代值，所以同一條公式可重複套用到任何學年。

### 認證（`utils/auth.py`）

Google OAuth + email 角色（**沒有密碼**，舊的 `admin_password_sha256` 已移除）：

- `ADMIN_EMAILS` 三個寫死在 `utils/auth.py`：`academy@`、`aca_sec@`、`walala@hlbh.hlc.edu.tw` → `admin`
- 其他 `@hlbh.hlc.edu.tw` → `viewer`
- 其他一律 None（連看都不能看）
- decorator：`@require_viewer`（網頁/讀 API）、`@require_admin`（寫 API）
- `_wants_json()` 判斷 `request.path.startswith('/api/')` → 沒登入回 401 JSON；否則 302 redirect 到 `/login`

**前端 UI 不要寫「誰能編輯」**（見 `~/.claude/.../feedback_admin_visibility.md`）。

### Render 持久化（`utils/github_sync.py`）

Render 免費方案 filesystem 重啟會清空。解法是每次 admin 寫入 `school_data.json`，背景 thread debounce 5 秒後用 GitHub Contents API commit + push 回 repo；下次 Render 重啟時開機先 pull 一次。

關鍵環境變數：`GITHUB_SYNC_ENABLED=1`、`GITHUB_TOKEN`、`GITHUB_REPO`、`GITHUB_BRANCH`、`GITHUB_SYNC_PATH`。本機開發預設關閉，不會誤推。

未來要把使用者 email 寫進 commit message：改 `save_json_file` 那邊的 `github_sync.schedule_push(filepath)` → `schedule_push(filepath, message=f'{user_email} 更新員額資料')` 一行即可。

### 路由

| 網頁路由 | 用途 | 對應模板 |
|---|---|---|
| `/` | 首頁節數總覽 | `index.html` |
| `/courses` | 員額編制（職務人數/代理/備註編輯） | `courses.html` |
| `/schedule` | 課程節數表（日校/進修部 cell 編輯） | `schedule.html` |
| `/compare` | 多年度比較 | `compare.html` |
| `/login` | Google 登入頁 | `login.html` |

主要 API（寫 API 都是 admin only）：
- 讀：`GET /api/summary`、`/api/schedule/<year>`、`/api/year_positions`、`/api/settings`、`/api/me`
- 寫：`PUT /api/year/<year>/domain/<id>`、`PATCH /api/domain_remark/<id>`、`PUT /api/schedule/<year>/<domain>/cell`、`PUT /api/schedule/<year>/evening/<section>/cell`、`POST/PATCH/DELETE /api/schedule/<year>/<domain>/subject[/<row>]`、`PATCH /api/schedule/<year>/class_count/<col>`、`POST /api/year/<year>`
- 已 410 Gone：`/api/teachers`、`/api/courses`、`/api/domain/<id>`（舊版，刻意保留路由回 410 提示新端點）

### 領域 ID 對映

| ID | 名稱 |
|---|---|
| `chinese_social` | 國文/社會 |
| `english` | 英文 |
| `math` | 數學 |
| `science` | 自然 |
| `accounting` | 會計 |
| `business` | 商經 |
| `data_processing` | 資處 |
| `multimedia` | 多媒 |
| `arts` | 美術 |
| `pe` | 體育 |
| `health_career` | 健康/生涯 |
| `defense` | 國防 |

## 編碼原則

對象是程式設計初學者（Lai 老師），優先簡單清楚而非優雅。

1. **KISS / DRY / YAGNI**：if-else 勝過三元；重複 3 次以上才抽函數；只做當前需要
2. 函數命名 `動詞_名詞`、變數命名描述內容
3. **註解一律中文**，但只寫 WHY，不寫 WHAT
4. JS 用 `function` 宣告而非箭頭函數，避免複雜鏈式呼叫

## 有事優先發包 Codex

實作量大的工作（重寫模板、重構 API、跨檔修改）優先用 `codex:codex-rescue` agent，Claude 負責出計畫 + 審 diff + 跑 verify。詳見 `~/.claude/.../feedback_codex_delegation.md`。
