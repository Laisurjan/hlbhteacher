# -*- coding: utf-8 -*-
"""
教師員額控管網頁系統 - Flask 主程式

這是系統的核心程式，負責：
1. 處理網頁請求（路由）
2. 讀取和儲存 JSON 資料
3. 提供 API 給前端使用
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import copy
import hashlib
import json
import os
import re
from datetime import datetime

from utils.calculator import calc_summary
from utils.schedule_eval import apply_cell_edit
from utils import github_sync

# 建立 Flask 應用程式
app = Flask(__name__)
# 設定 session 密鑰（用於登入狀態）
app.secret_key = 'teacher_quota_system_secret_key_2024'

# ============================================================
# 資料檔案路徑設定
# ============================================================
DATA_DIR = 'data'
COURSES_FILE = os.path.join(DATA_DIR, 'courses.json')
TEACHERS_FILE = os.path.join(DATA_DIR, 'teachers.json')
SETTINGS_FILE = os.path.join(DATA_DIR, 'settings.json')
SCHOOL_DATA_FILE = os.path.join(DATA_DIR, 'school_data.json')


# ============================================================
# 輔助函數：讀取和儲存 JSON 檔案
# ============================================================

def load_json_file(filepath):
    """讀取 JSON 檔案

    Args:
        filepath: JSON 檔案的路徑
    Returns:
        讀取到的資料（字典或列表）
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # 如果檔案不存在，回傳空字典
        return {}
    except json.JSONDecodeError:
        # 如果 JSON 格式錯誤，回傳空字典
        return {}


def save_json_file(filepath, data):
    """儲存資料到 JSON 檔案

    Args:
        filepath: 要儲存的檔案路徑
        data: 要儲存的資料
    Returns:
        True 表示成功，False 表示失敗
    """
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            # indent=2 讓 JSON 格式更易讀
            # ensure_ascii=False 讓中文正常顯示
            json.dump(data, f, ensure_ascii=False, indent=2)
        # 成功寫入後，若此檔是要同步到 GitHub 的目標，觸發背景 push（debounced）
        if os.path.abspath(filepath) == os.path.abspath(SCHOOL_DATA_FILE):
            github_sync.schedule_push(filepath)
        return True
    except Exception as e:
        print(f"儲存檔案時發生錯誤：{e}")
        return False


def is_admin():
    """檢查目前使用者是否為管理員（教務主任）

    Returns:
        True 表示是管理員，False 表示不是
    """
    return session.get('is_admin', False)


# ============================================================
# 啟動時從 GitHub 拉最新資料（僅在 Render 等雲端環境啟用）
# 本機開發不會設 GITHUB_SYNC_ENABLED=1，所以 pull_latest_on_boot 會 no-op
# Flask debug 模式下 reloader 會 fork 兩次，用 WERKZEUG_RUN_MAIN 避免重複
# ============================================================
if github_sync.is_enabled() and os.environ.get('WERKZEUG_RUN_MAIN') != 'false':
    try:
        github_sync.pull_latest_on_boot(SCHOOL_DATA_FILE)
    except Exception as e:
        print(f'[github_sync] 啟動拉取發生例外：{e}')


# ============================================================
# 網頁路由（頁面）
# ============================================================

@app.route('/')
def index():
    """首頁 - 節數總覽

    顯示各領域的基本節數與需求節數對照表
    """
    teachers_data = load_json_file(TEACHERS_FILE)
    settings = load_json_file(SETTINGS_FILE)

    return render_template('index.html',
                         teachers=teachers_data,
                         settings=settings,
                         is_admin=is_admin())


@app.route('/courses')
def courses():
    """課程管理頁面

    顯示各科系的課程列表，管理員可以編輯
    """
    courses_data = load_json_file(COURSES_FILE)
    settings = load_json_file(SETTINGS_FILE)

    return render_template('courses.html',
                         courses=courses_data,
                         settings=settings,
                         is_admin=is_admin())


@app.route('/schedule')
def schedule_page():
    """課程節數編輯頁（xlsx-style grid editor）

    日校課程節數預估表的可編輯版本，admin 可以改每個 cell，
    變動自動重算 weighted/sum/required_day，寫回 school_data.json。
    """
    settings = load_json_file(SETTINGS_FILE)
    school_data = load_json_file(SCHOOL_DATA_FILE)
    available_years = school_data.get('available_years', []) if school_data else []
    default_year = school_data.get('default_year', '113') if school_data else '113'
    return render_template('schedule.html',
                           settings=settings,
                           available_years=available_years,
                           default_year=default_year,
                           is_admin=is_admin())


@app.route('/compare')
def compare():
    """年度比較頁面

    比較不同學年度的課程差異
    """
    settings = load_json_file(SETTINGS_FILE)
    school_data = load_json_file(SCHOOL_DATA_FILE)
    available_years = school_data.get('available_years', []) if school_data else []
    return render_template('compare.html',
                         settings=settings,
                         available_years=available_years,
                         is_admin=is_admin())


# ============================================================
# API 路由（給前端 JavaScript 使用）
# ============================================================

