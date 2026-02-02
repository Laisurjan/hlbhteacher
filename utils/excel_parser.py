# -*- coding: utf-8 -*-
"""
Excel 課程資料解析工具

從 teacher.xlsx 讀取課程資料並轉換為系統需要的 JSON 格式
"""

import pandas as pd
import json
import os


# 不需要顯示的課程名稱
EXCLUDED_COURSES = [
    '小計', '總節數', '團體活動', '彈性課程增廣', '彈性課程補強', '本土語',
    '小                        計'
]

# 課程名稱 → 領域 對照表（用於補強領域辨識）
COURSE_DOMAIN_MAP = {
    # 國文/社會 領域課程
    '國語文': '國文/社會',
    '現代詩文賞析': '國文/社會',
    '古典文學選讀': '國文/社會',
    '國文閱讀與寫作': '國文/社會',
    '跨領域趨勢閱讀': '國文/社會',
    '歷史': '國文/社會',
    '地理': '國文/社會',
    '公民與社會': '國文/社會',
    '法律與生活': '國文/社會',
    '文學與生活': '國文/社會',
    # 英文 領域課程
    '英語文': '英文',
    '英文': '英文',
    '生活英語會話': '英文',
    '基礎英文閱讀與寫作': '英文',
    '英語聽講練習': '英文',
    '英文文法': '英文',
    '英語口語訓練': '英文',
    '商業英文': '英文',
    '觀光英語': '英文',
    '英文閱讀': '英文',
    # 數學領域課程
    '數學': '數學',
    '數學演習': '數學',
    '數學應用': '數學',
    '商業數學': '數學',
    '趣味數學': '數學',
    # 自然領域課程
    '物理': '自然',
    '化學': '自然',
    '生物': '自然',
    '自然科學': '自然',
    # 體育領域
    '體育': '體育',
    '體  育': '體育',

    # 健康與生涯領域
    '健康與護理': '健康/生涯',
    '生涯規劃': '健康/生涯',
    '生命教育': '健康/生涯',

    # 美術領域（只有美術相關，不含設計群專業課程）
    '音樂': '美術',
    '美術': '美術',
    '藝術生活': '美術',

    # 全民國防
    '全民國防教育': '國防',
    # 跨領域選修課程
    '人工智慧': '資處',
    '說故事學行銷': '商經',
}


