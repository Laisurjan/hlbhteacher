# -*- coding: utf-8 -*-
"""
教師員額控管網頁系統 - Flask 主程式

這是系統的核心程式，負責：
1. 處理網頁請求（路由）
2. 讀取和儲存 JSON 資料
3. 提供 API 給前端使用
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import json
import os
from datetime import datetime

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


@app.route('/compare')
def compare():
    """年度比較頁面

    比較不同學年度的課程差異
    """
    settings = load_json_file(SETTINGS_FILE)
    return render_template('compare.html',
                         settings=settings,
                         is_admin=is_admin())


# ============================================================
# API 路由（給前端 JavaScript 使用）
# ============================================================

@app.route('/api/login', methods=['POST'])
def api_login():
    """登入 API

    驗證密碼，成功則設定 session
    """
    data = request.get_json()
    password = data.get('password', '')

    settings = load_json_file(SETTINGS_FILE)
    correct_password = settings.get('admin_password', 'admin123')

    if password == correct_password:
        session['is_admin'] = True
        return jsonify({'success': True, 'message': '登入成功'})
    else:
        return jsonify({'success': False, 'message': '密碼錯誤'})


@app.route('/api/logout', methods=['POST'])
def api_logout():
    """登出 API

    清除 session 中的管理員狀態
    """
    session.pop('is_admin', None)
    return jsonify({'success': True, 'message': '已登出'})


@app.route('/api/teachers', methods=['GET'])
def api_get_teachers():
    """取得教師資料 API"""
    teachers_data = load_json_file(TEACHERS_FILE)
    return jsonify(teachers_data)


@app.route('/api/teachers', methods=['POST'])
def api_update_teachers():
    """更新教師資料 API（需要管理員權限）"""
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理員權限'}), 403

    data = request.get_json()
    data['last_updated'] = datetime.now().strftime('%Y-%m-%d')

    if save_json_file(TEACHERS_FILE, data):
        return jsonify({'success': True, 'message': '儲存成功'})
    else:
        return jsonify({'success': False, 'message': '儲存失敗'}), 500


@app.route('/api/courses', methods=['GET'])
def api_get_courses():
    """取得課程資料 API"""
    courses_data = load_json_file(COURSES_FILE)
    return jsonify(courses_data)


@app.route('/api/courses', methods=['POST'])
def api_update_courses():
    """更新課程資料 API（需要管理員權限）"""
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理員權限'}), 403

    data = request.get_json()
    data['last_updated'] = datetime.now().strftime('%Y-%m-%d')

    if save_json_file(COURSES_FILE, data):
        return jsonify({'success': True, 'message': '儲存成功'})
    else:
        return jsonify({'success': False, 'message': '儲存失敗'}), 500


@app.route('/api/domain/<domain_id>', methods=['PUT'])
def api_update_domain(domain_id):
    """更新單一領域資料 API

    Args:
        domain_id: 領域的識別碼（如 'chinese_social'）
    """
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理員權限'}), 403

    data = request.get_json()
    teachers_data = load_json_file(TEACHERS_FILE)

    # 找到對應的領域並更新
    for domain in teachers_data.get('domains', []):
        if domain.get('id') == domain_id:
            # 更新領域資料（如果有提供的話）
            if 'total_base_hours' in data:
                domain['total_base_hours'] = data['total_base_hours']
            if 'required_hours' in data:
                domain['required_hours'] = data['required_hours']
            if 'note' in data:
                domain['note'] = data['note']

            # 更新正式教師（直接替換整個列表，支援新增/刪除）
            if 'formal_teachers' in data:
                domain['formal_teachers'] = data['formal_teachers']
                # 重新計算正式教師數和進修部教師數
                domain['formal_count'] = len(data['formal_teachers'])
                domain['evening_formal_count'] = sum(
                    1 for t in data['formal_teachers'] if t.get('is_evening', False)
                )
                # 重新計算基本節數
                domain['total_base_hours'] = sum(
                    t.get('base_hours', 0) for t in data['formal_teachers']
                )

            # 更新代理教師（直接替換整個列表，支援新增/刪除/啟用停用）
            if 'substitute_teachers' in data:
                domain['substitute_teachers'] = data['substitute_teachers']
                domain['substitute_count'] = len(data['substitute_teachers'])
            break

    teachers_data['last_updated'] = datetime.now().strftime('%Y-%m-%d')

    if save_json_file(TEACHERS_FILE, teachers_data):
        return jsonify({'success': True, 'message': '更新成功'})
    else:
        return jsonify({'success': False, 'message': '更新失敗'}), 500


@app.route('/api/settings', methods=['GET'])
def api_get_settings():
    """取得系統設定 API"""
    settings = load_json_file(SETTINGS_FILE)
    # 不要回傳密碼給前端
    settings_safe = {k: v for k, v in settings.items() if k != 'admin_password'}
    return jsonify(settings_safe)


@app.route('/api/summary', methods=['GET'])
def api_get_summary():
    """取得節數總覽摘要 API

    計算各領域的節數差異和整體統計
    """
    teachers_data = load_json_file(TEACHERS_FILE)

    summary = {
        'school_year': teachers_data.get('school_year', 115),
        'domains': [],
        'total_base': 0,
        'total_required': 0,
        'total_difference': 0
    }

    for domain in teachers_data.get('domains', []):
        base = domain.get('total_base_hours', 0)
        required = domain.get('required_hours', 0)
        difference = required - base
        teacher_count = len(domain.get('teachers', []))

        # 計算平均超時（如果需求大於基本節數）
        avg_overtime = 0
        if difference > 0 and teacher_count > 0:
            avg_overtime = round(difference / teacher_count, 2)

        domain_summary = {
            'id': domain.get('id', ''),
            'name': domain.get('name', ''),
            'base_hours': base,
            'required_hours': required,
            'difference': difference,
            'teacher_count': teacher_count,
            'avg_overtime': avg_overtime,
            'status': 'shortage' if difference > 0 else ('surplus' if difference < 0 else 'balanced')
        }

        summary['domains'].append(domain_summary)
        summary['total_base'] += base
        summary['total_required'] += required

    summary['total_difference'] = summary['total_required'] - summary['total_base']

    return jsonify(summary)


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