@app.route('/api/login', methods=['POST'])
def api_login():
    """登入 API

    驗證密碼，成功則設定 session
    """
    data = request.get_json() or {}
    password = data.get('password', '')

    settings = load_json_file(SETTINGS_FILE)
    stored_hash = settings.get('admin_password_sha256', '')
    attempt_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()

    if stored_hash and attempt_hash == stored_hash:
        session['is_admin'] = True
        return jsonify({'success': True, 'message': '登入成功'})
    return jsonify({'success': False, 'message': '密碼錯誤'})


@app.route('/api/logout', methods=['POST'])
def api_logout():
    """登出 API

    清除 session 中的管理員狀態
    """
    session.pop('is_admin', None)
    return jsonify({'success': True, 'message': '已登出'})


_REMARK_FIELDS = (
    'name_list',
    'substitute_note',
    'remark_person',
    'remark_event',
    'future_note',
)

_LEGACY_MSG = {
    'success': False,
    'message': '此 API 已停用；請改用 /api/summary、/api/domain_remark/<id>、/api/year/<year>/domain/<id>'
}


@app.route('/api/teachers', methods=['GET', 'POST'])
def api_teachers_gone():
    return jsonify(_LEGACY_MSG), 410


@app.route('/api/courses', methods=['GET', 'POST'])
def api_courses_gone():
    return jsonify(_LEGACY_MSG), 410


@app.route('/api/domain/<domain_id>', methods=['PUT'])
def api_domain_gone(domain_id):
    return jsonify(_LEGACY_MSG), 410


@app.route('/api/domain_remark/<domain_id>', methods=['PATCH'])
def api_update_domain_remark(domain_id):
    """更新單一領域的 5 個備註欄位（需管理員權限）。"""
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理員權限'}), 403

    payload = request.get_json() or {}
    school_data = load_json_file(SCHOOL_DATA_FILE)
    if not school_data:
        return jsonify({'success': False, 'message': 'school_data.json 不存在'}), 500

    for domain in school_data.get('domains', []):
        if domain.get('id') == domain_id:
            for field in _REMARK_FIELDS:
                if field in payload:
                    value = payload[field]
                    domain[field] = '' if value is None else str(value)
            school_data['last_updated'] = datetime.now().strftime('%Y-%m-%d')
            if save_json_file(SCHOOL_DATA_FILE, school_data):
                return jsonify({'success': True, 'message': '備註已更新'})
            return jsonify({'success': False, 'message': '儲存失敗'}), 500

    return jsonify({'success': False, 'message': f'找不到領域 {domain_id}'}), 404


@app.route('/api/year_positions', methods=['GET'])
def api_get_year_positions():
    """回傳指定學年度每個領域的職務人數與代理人數（給員額編制頁用）。"""
    school_data = load_json_file(SCHOOL_DATA_FILE)
    if not school_data:
        return jsonify({'error': 'school_data.json 不存在'}), 500

    year = request.args.get('year') or school_data.get('default_year', '113')
    years = school_data.get('years', {})
    if year not in years:
        return jsonify({
            'error': f'未知學年度 {year}',
            'available_years': school_data.get('available_years', []),
        }), 400

    positions = {}
    substitutes = {}
    for dom_id, state in years[year].items():
        positions[dom_id]   = dict(state.get('positions', {}))
        substitutes[dom_id] = state.get('substitute_count', 0)

    return jsonify({
        'year': year,
        'positions': positions,
        'substitute_count': substitutes,
    })


@app.route('/api/year/<year>/domain/<domain_id>', methods=['PUT'])
def api_update_year_domain(year, domain_id):
    """更新指定學年度某領域的職務人數與代理人數（需管理員權限）。"""
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理員權限'}), 403

    payload = request.get_json() or {}
    school_data = load_json_file(SCHOOL_DATA_FILE)
    if not school_data:
        return jsonify({'success': False, 'message': 'school_data.json 不存在'}), 500

    years = school_data.get('years', {})
    if year not in years:
        return jsonify({
            'success': False,
            'message': f'未知學年度 {year}',
            'available_years': school_data.get('available_years', []),
        }), 400

    state = years[year].get(domain_id)
    if state is None:
        return jsonify({'success': False, 'message': f'找不到領域 {domain_id}'}), 404

    allowed_keys = {spec['key'] for spec in school_data.get('position_columns', [])}

    positions_in = payload.get('positions')
    if isinstance(positions_in, dict):
        positions = state.get('positions', {})
        for key, value in positions_in.items():
            if key in allowed_keys:
                try:
                    positions[key] = max(0, int(value))
                except (TypeError, ValueError):
                    positions[key] = 0
        state['positions'] = positions

    if 'substitute_count' in payload:
        try:
            state['substitute_count'] = max(0, int(payload['substitute_count']))
        except (TypeError, ValueError):
            state['substitute_count'] = 0

    school_data['last_updated'] = datetime.now().strftime('%Y-%m-%d')
    if save_json_file(SCHOOL_DATA_FILE, school_data):
        return jsonify({'success': True, 'message': '已更新'})
    return jsonify({'success': False, 'message': '儲存失敗'}), 500


# ============================================================
# 課程節數 grid editor 相關 API
# ============================================================