def parse_courses_from_excel(excel_path):
    """從 Excel 讀取課程資料

    Args:
        excel_path: Excel 檔案路徑
    Returns:
        課程資料字典
    """
    # 讀取第二個工作表（113課程節數預估表）
    df = pd.read_excel(excel_path, sheet_name=1, header=None)

    # 科系欄位對應（一年級上下、二年級上下、三年級上下）
    # 根據 Excel 實際結構：多媒(3,4)、資處(5,6)、會計(7,8)、商經(9,10)、應英(11,12) 為一年級
    # 二年級：多媒(13,14)、資處(15,16)、會計(17,18)、商經(19,20)、應英(21,22)
    # 三年級：資處(23,24)、會計(25,26)、商經(27,28)、應英(29,30)
    departments = {
        'multimedia': {
            'name': '多媒體設計科',
            'cols': {
                '1-1': 3, '1-2': 4,
                '2-1': 13, '2-2': 14
            }
        },
        'data_processing': {
            'name': '資處科',
            'cols': {
                '1-1': 5, '1-2': 6,
                '2-1': 15, '2-2': 16,
                '3-1': 23, '3-2': 24
            }
        },
        'accounting': {
            'name': '會計科',
            'cols': {
                '1-1': 7, '1-2': 8,
                '2-1': 17, '2-2': 18,
                '3-1': 25, '3-2': 26
            }
        },
        'business': {
            'name': '商經科',
            'cols': {
                '1-1': 9, '1-2': 10,
                '2-1': 19, '2-2': 20,
                '3-1': 27, '3-2': 28
            }
        },
        'applied_english': {
            'name': '應用英語科',
            'cols': {
                '1-1': 11, '1-2': 12,
                '2-1': 21, '2-2': 22,
                '3-1': 29, '3-2': 30
            }
        }
    }

    courses_data = {
        'school_year': 113,
        'last_updated': '',
        'departments': []
    }

    # 為每個科系建立課程列表
    for dept_id, dept_info in departments.items():
        dept_courses = {
            'id': dept_id,
            'name': dept_info['name'],
            'classes': 2,
            'courses': []
        }

        current_domain = ''

        # 從第 5 行開始讀取課程（跳過標題列，實際課程從 Row 4 開始）
        for row_idx in range(4, len(df)):
            row = df.iloc[row_idx]

            # 檢查是否為領域標題（第2欄）
            domain_cell = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
            if domain_cell and domain_cell != 'nan':
                # 處理領域名稱
                domain_cell = domain_cell.replace('\n', '').replace(' ', '')
                if '國文' in domain_cell or '社會' in domain_cell:
                    current_domain = '國文/社會'
                elif '英文' in domain_cell:
                    current_domain = '英文'
                elif '數學' in domain_cell or '自然' in domain_cell:
                    current_domain = '數學/自然'
                elif '會計' in domain_cell:
                    current_domain = '會計'
                elif '商經' in domain_cell:
                    current_domain = '商經'
                elif '資處' in domain_cell:
                    current_domain = '資處'
                elif '多媒' in domain_cell:
                    current_domain = '多媒'
                elif '藝能' in domain_cell:
                    current_domain = '藝能'

            # 課程名稱（第3欄）
            course_name = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ''

            if not course_name or course_name == 'nan':
                continue

            # 檢查是否為要排除的課程
            should_exclude = False
            for excluded in EXCLUDED_COURSES:
                if excluded in course_name:
                    should_exclude = True
                    break
            if should_exclude:
                continue

            # 收集各學期節數
            semesters = {}
            cols = dept_info['cols']

            for sem_key, col_idx in cols.items():
                if col_idx < len(row):
                    val = row.iloc[col_idx]
                    if pd.notna(val):
                        try:
                            semesters[sem_key] = int(float(val))
                        except (ValueError, TypeError):
                            semesters[sem_key] = 0
                    else:
                        semesters[sem_key] = 0
                else:
                    semesters[sem_key] = 0

            # 計算總學分
            total_credits = sum(semesters.values())

            # 如果該科系有這門課（至少有一個學期有節數）
            if total_credits > 0:
                # 決定課程領域：優先使用對照表，其次使用 current_domain
                final_domain = current_domain

                # 檢查課程名稱是否在對照表中
                for key, domain_value in COURSE_DOMAIN_MAP.items():
                    if key in course_name:
                        final_domain = domain_value
                        break

                course = {
                    'domain': final_domain,
                    'name': course_name,
                    'credits': total_credits,
                    'semesters': semesters
                }
                dept_courses['courses'].append(course)

        courses_data['departments'].append(dept_courses)

    return courses_data


def save_courses_json(data, output_path):
    """儲存課程資料到 JSON 檔案"""
    from datetime import datetime
    data['last_updated'] = datetime.now().strftime('%Y-%m-%d')

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"課程資料已儲存到 {output_path}")
    print(f"共 {len(data['departments'])} 個科系")
    for dept in data['departments']:
        print(f"  - {dept['name']}: {len(dept['courses'])} 門課程")

        # 顯示各領域
        domains = {}
        for course in dept['courses']:
            d = course.get('domain', '其他')
            if d not in domains:
                domains[d] = 0
            domains[d] += 1
        for d, count in domains.items():
            print(f"      {d}: {count} 門")


if __name__ == '__main__':
    excel_path = 'data/teacher.xlsx'
    output_path = 'data/courses.json'

    if os.path.exists(excel_path):
        courses = parse_courses_from_excel(excel_path)
        save_courses_json(courses, output_path)
    else:
        print(f"找不到檔案: {excel_path}")
