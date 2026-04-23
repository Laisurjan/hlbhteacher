# Phase 2.1 — 需求節數日/進拆分 + 三模式切換

## 前提（已驗證完成，不需重動）
- Phase 1：`scripts/verify_against_excel.py` ✅ ALL MATCH
- Phase 2（登入 hash + 備註編輯 + /courses 員額編輯器 + /compare 真實比較）已完成
- 絕不修改 `data/teacher.xlsx`；所有資料流由 xlsx → `utils/excel_parser.py` → `data/school_data.json` → Flask API → 前端

## 本階段目標
1. 解析日校課程節數預估表（sheet index 1=日113、2=日114）到 `school_data.json`
2. 解析進修部課程節數（sheet index 4=進113）到 `school_data.json`
3. 解析進修部基本節數對照（sheet 5）供驗證
4. 每領域 × 每年度產出 `required_day` / `required_evening` / `required_total`
5. 計算器加三模式參數：`mode` ∈ {`strict`=現職務/寬鬆, `homeroom_all`=全導師/保守}、`include_substitute` bool
6. 首頁 `/` 與 `/compare` 加模式切換 UI，需求欄分「日 / 進 / 合計」三欄顯示
7. 不動編輯器（編輯器是 Phase 2.2）

## 實作步驟

### Step 1 — `utils/excel_parser.py` 擴充

新增函式：
```python
def parse_day_schedule(wb_values, sheet_name: str) -> dict:
    """解析『日113/114 課程節數預估表』。

    表頭：
      row 2: B=領域, C=科目名稱, D=一年級 (merged), N=二年級, X=三年級, AF=小計, AH=各領域總計
      row 3: D/F/H/J/L=多媒/資處/會計/商經/應英(一)；N~V=同(二)；X/Z/AB/AD=資處/會計/商經/應英(三)
      row 4: D/E=上/下，依此 2 欄一組
    領域列（B 欄有值、且長度 ≤ 10）：國文/社會, 英文, 數學/自然, 會計, 商經, 資處, 多媒, 藝能

    回傳：
    {
      "class_columns": [
        {"id": "multimedia-1", "grade": 1, "dept": "多媒", "col_upper": "D", "col_lower": "E"},
        ...
      ],  # 14 組
      "domain_sections": [
        {
          "domain_key": "國文/社會",      # 原始 B 欄字串
          "subjects": [
            {
              "name": "國語文",
              "row": 5,
              "hours_by_class_semester": {
                "multimedia-1": {"上": 3, "下": 3},
                ...
              }
            }, ...
          ]
        }, ...
      ],
      "total_by_domain": {"國文/社會": 132, "英文": 141, ...}   # 從 AH 欄讀（驗證用）
    }
    ```
  - domain_key → domain_id 對照表（放 module 常數）：
    ```python
    DAY_DOMAIN_TO_ID = {
      "國文/社會": "chinese_social",
      "英文": "english",
      "數學/自然": None,       # 數學與自然要拆，見下
      "會計": "accounting",
      "商經": "commerce",
      "資處": "info_tech",
      "多媒": "multimedia",
      "藝能": None,            # 藝能含 藝術 / 體育 / 健護 / 國防，見下
    }
    ```
  - 數學/自然段：subjects 中「自然科學探究與實作」「自然」類歸 `science`，其餘歸 `math`（以科目名稱 substring 判斷；若不明確，先比對 sheet0 的 D 欄總數，不符則在 log 出警告）
  - 藝能段：比對 sheet0 D 欄總數（藝術=21/22, 體育=61, 健護=34/25, 國防=11）逐科分派；每個科目以名稱判斷（美術/音樂→art，體育→pe，護理/健康/生涯→health_career，國防→national_defense）

```python
def parse_evening_schedule(wb_values) -> dict:
    """解析『進113課程節數一覽表』(sheet 4)。
    表頭：
      row 2: A=領域, B=科目名稱, C-I=班級（商經/資處/商訊 一二三年級，7 班，無學期拆分）
      J=小計，K=總計，L=備註，M=導師班名，N=導師姓名
      row 3: C=商經,D=資處,E=商訊,F=商經,G=資處,H=商經,I=資處
    領域列（A 欄非空）：語文, 英文, 數學, 會計科, 商經科, 資處科, 自然, 藝能, 體育, 健護, 國防, 輔導, 團體活動...
    """
```
  - `EVENING_DOMAIN_TO_ID` 對照表（進修部沒有多媒）
  - 語文 → chinese_social

```python
def parse_evening_baseline(wb_values) -> dict:
    """解析 sheet 5『113進修部-節數比較表』B/C 欄。
    回傳 {domain_id: {"baseline": B, "allocated": C}}，供驗證 parse_evening_schedule 的小計。
    """
```

**在主 parse_excel 裡**：
- 為每個 domain × year 計算 `required_day`（日校小計）、`required_evening`（進修部小計）、`required_total = day + evening`
- `schedule` 結構加到 school_data.json 頂層：
  ```json
  "schedule": {
    "113": {
      "day":     { ... parse_day_schedule 的回傳 ... },
      "evening": { ... parse_evening_schedule 的回傳 ... }
    },
    "114": {
      "day":     { ... sheet 2 ... },
      "evening": null    // 目前 Excel 只有 進113；114 進修部暫無來源
    }
  }
  ```