# 用來解析 required_formula 的正規式
_DAY_REF_PATTERN = re.compile(r'日(\d+)[^!]*!\s*([A-Z]+)(\d+)')
_EVENING_TERM_PATTERN = re.compile(r'([+\-])\s*進\d+[^!]*!\s*[A-Z]+\d+')
_LEADING_EVENING_PATTERN = re.compile(r'^\s*進\d+[^!]*!\s*[A-Z]+\d+')
_SAFE_MATH_PATTERN = re.compile(r'^[\d+\-*/()\s]+$')
_YEAR_REF_PATTERN = re.compile(r'日\d+')


def _evaluate_day_part(formula, day_schedule):
    """把 required_formula 拆成日校部分並代入新的 sum 值重算。

    formula 範例：
      =日113課程節數預估表!AH5-9+進113課程節數一覽表!K4
      =9+進113課程節數一覽表!J73
      =日113課程節數預估表!AH104
    回傳新的日校部分數值（int）；若公式空或無法解析回 0。
    """
    if not formula:
        return 0
    s = formula.strip()
    if s.startswith('='):
        s = s[1:]
    # 先刪掉帶正負號的「+進... / -進...」項
    s = _EVENING_TERM_PATTERN.sub('', s)
    # 再處理開頭若本身就是「進...」的情況（沒有前導正負號）
    s = _LEADING_EVENING_PATTERN.sub('0', s)
    s = s.lstrip('+').strip()
    if not s:
        return 0

    layout = (day_schedule or {}).get('layout') or {}
    sum_up_col = layout.get('sum_up_col')
    sum_down_col = layout.get('sum_down_col')
    row_to_domain = {}
    for dom in (day_schedule or {}).get('domains', []):
        row = dom.get('sum_row')
        if row is not None:
            # health_career 會出現兩筆，用 list 記下，按「最接近的 sum_row」匹配
            row_to_domain.setdefault(int(row), dom)

    def _sub(match):
        col = match.group(2)
        row = int(match.group(3))
        dom = row_to_domain.get(row)
        if dom is None:
            return '0'
        if col == sum_up_col:
            return str(int((dom.get('sum_up') or {}).get('value') or 0))
        if col == sum_down_col:
            return str(int((dom.get('sum_down') or {}).get('value') or 0))
        return '0'

    s = _DAY_REF_PATTERN.sub(_sub, s)
    if not _SAFE_MATH_PATTERN.match(s):
        raise ValueError(f'required_formula 含不可 eval 的字元：{s!r}')
    try:
        result = eval(s, {'__builtins__': {}}, {})
    except Exception:
        return 0
    return int(result) if isinstance(result, (int, float)) else 0


_EVENING_REF_PATTERN = re.compile(r'進(\d+)[^!]*!\s*([A-Z]+)(\d+)')
_DAY_TERM_PATTERN = re.compile(r'([+\-])\s*日\d+[^!]*!\s*[A-Z]+\d+')
_LEADING_DAY_PATTERN = re.compile(r'^\s*日\d+[^!]*!\s*[A-Z]+\d+')


def _evaluate_evening_part(formula, evening_schedule):
    """把 required_formula 拆成進修部部分並代入 subtotal_J/total_K 重算。

    進修部公式 ref 例：
      進113課程節數一覽表!K4  → section 首列 total_K
      進113課程節數一覽表!J73 → 某列 subtotal_J（若 col=J）
    若 evening 資料缺值，無法找到對應格時回 0。
    """
    if not formula:
        return 0
    s = formula.strip()
    if s.startswith('='):
        s = s[1:]
    # 刪掉日校部分
    s = _DAY_TERM_PATTERN.sub('', s)
    s = _LEADING_DAY_PATTERN.sub('0', s)
    s = s.lstrip('+').strip()
    if not s:
        return 0

    # 建 row → subject 與 section-first-row → section 的對照
    row_to_subj = {}
    first_row_to_section = {}
    for sec in (evening_schedule or {}).get('sections', []):
        subjects = sec.get('subjects') or []
        if subjects:
            first_row_to_section[int(subjects[0].get('row', -1))] = sec
        for subj in subjects:
            r = subj.get('row')
            if r is not None:
                row_to_subj[int(r)] = subj

    def _sub(match):
        col = match.group(2)
        row = int(match.group(3))
        if col == 'J':
            subj = row_to_subj.get(row)
            if subj:
                return str(int(subj.get('subtotal_J') or 0))
            return '0'
        if col == 'K':
            sec = first_row_to_section.get(row)
            if sec:
                return str(int((sec.get('subjects') or [{}])[0].get('total_K') or 0))
            # 若不是某 section 起始列，還是嘗試回該 subject 的 total_K
            subj = row_to_subj.get(row)
            if subj and subj.get('total_K') is not None:
                return str(int(subj.get('total_K') or 0))
            return '0'
        # 非 J/K 欄，回 cells[col]
        subj = row_to_subj.get(row)
        if subj:
            v = (subj.get('cells') or {}).get(col)
            if isinstance(v, (int, float)):
                return str(int(v))
        return '0'

    s = _EVENING_REF_PATTERN.sub(_sub, s)
    if not _SAFE_MATH_PATTERN.match(s):
        raise ValueError(f'evening 公式無法 eval：{s!r}')
    try:
        result = eval(s, {'__builtins__': {}}, {})
    except Exception:
        return 0
    return int(result) if isinstance(result, (int, float)) else 0


