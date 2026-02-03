# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概述

教師員額控管網頁系統 - 供國立花蓮高級商業職業學校教務主任維護、全校教師檢視的教師節數管理系統。

## 常用指令

```bash
# 啟動開發伺服器
python app.py
# 伺服器會在 http://localhost:5000 運行
# 管理員密碼：admin123

# 從 Excel 重新產生課程資料
python utils/excel_parser.py
```

## 系統架構

### 後端 (Flask)
- `app.py` - 主程式，包含所有路由和 API
  - `/` - 首頁（節數總覽）
  - `/courses` - 課程管理
  - `/api/*` - REST API 端點

### 前端 (純 HTML/CSS/JS)
- `templates/index.html` - 節數總覽頁面，顯示各領域人力狀況
- `templates/courses.html` - 課程管理，支援日間部/進修部切換

### 資料儲存 (JSON)
- `data/courses.json` - 課程資料，結構：`{ day_school: { departments: [...] }, evening_school: { departments: [...] } }`
- `data/teachers.json` - 教師資料與各領域統計
- `data/settings.json` - 系統設定

### 工具模組
- `utils/excel_parser.py` - 從 teacher.xlsx 解析課程資料

## 領域對應關係

teachers.json 的領域 ID 與 courses.json 的領域名稱對應：
| ID | 名稱 |
|----|------|
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

### 核心理念
用簡單、清楚、易維護的方式寫程式。使用者是程式設計初學者。

### 必須遵守
1. **KISS** - 優先用 if-else 而不是三元運算子或複雜的 lambda
2. **DRY** - 重複邏輯（3次以上）寫成函數
3. **YAGNI** - 只做當前需要的功能
4. **單一職責** - 每個函數只做一件事，超過 20 行考慮拆分

### 程式碼風格
- 函數命名：`動詞_名詞`，如 `calculate_grade()`
- 變數命名：清楚描述內容，如 `student_scores` 而非 `data`
- **使用中文註解**
- 每個函數都要有說明用途的註解

### JavaScript 注意事項
- 使用 `function` 宣告而非箭頭函數
- 避免複雜的鏈式呼叫