- `years[year][domain_id]` 加三個新欄位：
  ```
  "required_day": <int>,
  "required_evening": <int>,
  "required_total": <int>,
  ```
- `required_hours` 維持原值（= sheet 0 D/L 欄，只含日校；不刪，供驗證用）
- `schema_version` 從 1 → 2

**驗證（強制在 parse_excel 末尾做，不一致就 print 警告且 raise）**：
- 每個 domain × 113: `required_day` 必須 == sheet 0 D 欄值（`_excel_raw.113.D`）
- 每個 domain × 114: `required_day` 必須 == sheet 0 L 欄值（`_excel_raw.114.L`）
- 進113: 每個 domain `required_evening` 與 sheet 5 C 欄（分配節數）比對，允許 ±2 節誤差（sheet 5 手算可能有小誤）

### Step 2 — `utils/calculator.py` 三模式

新增 signature：
```python
def calc_domain_summary(
    domain_meta, year_state, position_columns,
    mode: str = "strict",
    include_substitute: bool = False,
) -> dict:
```

- `mode == "strict"`（現職務/寬鬆）：AI 與現行一致（Σ 人數×職務節數 + adjustment）
- `mode == "homeroom_all"`（全導師/保守）：AI = AH × 12（假設全員導師，不套 override 不套 adjustment）
- `include_substitute`：只影響 `avg_overload_position` 的分母 → `teacher_count = AH + (AK if include_substitute else 0)`；`base_position` / `base_homeroom` 不受影響（仍由 G/C 公式決定）

`required_hours` 欄位處理：
- `row["required_day"] = year_state.get("required_day", 0)`
- `row["required_evening"] = year_state.get("required_evening", 0)`
- `row["required_hours"] = year_state.get("required_total", year_state.get("required_hours", 0))`（向後相容；若 required_total 沒填就 fallback）
- `diff_position = required_hours - base_position`（用 total）

totals 同步新增 `required_day` / `required_evening` / `required_total` 三欄。

### Step 3 — `app.py` `/api/summary`

query 參數新增：
- `mode` (default `strict`) — 驗 `{strict, homeroom_all}`；不合法 → 400
- `include_sub` (`0`/`1`，default `0`)

把 mode + include_sub 傳給 `calc_summary`。回傳 `mode` + `include_substitute` 兩個欄位給前端。

### Step 4 — `templates/index.html` UI

表頭原「需求節數」改為 3 欄：「需求(日) / 需求(進) / 需求(合計)」。
頂部加一排控制列：
```
[ 學年度：113 | 114 ]   [ 模式：○ 現職務(寬鬆) ● 全導師(保守) ]   [ ☐ 含代理教師計算 ]
```
- radio/toggle 變更 → 重新 `GET /api/summary?year=...&mode=...&include_sub=0|1` → 重繪
- 表格每列新增三欄；totals 列同步

不動備註欄、不動模式切換 Excel 對照、不動登入流程。

### Step 5 — `templates/compare.html` UI

- 頂部控制列加同樣的 mode + 含代理 toggle（兩年共用）
- 比較表原「需求」欄 → 拆「需求(日) / 需求(進) / 需求(合計)」6 欄（左年 3 + 右年 3）+ 需求差（用合計 R - L）
- 換年度或切模式 → 重呼叫 `/api/summary`

### Step 6 — 驗證腳本

修改 `scripts/verify_against_excel.py`：
- 新增一組斷言：每個 domain × year 的 `required_day` == sheet0 D/L 欄
- 新增 `scripts/verify_schedule.py`（簡單）：從 `school_data.json['schedule']` 把每個 domain 的小時加總，列印和逐 domain 誤差

### 最後：跑一次
```
python utils/excel_parser.py
python scripts/verify_against_excel.py
python scripts/verify_schedule.py
python app.py   # 手動 curl / 瀏覽器驗收
```
`verify_against_excel.py` 必須維持 ✅ ALL MATCH。

## 交付清單
| 檔案 | 動作 |
|---|---|
| `utils/excel_parser.py` | 擴充解析 sheet 1/2/4/5，加 schedule 結構，加驗證 |
| `utils/calculator.py` | 加 mode + include_substitute 參數，rows/totals 多三欄 |
| `app.py` | `/api/summary` 加 mode/include_sub query；參數驗證 |
| `templates/index.html` | 模式切換 UI + 需求 3 欄 |
| `templates/compare.html` | 模式切換 UI + 雙側需求各 3 欄 |
| `scripts/verify_against_excel.py` | 新增 required_day 斷言 |
| `scripts/verify_schedule.py` | 新檔，簡單小計驗證 |
| `data/school_data.json` | 由 `excel_parser.py` 重新產生（不要手改） |

## 範圍外（Phase 2.2 再說）
- 仿 xlsx 的可編輯表格 UI（/schedule 頁）
- 新學年匯入流程
- 115 學年度資料
- 進修部 114 資料（Excel 沒有，暫不處理）