def _recompute_evening_section(section):
    """重新計算 section 內每個 subject 的 subtotal_J、以及首列 total_K。"""
    subjects = section.get('subjects') or []
    section_total = 0
    for subj in subjects:
        cells = subj.get('cells') or {}
        sub_total = sum(int(v) for v in cells.values() if isinstance(v, (int, float)))
        subj['subtotal_J'] = sub_total
        section_total += sub_total
    # total_K 只掛在第一列，其他列保留 null
    for idx, subj in enumerate(subjects):
        if idx == 0:
            subj['total_K'] = section_total
        else:
            subj['total_K'] = None
    return section_total


def _find_domain_by_row(domains, row):
    """在 schedule.day.domains 裡找出 subjects 裡含 row 的 domain。"""
    for dom in domains or []:
        for subj in dom.get('subjects') or []:
            if int(subj.get('row', -1)) == int(row):
                return dom
    return None


def _update_domain_cell(domain, row, col, new_value, apply_result):
    """把 apply_cell_edit 回傳的新值寫回 domain（原地修改）。"""
    for subj in domain.get('subjects', []):
        if int(subj.get('row', -1)) == int(row):
            cells = subj.setdefault('cells', {})
            if new_value is None or new_value == '':
                cells.pop(col, None)
            else:
                cells[col] = int(new_value)
            if subj.get('weighted_up'):
                subj['weighted_up']['value'] = apply_result['weighted_up_new']
            if subj.get('weighted_down'):
                subj['weighted_down']['value'] = apply_result['weighted_down_new']
            break
    if domain.get('sum_up'):
        domain['sum_up']['value'] = apply_result['domain_sum_up_new']
    if domain.get('sum_down'):
        domain['sum_down']['value'] = apply_result['domain_sum_down_new']


def _recompute_required_for_year(school_data, year, recompute_day=True, recompute_evening=True):
    """年度內所有 domain 的 required_day/evening/total 依目前 schedule 值重算。"""
    schedule_year = (school_data.get('schedule') or {}).get(year) or {}
    day_schedule = schedule_year.get('day')
    evening_schedule = schedule_year.get('evening')
    year_state = (school_data.get('years') or {}).get(year, {})
    for domain_id, state in year_state.items():
        formula = state.get('required_formula')
        if not formula:
            continue
        if recompute_day and day_schedule is not None:
            try:
                state['required_day'] = int(_evaluate_day_part(formula, day_schedule))
            except Exception as exc:
                print(f"[required recompute day] {year}/{domain_id} 失敗：{exc}")
        if recompute_evening and evening_schedule is not None:
            try:
                state['required_evening'] = int(_evaluate_evening_part(formula, evening_schedule))
            except Exception as exc:
                print(f"[required recompute evening] {year}/{domain_id} 失敗：{exc}")
        new_total = int(state.get('required_day', 0) or 0) + int(state.get('required_evening', 0) or 0)
        state['required_total'] = new_total
        state['required_hours'] = new_total


def _make_empty_year_schedule(source_day, new_year):
    """複製 source day schedule 結構並把所有 cells/weighted/sum 值歸零。

    formulas / coef / range / tail 保留，讓之後 admin 填回 cells 時
    recompute 引擎能正常運作。
    """
    new_day = copy.deepcopy(source_day) if source_day else {}
    for dom in new_day.get('domains', []):
        for subj in dom.get('subjects', []):
            subj['cells'] = {}
            if subj.get('weighted_up'):
                subj['weighted_up']['value'] = 0
            if subj.get('weighted_down'):
                subj['weighted_down']['value'] = 0
        if dom.get('sum_up'):
            dom['sum_up']['value'] = 0
        if dom.get('sum_down'):
            dom['sum_down']['value'] = 0
    return new_day


def _make_empty_year_state(source_state, new_year):
    """複製 years[source] 結構，人數歸零、required 歸零、公式沿用（年度 prefix 換掉）。"""
    new_state = {}
    for domain_id, state in (source_state or {}).items():
        positions = {key: 0 for key in (state.get('positions') or {}).keys()}
        old_formula = state.get('required_formula')
        new_formula = _YEAR_REF_PATTERN.sub(f'日{new_year}', old_formula) if old_formula else None
        new_state[domain_id] = {
            'positions': positions,
            'substitute_count': 0,
            'substitute_evening_count': 0,
            'required_hours': 0,
            'required_day': 0,
            'required_evening': 0,
            'required_total': 0,
            'required_formula': new_formula,
        }
    return new_state


@app.route('/api/schedule/<year>', methods=['GET'])
def api_get_schedule(year):
    """取得指定學年度的課程節數資料（唯讀）。"""
    school_data = load_json_file(SCHOOL_DATA_FILE)
    if not school_data:
        return jsonify({'success': False, 'message': 'school_data.json 不存在'}), 500
    schedule = (school_data.get('schedule') or {}).get(year)
    if not schedule:
        return jsonify({
            'success': False,
            'message': f'未知學年度 {year}',
            'available_years': school_data.get('available_years', []),
        }), 404

    # 領域中文名對照（從 top-level domains meta 取）
    domain_names = {d['id']: d.get('name') for d in school_data.get('domains', [])}
    return jsonify({
        'success': True,
        'year': year,
        'available_years': school_data.get('available_years', []),
        'default_year': school_data.get('default_year'),
        'domain_names': domain_names,
        'schedule': schedule,
    })


