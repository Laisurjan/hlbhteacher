# Phase 2.2 A1 — xlsx-style grid editor UI + 新學年建空

## 前提：parser 與 eval 已由 Claude 完成

- `data/school_data.json` 的 `schedule[year].day.domains[*]` 已含：
  - `domain_id`（已對映到 12 domain；national_defense 透過 name fallback 補上）
  - `sum_row`, `sum_up`, `sum_down`（各含 `range={col, rows, start, end, tail}`, `formula`, `value`）
  - `subjects[*]`：`{row, name, cells, weighted_up, weighted_down}`
  - `weighted_up/down = {formula, coef, const, value, raw_value}`：coef 為 `{col_letter: 班數係數}`，const 為常數項，raw_value 為 Excel 硬編格（formula=null 時用）
- `utils/schedule_eval.py` 已建：
  - `compute_subject_weighted(cells, spec)` → int
  - `compute_domain_sum(domain, which)` → int
  - `apply_cell_edit(domain, row, col, new_value)` → 新四個值
  - `verify_domain(domain)` → round-trip 驗證（已證 26/26 全對）
- 驗證腳本：
  - `python scripts/verify_against_excel.py` → ✅ ALL MATCH
  - `python scripts/verify_schedule.py` → ✅ 全對

## 你的任務

### A. 後端 API（app.py）

**是否為 admin**：沿用既有 `is_admin()`；所有寫入 endpoint 都需 admin。

1. `GET /api/schedule/<year>` → 回 `school_data['schedule'][year]`（唯讀即可）
2. `PUT /api/schedule/<year>/<domain_id>/cell`
   - body: `{"row": 5, "col": "F", "value": 3}`
   - admin 僅；找到對應 domain + subject，更新 `cells[col]=value`
   - 呼叫 `schedule_eval.apply_cell_edit` 取得新的 `weighted_up/down.value` 與 `sum_up/down.value`
   - 寫回 school_data.json（保持 formula/coef/const/raw_value 不動）
   - 同步重算 `years[year][domain_id].required_day/evening/total`（用既有 `_decompose_required_formula` 的語義：summary D/L 公式把 `日<year>!AH<sum_row>` 替換成新的 sum_up.value，把 `日<year>!AI<sum_row>` 替換成新 sum_down.value；保留 evening 部分原值）
   - **實作提示**：可把 required_formula 做輕量 eval：
     - parse summary D/L formula stored in `years[year][domain_id].required_formula`
     - for each `日<year>!XY<N>` ref：若 XY == sum_up_col → 用新 sum_up.value；若 XY == sum_down_col → 用新 sum_down.value；若 sheet 是進修部 → 讀回舊 evening cell 值
   - 回 `{success, new_sum_up, new_sum_down, new_required_day, new_required_total}`
3. `POST /api/year/<year>` （新學年）
   - body: `{"copy_structure_from": "114"}`
   - admin 僅
   - 複製來源年度的 `schedule[source].day`（含 layout、class_columns、domains）結構
   - 所有 `subjects[*].cells` 清空為 `{}`；`weighted_up/down.value` 清為 0；`sum_up/down.value` 清為 0
   - 公式/係數/範圍全部保留（讓教務主任之後填 cells 時公式仍有效）
   - `years[new_year]` 也建立空骨架：各 domain `positions` 全 0、`required_hours/day/evening/total` 全 0、公式沿用
   - `available_years` 加入新年度
   - 回 `{success, year}`

### B. 前端 — xlsx-style grid editor

**新模板**：`templates/schedule.html`，路由 `/schedule`（在 index.html 導覽加連結）

**版面**（模仿 Excel 日校課程節數預估表）：
- 頂部：學年度下拉（available_years + 「＋新學年」按鈕）
- 下方：整個 day schedule 的大表格
  - 第一列：dept headers（merged 顯示：商經/幼保/廣告 × 學期 1/2）
  - 第二列：col letter（D, E, F, G, ... AE / AG）
  - 每 domain 之前插一 section header（顯示 domain_id 對應中文）
  - domain 內每個 subject 一列：`row | name | cells[D..AE] | weighted_up.value | weighted_down.value`
  - domain 結束後插 domain total 列：`sum_up.value | sum_down.value | tail`
- 每個 cell：`<input type="number" min="0">`（admin）或純文字（訪客）
- 每個 cell 獨立編輯、blur 時送 API、回傳後局部更新三個加總欄（該 subject 兩欄 + domain sum 兩欄 + 首頁的 required_day）

**新學年流程**：
- 下拉選 `＋新學年` → 彈 modal：「輸入新學年代碼（例：115），選擇從哪一年度複製結構」
- 送 POST /api/year/<year> 後自動切到新學年、表格顯示空 cell

### C. 驗證（Codex 做完後 Claude 跑）

1. `python scripts/verify_against_excel.py` → ✅ ALL MATCH（不破壞 Phase 1）
2. `python scripts/verify_schedule.py` → 26/26 recompute 通過
3. 手動編輯 chinese_social 113 row 5 的 F 格（原 3）改成 5：
   - weighted_up 從 72 → 76（+4 = +2×2）
   - sum_up 從 112 → 116
   - required_day 從 103 → 107
   - 首頁 required 顯示跟著變
4. 建 115 學年 copy_structure_from=114：
   - schedule[115].day.domains[*].subjects[*].cells 全 `{}`
   - weighted_up/down.value 全 0
   - `/api/summary?year=115` 所有 required 全 0、domains 結構在

### D. 不做

- 不改 `utils/excel_parser.py`、`utils/schedule_eval.py`（Claude 已確認）
- 不改 `calc_summary` / `calc_domain_summary`（Phase 2.1 已定案）
- 不改 teacher.xlsx（資料流單向：Excel → json；json 之後成為 source of truth）
- 不做 evening schedule 的編輯器（本輪只做日校）
- 不做係數/範圍 UI 可調（那是 Phase 3）
