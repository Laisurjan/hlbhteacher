# -*- coding: utf-8 -*-
"""
PDF 課綱解析工具

這個模組負責：
1. 讀取課綱 PDF 檔案
2. 找出課程名稱和節數
3. 過濾掉表格標題等非課程資料

設計原則：簡單、易懂、好維護
"""

import pdfplumber


def parse_curriculum_pdf(pdf_path):
    """解析課綱 PDF 檔案

    Args:
        pdf_path: PDF 檔案的路徑
    Returns:
        解析結果（字典格式）
    """
    # 準備回傳的結果
    result = {
        'success': True,
        'pages_count': 0,
        'tables_found': 0,
        'courses': [],
        'raw_tables': [],
        'error': None
    }

    # 這些關鍵字出現時，代表這行是標題或小計，不是課程
    # 用簡單的方式過濾
    title_keywords = [
        '教學科目', '學分', '節數', '表', '課程類別',
        '學年度', '入學', '適用', '部定', '校訂',
        '必修', '選修', '名稱', '類別', '群科',
        '一年級', '二年級', '三年級', '上', '下',
        '科目', '領域', '商業與管理', '設計群',
        '小計', '總計', '合計', '總節數'  # 過濾小計行
    ]

    try:
        # 開啟 PDF 檔案
        with pdfplumber.open(pdf_path) as pdf:
            result['pages_count'] = len(pdf.pages)

            # 逐頁處理
            for page_num, page in enumerate(pdf.pages):
                # 嘗試擷取表格
                tables = page.extract_tables()

                if tables:
                    result['tables_found'] += len(tables)

                    # 處理每個表格
                    for table in tables:
                        if not table:
                            continue

                        # 處理表格中的每一行
                        for row in table:
                            # 嘗試解析這一行
                            course = try_parse_course_row(row, title_keywords)

                            if course:
                                result['courses'].append(course)

                        # 儲存原始表格（除錯用）
                        result['raw_tables'].append({
                            'page': page_num + 1,
                            'rows': len(table)
                        })

    except Exception as e:
        result['success'] = False
        result['error'] = str(e)

    return result


def try_parse_course_row(row, title_keywords):
    """嘗試解析一行資料，判斷是否為課程

    判斷邏輯：
    1. 第一欄應該是課程名稱（中文字，2-20字）
    2. 後面應該有數字（節數）
    3. 不能包含標題關鍵字

    Args:
        row: 表格的一行資料（列表）
        title_keywords: 標題關鍵字列表
    Returns:
        課程資料（字典）或 None
    """
    # 如果是空行，跳過
    if not row:
        return None

    # 清理每個欄位
    cleaned_row = []
    for cell in row:
        if cell is None:
            cleaned_row.append('')
        else:
            # 清理空白和換行
            cleaned_row.append(str(cell).strip().replace('\n', ''))

    # 找出第一個非空欄位當作課程名稱
    course_name = ''
    name_index = -1
    for i, cell in enumerate(cleaned_row):
        if cell and len(cell) >= 2:
            course_name = cell
            name_index = i
            break

    # 如果沒有課程名稱，跳過
    if not course_name:
        return None

    # 檢查是否為標題（包含標題關鍵字）
    for keyword in title_keywords:
        if keyword in course_name:
            return None

    # 檢查課程名稱是否合理（至少有一個中文字）
    has_chinese = any('\u4e00' <= char <= '\u9fff' for char in course_name)
    if not has_chinese:
        return None

    # 找出數字（節數）
    numbers = []
    for i, cell in enumerate(cleaned_row):
        if i == name_index:
            continue  # 跳過課程名稱欄

        # 嘗試轉換成數字
        try:
            num = int(float(cell))
            if 0 <= num <= 20:  # 合理的節數範圍
                numbers.append(num)
        except (ValueError, TypeError):
            pass

    # 如果沒有找到數字，可能不是課程行
    if len(numbers) == 0:
        return None

    # 計算總學分（所有數字加總）
    total_credits = sum(numbers)

    # 如果總學分為 0，跳過
    if total_credits == 0:
        return None

    # 回傳課程資料
    return {
        'name': course_name,
        'credits': total_credits,
        'semesters': numbers,  # 各學期節數
        'domain': '',  # 領域待定
        'category': ''  # 類別待定
    }


def test_pdf_parser(pdf_path):
    """測試 PDF 解析功能

    用於開發和除錯

    Args:
        pdf_path: 要測試的 PDF 檔案路徑
    """
    print(f"測試解析 PDF: {pdf_path}")
    print("-" * 50)

    result = parse_curriculum_pdf(pdf_path)

    print(f"頁數: {result['pages_count']}")
    print(f"找到表格數: {result['tables_found']}")
    print(f"解析到的課程數: {len(result['courses'])}")

    if result['courses']:
        print("\n課程列表（前 20 筆）:")
        for i, course in enumerate(result['courses'][:20]):
            semesters = course.get('semesters', [])
            sem_str = ' '.join(str(s) for s in semesters)
            print(f"  {course['name']}: 總{course['credits']}節 [{sem_str}]")

    if result.get('error'):
        print(f"\n錯誤: {result['error']}")

    return result


# 如果直接執行此檔案，進行測試
if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        test_pdf_parser(sys.argv[1])
    else:
        # 預設測試 data/115.pdf
        test_pdf_parser('data/115.pdf')