@app.route('/api/schedule/<year>/<domain_id>/cell', methods=['PUT'])
def api_update_schedule_cell(year, domain_id):
    """更新某 subject 某 col 的節數值，並連動重算 weighted/sum/required。

    body: {"row": 5, "col": "F", "value": 3}
    value 為 None 或 "" 代表清空 cell。
    """
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理員權限'}), 403

    payload = request.get_json() or {}
    row = payload.get('row')
    col = payload.get('col')
    raw_value = payload.get('value')

    if row is None or not col:
        return jsonify({'success': False, 'message': 'row / col 必填'}), 400
    try:
        row = int(row)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'row 必須是整數'}), 400
    col = str(col).strip().upper()
    if not re.match(r'^[A-Z]+$', col):
        return jsonify({'success': False, 'message': f'col 格式錯誤：{col}'}), 400

    if raw_value in (None, ''):
        new_value = 0
        clear = True
    else:
        try:
            new_value = int(raw_value)
            clear = False
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'value 必須是整數'}), 400
        if new_value < 0:
            return jsonify({'success': False, 'message': 'value 不能為負數'}), 400

    school_data = load_json_file(SCHOOL_DATA_FILE)
    if not school_data:
        return jsonify({'success': False, 'message': 'school_data.json 不存在'}), 500

    day_schedule = (school_data.get('schedule') or {}).get(year, {}).get('day')
    if not day_schedule:
        return jsonify({'success': False, 'message': f'學年度 {year} 無 day schedule'}), 404

    # 1) 找 domain：先用 row，若對應 domain_id 不符再回頭比對
    target = _find_domain_by_row(day_schedule.get('domains', []), row)
    if target is None:
        return jsonify({'success': False, 'message': f'找不到 row {row} 對應的 domain'}), 404
    if target.get('domain_id') and target.get('domain_id') != domain_id:
        # row 有對應 domain，但和 URL 參數不符：以 row 為準（避免 health_career 兩段混淆）
        pass

    # 2) 試算新值
    try:
        result = apply_cell_edit(target, row, col, 0 if clear else new_value)
    except Exception as exc:
        return jsonify({'success': False, 'message': f'試算失敗：{exc}'}), 500

    # 3) 寫回 domain（更新 cells + weighted + sum）
    _update_domain_cell(
        target, row, col,
        None if clear else new_value,
        result,
    )

    # 4) 重算 years[year] 的 required_day/total
    _recompute_required_for_year(school_data, year)

    # 5) 存檔
    school_data['last_updated'] = datetime.now().strftime('%Y-%m-%d')
    if not save_json_file(SCHOOL_DATA_FILE, school_data):
        return jsonify({'success': False, 'message': '儲存失敗'}), 500

    updated = (school_data.get('years') or {}).get(year, {}).get(target.get('domain_id') or domain_id, {})
    return jsonify({
        'success':           True,
        'row':               row,
        'col':               col,
        'value':             None if clear else new_value,
        'domain_id':         target.get('domain_id') or domain_id,
        'weighted_up_new':   result['weighted_up_new'],
        'weighted_down_new': result['weighted_down_new'],
        'sum_up_new':        result['domain_sum_up_new'],
        'sum_down_new':      result['domain_sum_down_new'],
        'required_day_new':   updated.get('required_day'),
        'required_total_new': updated.get('required_total'),
    })


@app.route('/api/schedule/<year>/evening/<section_key>/cell', methods=['PUT'])
def api_update_evening_cell(year, section_key):
    """進修部 cell 編輯：body {row, col, value}。value 為 "" 代表清空。"""
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理員權限'}), 403

    payload = request.get_json() or {}
    try:
        row = int(payload.get('row'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'row 必須是整數'}), 400
    col = str(payload.get('col') or '').strip().upper()
    if not re.match(r'^[A-Z]+$', col):
        return jsonify({'success': False, 'message': f'col 格式錯誤：{col}'}), 400

    raw_value = payload.get('value')
    if raw_value in (None, ''):
        new_value = None
    else:
        try:
            new_value = int(raw_value)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'value 必須是整數'}), 400
        if new_value < 0:
            return jsonify({'success': False, 'message': 'value 不能為負數'}), 400

    school_data = load_json_file(SCHOOL_DATA_FILE)
    if not school_data:
        return jsonify({'success': False, 'message': 'school_data.json 不存在'}), 500

    evening = (school_data.get('schedule') or {}).get(year, {}).get('evening')
    if not evening:
        return jsonify({'success': False, 'message': f'學年度 {year} 無 evening schedule'}), 404

    section = next((s for s in evening.get('sections', []) if s.get('section_key') == section_key), None)
    if section is None:
        return jsonify({'success': False, 'message': f'找不到 section {section_key}'}), 404
    subj = next((s for s in section.get('subjects', []) if int(s.get('row', -1)) == row), None)
    if subj is None:
        return jsonify({'success': False, 'message': f'section {section_key} 無 row {row}'}), 404

    cells = subj.setdefault('cells', {})
    if new_value is None:
        cells.pop(col, None)
    else:
        cells[col] = new_value

    section_total = _recompute_evening_section(section)
    _recompute_required_for_year(school_data, year, recompute_day=False, recompute_evening=True)

    school_data['last_updated'] = datetime.now().strftime('%Y-%m-%d')
    if not save_json_file(SCHOOL_DATA_FILE, school_data):
        return jsonify({'success': False, 'message': '儲存失敗'}), 500

    # 回傳本 section 每個 subject 的 subtotal_J 與首列 total_K
    subtotals = {int(s['row']): s.get('subtotal_J') for s in section.get('subjects', [])}
    return jsonify({
        'success':        True,
        'section_key':    section_key,
        'row':            row,
        'col':            col,
        'value':          new_value,
        'subtotals_new':  subtotals,
        'total_K_new':    section_total,
    })


