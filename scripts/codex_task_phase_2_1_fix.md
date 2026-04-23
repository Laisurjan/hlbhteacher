# Phase 2.1 Bugfix：include_substitute 應該一致地影響基本節數

## 現況 Bug

使用者回報：勾選「含代理教師計算」後，**只有每人平均超時節數（avg_overload_position）改變**，基本節數（base_homeroom / base_position）沒變。這不符合直覺。

根因在 `utils/calculator.py::calc_domain_summary`：

```python
sub_count = int(year_state.get("substitute_count", 0) or 0)
...
env = {"AH": ah, "AI": ai, "AK": sub_count}   # ← 無條件把 AK 塞進 env
...
teacher_count = ah + (sub_count if include_substitute else 0)
```

Excel 原始公式中：
- `base_homeroom_formula` 寫死 `(AH+AK)*X`（X = 10/12）→ 只要 `env.AK` 有值就一定會算到代理
- `base_position_formula` 只吃 `AI`（如 `AI5+26`）→ 代理從來進不來

所以當前「勾選」語義不完整：
- `base_homeroom` 不管勾不勾都含代理 ❌
- `base_position` 不管勾不勾都不含代理 ❌
- 只有 `avg_overload_position` 分母真的受切換影響 ✓

## 目標行為（統一語義）

切換 `include_substitute` 要**全面**影響計算：

| 項目 | unchecked（只算正式） | checked（含代理） |
|---|---|---|
| `AH` effective | `AH`（正式） | `AH + AK` |
| `AI` effective | `AI`（正式加權） | `AI + AK × 16` |
| `env.AK` 傳入公式 | `0` | `AK`（代理人數） |
| `base_homeroom` | `(AH+0)×X = 純正式` | `(AH+AK)×X` = 原 Excel 值 |
| `base_position` | `AI+adj` = 純正式 | `(AI + AK×16) + adj` = 含代理 |
| `teacher_count`（avg 分母） | `AH` | `AH + AK` |

**代理鐘點選 16 的理由**：`position_columns` 裡 AG = `專任(16節)` = 在校最高常態鐘點，實務上代理缺額就是補專任，故選 16。常數定義成 `SUBSTITUTE_TEACHER_RATE = 16` 放在檔頭方便日後調整。

---

## 實作點

### A. `utils/calculator.py`（主要修改）

1. 檔頭加常數：
   ```python
   SUBSTITUTE_TEACHER_RATE = 16   # 含代理計算時，代理比照 AG 專任 16 節
   ```

2. `calc_domain_summary` 改為：
   ```python
   ah = compute_ah(positions, override=domain_meta.get("ah_override"))
   if mode == "homeroom_all":
       ai_base = ah * _HOMEROOM_RATE
   else:
       ai_base = compute_ai(
           positions, position_columns,
           adjustment=domain_meta.get("ai_adjustment", 0),
           override=domain_meta.get("ai_override"),
       )

   extra_sub = sub_count if include_substitute else 0
   ah_eff = ah + extra_sub
   if mode == "homeroom_all":
       ai_eff = ah_eff * _HOMEROOM_RATE
   else:
       ai_eff = ai_base + extra_sub * SUBSTITUTE_TEACHER_RATE

   env = {"AH": ah_eff, "AI": ai_eff, "AK": extra_sub}
   ```

3. `teacher_count` 改為 `ah_eff`（因已含代理），保留 `avg_overload_position` 原計算邏輯。

4. 對外回傳欄位：
   - `AH_formal_count` 仍回**原始 AH（正式人數）**，不要回 `ah_eff`（前端「正式教師」欄要維持正式意義）
   - `AI_weighted_hours` 改回 `ai_eff`（這樣前端 Excel 原值對照時 checked → 有差異、unchecked → 吻合 Excel AI？

     → **錯，AI_weighted_hours 也要維持原 AI（不含代理）**，因為 `verify_against_excel.py` 是用 unchecked 模式下的原 AI 對 Excel 比。
   - 結論：**`AH/AI/AK` 三個對外欄位一律回「原始正式 / 原始 AI / 原始 AK」，不要被 include_sub 污染**；base_homeroom / base_position / avg_overload / diff 才是 include_sub 的產物。

### B. `scripts/verify_against_excel.py`

因為「新的 unchecked 預設 = 只算正式」會跟 Excel 原值（含代理）對不上，改為跑 **`include_substitute=True`** 做比對：

```python
summary = calc_summary(school_data, year, include_substitute=True)
```

這個 verify 的語義變成「含代理模式下 100% 復刻 Excel」，與 Phase 1 目標一致，並明確釘死「Excel = checked 模式 = 含代理」。

### C. `scripts/verify_schedule.py`

**不動**。Schedule 結構驗證與 include_sub 無關。

### D. `templates/index.html` 的說明區（info-section 或 tooltip）

把「含代理教師計算」的說明改成：

> 預設只計入正式教師（AH / 職務法 AI）。勾選後，代理教師按 AG 專任 16 節併入，會改變 base_homeroom / base_position / 每人平均超時節數。不勾選 = 與 Excel「代理欄外推」版本一致；勾選 = 與 Excel 原檔公式結果一致。

### E. `templates/compare.html`

只需確認 include_sub 勾選後，兩邊 base_position 顯示會跟著變。不需改程式碼（`/api/summary` 的回傳結構沒變）。

---

## 驗收（Codex 完成後 Claude 跑）

### 單元驗證
1. `python scripts/verify_against_excel.py` → **✅ ALL MATCH**（因改為 include_sub=True 跑）
2. `python scripts/verify_schedule.py` → 全 ✅

### API 驗證（chinese_social 領域，113 學年；公式 `(AH+AK)*10` 與 `AI+26`）
假設 AH=13、AK=1、AI=? 先跑一次看實際值，然後確認：

| 請求 | `base_homeroom` 應等於 | `base_position` 應等於 |
|---|---|---|
| `/api/summary?year=113` (預設) | `(13+0)*10 = 130` | `AI + 26` |
| `/api/summary?year=113&include_sub=1` | `(13+1)*10 = 140` | `(AI + 1*16) + 26 = AI + 42` |

3. 上述兩種呼叫的 `base_homeroom` 應差 `AK × 10 = 10`
4. 上述兩種呼叫的 `base_position` 應差 `AK × 16 = 16`
5. `AH_formal_count` / `AI_weighted_hours` 在兩種呼叫下**應相等**（都是原始值）

### 瀏覽器驗證
6. 首頁切勾選：整排 base_homeroom / base_position / diff_position / avg_overload 都要有數字變動
7. compare 頁勾 `cmp-include-sub` → 左右兩邊的 `base_position` 都要跟著變

---

## 範圍外

- 不改 `teacher.xlsx` 原檔
- 不動 `required_day / required_evening / required_total`（那是節數來源，與教師員額無關）
- 不調整 `data/school_data.json` 內容（公式與代理人數維持原值）
- 代理鐘點預設 16，不另外做 UI 可調；如日後要可調，Phase 3 再加