def _regenerate_weighted_formula(row, coef, const):
    """依 coef + const 重組 weighted_up/down 的 Excel 風格 formula 字串。"""
    terms = []
    for col in sorted(coef.keys(), key=lambda c: (len(c), c)):
        n = int(coef[col])
        if n == 0:
            continue
        ref = f'{col}{row}'
        terms.append(ref if n == 1 else f'{ref}*{n}')
    expr = '+'.join(terms) if terms else '0'
    c = int(const or 0)
    if c > 0:
        expr += f'+{c}'
    elif c < 0:
        expr += f'{c}'
    return '=' + expr


@app.route('/api/schedule/<year>/<domain_id>/subject/<int:row>', methods=['PATCH', 'DELETE'])
def api_modify_subject(year, domain_id, row):
    """PATCH body {name?} 更名；DELETE 刪除 subject 並從 sum range 移除。"""
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理員權限'}), 403

    school_data = load_json_file(SCHOOL_DATA_FILE)
    if not school_data:
        return jsonify({'success': False, 'message': 'school_data.json 不存在'}), 500

    day = (school_data.get('schedule') or {}).get(year, {}).get('day')
    if not day:
        return jsonify({'success': False, 'message': f'學年度 {year} 無 day schedule'}), 404

    target = _find_domain_by_row(day.get('domains', []), row)
    if target is None:
        return jsonify({'success': False, 'message': f'找不到 row {row}'}), 404

    if request.method == 'PATCH':
        payload = request.get_json() or {}
        if 'name' in payload:
            new_name = str(payload['name']).strip()
            if not new_name:
                return jsonify({'success': False, 'message': '科目名稱不可為空'}), 400
            subj = next((s for s in target['subjects'] if int(s.get('row', -1)) == row), None)
            if subj is None:
                return jsonify({'success': False, 'message': 'subject 不存在'}), 404
            subj['name'] = new_name

        school_data['last_updated'] = datetime.now().strftime('%Y-%m-%d')
        if not save_json_file(SCHOOL_DATA_FILE, school_data):
            return jsonify({'success': False, 'message': '儲存失敗'}), 500
        return jsonify({'success': True, 'row': row, 'name': subj['name']})

    # DELETE
    before = len(target.get('subjects', []))
    target['subjects'] = [s for s in target.get('subjects', []) if int(s.get('row', -1)) != row]
    if len(target['subjects']) == before:
        return jsonify({'success': False, 'message': f'row {row} 不存在'}), 404
    # 從 sum range.rows 中移除
    for which in ('sum_up', 'sum_down'):
        block = target.get(which) or {}
        rng = block.get('range') or {}
        if rng.get('rows'):
            rng['rows'] = [r for r in rng['rows'] if int(r) != row]
    # 重算 sum_up / sum_down value
    from utils.schedule_eval import compute_domain_sum
    if target.get('sum_up'):
        target['sum_up']['value'] = compute_domain_sum(target, 'up')
    if target.get('sum_down'):
        target['sum_down']['value'] = compute_domain_sum(target, 'down')
    _recompute_required_for_year(school_data, year, recompute_day=True, recompute_evening=False)

    school_data['last_updated'] = datetime.now().strftime('%Y-%m-%d')
    if not save_json_file(SCHOOL_DATA_FILE, school_data):
        return jsonify({'success': False, 'message': '儲存失敗'}), 500
    updated = (school_data.get('years') or {}).get(year, {}).get(target.get('domain_id') or domain_id, {})
    return jsonify({
        'success':          True,
        'deleted_row':      row,
        'sum_up_new':       (target.get('sum_up') or {}).get('value'),
        'sum_down_new':     (target.get('sum_down') or {}).get('value'),
        'required_day_new': updated.get('required_day'),
        'required_total_new': updated.get('required_total'),
    })


@app.route('/api/schedule/<year>/<domain_id>/subject', methods=['POST'])
def api_add_subject(year, domain_id):
    """新增 subject 至指定 domain。

    body: {"name": "新科目名", "coef_source_row": optional int}
    預設 coef 從 domain 第一個科目複製（保留班級數配置），const=0。
    新列號 = 全年度 day schedule 中最大 row + 1（保證不撞）。
    """
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理員權限'}), 403

    payload = request.get_json() or {}
    name = str(payload.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': '科目名稱必填'}), 400

    school_data = load_json_file(SCHOOL_DATA_FILE)
    if not school_data:
        return jsonify({'success': False, 'message': 'school_data.json 不存在'}), 500
    day = (school_data.get('schedule') or {}).get(year, {}).get('day')
    if not day:
        return jsonify({'success': False, 'message': f'學年度 {year} 無 day schedule'}), 404

    target = None
    for dom in day.get('domains', []):
        if dom.get('domain_id') == domain_id:
            target = dom
            break
    if target is None:
        return jsonify({'success': False, 'message': f'找不到 domain {domain_id}'}), 404

    # 找 coef 模板
    coef_source_row = payload.get('coef_source_row')
    template = None
    if coef_source_row is not None:
        template = next((s for s in target.get('subjects', []) if int(s.get('row', -1)) == int(coef_source_row)), None)
    if template is None and target.get('subjects'):
        template = target['subjects'][0]
    coef_up = dict((template.get('weighted_up') or {}).get('coef') or {}) if template else {}
    coef_down = dict((template.get('weighted_down') or {}).get('coef') or {}) if template else {}

    # 計算新 row：全 day schedule 所有 subject row 最大值 + 1
    all_rows = [0]
    for dom in day.get('domains', []):
        for s in dom.get('subjects', []):
            all_rows.append(int(s.get('row', 0)))
    new_row = max(all_rows) + 1

    new_subj = {
        'row': new_row,
        'name': name,
        'cells': {},
        'weighted_up': {
            'formula': _regenerate_weighted_formula(new_row, coef_up, 0),
            'coef':   coef_up,
            'const':  0,
            'value':  0,
            'raw_value': None,
        },
        'weighted_down': {
            'formula': _regenerate_weighted_formula(new_row, coef_down, 0),
            'coef':   coef_down,
            'const':  0,
            'value':  0,
            'raw_value': None,
        },
    }
    target.setdefault('subjects', []).append(new_subj)

    # 加入 sum range.rows（若存在）
    for which in ('sum_up', 'sum_down'):
        block = target.get(which) or {}
        rng = block.get('range') or {}
        if 'rows' in rng:
            rng['rows'] = list(rng['rows']) + [new_row]
        if 'end' in rng and rng.get('end') is not None:
            rng['end'] = max(int(rng['end']), new_row)

    school_data['last_updated'] = datetime.now().strftime('%Y-%m-%d')
    if not save_json_file(SCHOOL_DATA_FILE, school_data):
        return jsonify({'success': False, 'message': '儲存失敗'}), 500
    return jsonify({'success': True, 'row': new_row, 'name': name})


@app.route('/api/schedule/<year>/class_count/<col>', methods=['PATCH'])
def api_update_class_count(year, col):
    """調整某欄的班級數係數（隱藏倍數）。

    body: {"new_count": int}
    會掃 day schedule 所有 subject 的 weighted_up.coef[col] 與 weighted_down.coef[col]
    （若存在則更新），並重算 weighted / sum / required。
    """
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理員權限'}), 403

    col = str(col).strip().upper()
    if not re.match(r'^[A-Z]+$', col):
        return jsonify({'success': False, 'message': f'col 格式錯誤：{col}'}), 400

    payload = request.get_json() or {}
    try:
        new_count = int(payload.get('new_count'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'new_count 必須是整數'}), 400
    if new_count < 0:
        return jsonify({'success': False, 'message': 'new_count 不能為負'}), 400

    school_data = load_json_file(SCHOOL_DATA_FILE)
    if not school_data:
        return jsonify({'success': False, 'message': 'school_data.json 不存在'}), 500

    day = (school_data.get('schedule') or {}).get(year, {}).get('day')
    if not day:
        return jsonify({'success': False, 'message': f'學年度 {year} 無 day schedule'}), 404

    from utils.schedule_eval import compute_subject_weighted, compute_domain_sum

    touched = 0
    for dom in day.get('domains', []):
        for subj in dom.get('subjects', []):
            row = int(subj.get('row', 0))
            for which in ('weighted_up', 'weighted_down'):
                spec = subj.get(which) or {}
                coef = spec.get('coef') or {}
                if col in coef:
                    coef[col] = new_count
                    spec['coef'] = coef
                    spec['formula'] = _regenerate_weighted_formula(row, coef, spec.get('const') or 0)
                    spec['value'] = compute_subject_weighted(subj.get('cells') or {}, spec)
                    touched += 1
        if dom.get('sum_up'):
            dom['sum_up']['value'] = compute_domain_sum(dom, 'up')
        if dom.get('sum_down'):
            dom['sum_down']['value'] = compute_domain_sum(dom, 'down')

    _recompute_required_for_year(school_data, year, recompute_day=True, recompute_evening=False)

    school_data['last_updated'] = datetime.now().strftime('%Y-%m-%d')
    if not save_json_file(SCHOOL_DATA_FILE, school_data):
        return jsonify({'success': False, 'message': '儲存失敗'}), 500
    return jsonify({'success': True, 'col': col, 'new_count': new_count, 'touched_subjects': touched})


@app.route('/api/year/<year>', methods=['POST'])
def api_create_year(year):
    """建立新學年度：以既有年度的結構為模板，cells/人數/需求全部歸零。

    body: {"copy_structure_from": "114"}
    """
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理員權限'}), 403

    payload = request.get_json() or {}
    source_year = str(payload.get('copy_structure_from') or '').strip()
    year = str(year).strip()

    if not re.match(r'^\d{3}$', year):
        return jsonify({'success': False, 'message': f'年度代碼格式錯誤：{year}'}), 400

    school_data = load_json_file(SCHOOL_DATA_FILE)
    if not school_data:
        return jsonify({'success': False, 'message': 'school_data.json 不存在'}), 500

    available = school_data.get('available_years') or []
    if year in available:
        return jsonify({'success': False, 'message': f'學年度 {year} 已存在'}), 400
    if source_year and source_year not in available:
        return jsonify({
            'success': False,
            'message': f'來源學年度 {source_year} 不存在',
            'available_years': available,
        }), 400
    if not source_year:
        # 預設拿最新一年當模板
        source_year = available[-1] if available else None
    if not source_year:
        return jsonify({'success': False, 'message': '沒有可用的模板年度'}), 400

    # 1) 複製 schedule.day 並清空值（公式保留）
    source_day = (school_data.get('schedule') or {}).get(source_year, {}).get('day')
    empty_day = _make_empty_year_schedule(source_day, year)

    schedule = school_data.setdefault('schedule', {})
    schedule[year] = {'day': empty_day}

    # 2) 複製 years[source] 並清空
    source_state = (school_data.get('years') or {}).get(source_year, {})
    years = school_data.setdefault('years', {})
    years[year] = _make_empty_year_state(source_state, year)

    # 3) 加入 available_years 並保持排序
    available_sorted = sorted(set(available + [year]), key=lambda x: int(x))
    school_data['available_years'] = available_sorted

    school_data['last_updated'] = datetime.now().strftime('%Y-%m-%d')
    if not save_json_file(SCHOOL_DATA_FILE, school_data):
        return jsonify({'success': False, 'message': '儲存失敗'}), 500

    return jsonify({
        'success':         True,
        'year':            year,
        'source_year':     source_year,
        'available_years': school_data['available_years'],
    })


@app.route('/api/settings', methods=['GET'])
def api_get_settings():
    """取得系統設定 API"""
    settings = load_json_file(SETTINGS_FILE)
    # 不要回傳密碼/雜湊給前端
    _SECRET_KEYS = {'admin_password', 'admin_password_sha256'}
    settings_safe = {k: v for k, v in settings.items() if k not in _SECRET_KEYS}
    return jsonify(settings_safe)


_ALLOWED_MODES = {'strict', 'homeroom_all'}


def _parse_bool_flag(raw: str | None) -> bool:
    if raw is None:
        return False
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


@app.route('/api/summary', methods=['GET'])
def api_get_summary():
    """節數總覽（以 school_data.json 為來源，逐格復刻 Excel）。

    Query params:
      year        113/114（預設 default_year）
      mode        strict | homeroom_all（預設 strict）
      include_sub 0/1（預設 0）— True 時將代理計入每人超時節數分母
    """
    school_data = load_json_file(SCHOOL_DATA_FILE)
    if not school_data:
        return jsonify({'error': 'school_data.json 不存在，請先跑 python utils/excel_parser.py'}), 500

    year = request.args.get('year') or school_data.get('default_year', '113')
    if year not in school_data.get('years', {}):
        return jsonify({
            'error': f'未知學年度 {year}',
            'available_years': school_data.get('available_years', []),
        }), 400

    mode = request.args.get('mode', 'strict')
    if mode not in _ALLOWED_MODES:
        return jsonify({
            'error': f'未知 mode {mode}',
            'allowed_modes': sorted(_ALLOWED_MODES),
        }), 400
    include_sub = _parse_bool_flag(request.args.get('include_sub'))

    summary = calc_summary(school_data, year, mode=mode, include_substitute=include_sub)

    # 把 Excel 原值也放進來，供前端「顯示 Excel 對照」切換使用
    snapshot = school_data.get('excel_raw_snapshot', {})
    for row in summary['rows']:
        row['excel_raw'] = snapshot.get(row['domain_id'], {})

    return jsonify({
        'year': year,
        'mode': mode,
        'include_substitute': include_sub,
        'available_years': school_data.get('available_years', []),
        'default_year': school_data.get('default_year'),
        'rows': summary['rows'],
        'totals': summary['totals'],
        'position_columns': school_data.get('position_columns', []),
    })


# ============================================================
# 主程式入口
# ============================================================

if __name__ == '__main__':
    # 確保資料目錄存在
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    # 啟動開發伺服器
    # debug=True 讓修改程式後自動重新載入
    # host='0.0.0.0' 讓區域網路內的其他電腦也能連線
    print("=" * 50)
    print("教師員額控管系統啟動中...")
    print("請在瀏覽器開啟：http://localhost:5000")
    print("按 Ctrl+C 可停止伺服器")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)
