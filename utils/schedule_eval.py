# -*- coding: utf-8 -*-
"""日校課程節數表的重算引擎。

Phase 2.2 A1：教務主任在 xlsx-style grid 裡改 cell → 觸發 recompute。
三層 roll-up：
  1. cell  → subject weighted_up/down = Σ cells[col] × coef[col] + const
  2. subject → domain sum_up/down = Σ subjects 加權值 + tail
  3. domain sum → required_day/total（透過既有的 summary D/L 公式語義，見 excel_parser._decompose_required_formula）

此模組不寫 xlsx，只對 school_data.json 的 schedule 結構做純函式運算。
"""

from __future__ import annotations


def compute_subject_weighted(cells: dict, spec: dict) -> int:
    """回傳 subject 的上(或下)學期加權節數值。

    spec 為 schedule[year]['day']['domains'][i]['subjects'][j]['weighted_up'] 或 'weighted_down'，
    含 coef / const / raw_value / formula 四欄。若 formula 為 None 代表 Excel 原檔硬編數字，
    直接回 raw_value；否則 Σ cells[col] × coef[col] + const。
    """
    if spec.get("formula") is None:
        return int(spec.get("raw_value") or 0)
    total = int(spec.get("const", 0) or 0)
    for col, coef in (spec.get("coef") or {}).items():
        v = cells.get(col)
        if isinstance(v, (int, float)):
            total += int(v) * int(coef)
    return total


def compute_domain_sum(domain: dict, which: str = "up") -> int:
    """回傳 domain 上(或下)學期 SUM 節數。which ∈ {'up', 'down'}。

    = Σ 範圍內 subjects 的 weighted_<which> + tail。範圍與 tail 取自 domain['sum_<which>']。
    """
    sum_key = f"sum_{which}"
    weighted_key = f"weighted_{which}"
    sum_block = domain.get(sum_key) or {}
    rng = sum_block.get("range") or {}
    rows = rng.get("rows")
    tail = int(rng.get("tail") or 0)
    if not rows:
        # 後備：若 rows 欠缺，沿用 start/end 區間
        start = rng.get("start")
        end = rng.get("end")
        if start is None or end is None:
            return 0
        rows = list(range(int(start), int(end) + 1))
    row_to_subj = {s.get("row"): s for s in domain.get("subjects", [])}
    total = tail
    for r in rows:
        subj = row_to_subj.get(r)
        if subj is None:
            continue
        total += compute_subject_weighted(subj.get("cells") or {}, subj.get(weighted_key) or {})
    return total


def apply_cell_edit(domain: dict, row: int, col: str, new_value: int) -> dict:
    """修改某個 subject 的 cell 值後，回傳含新 weighted_up/down 與 domain sum 的結果。

    不改動 domain 本身（保持 immutable 習慣）。回傳：
        {
          'subject_row': row,
          'weighted_up_new': int,
          'weighted_down_new': int,
          'domain_sum_up_new': int,
          'domain_sum_down_new': int,
        }
    """
    subj = next((s for s in domain.get("subjects", []) if s.get("row") == row), None)
    if subj is None:
        raise ValueError(f"row {row} 不存在於 domain {domain.get('domain_id')!r}")
    # 建一個 shallow-copy domain 做試算
    new_cells = dict(subj.get("cells") or {})
    new_cells[col] = int(new_value or 0)
    new_subj = dict(subj)
    new_subj["cells"] = new_cells
    new_domain = dict(domain)
    new_domain["subjects"] = [new_subj if s.get("row") == row else s for s in domain.get("subjects", [])]
    return {
        "subject_row":        row,
        "weighted_up_new":    compute_subject_weighted(new_cells, new_subj.get("weighted_up") or {}),
        "weighted_down_new":  compute_subject_weighted(new_cells, new_subj.get("weighted_down") or {}),
        "domain_sum_up_new":  compute_domain_sum(new_domain, "up"),
        "domain_sum_down_new": compute_domain_sum(new_domain, "down"),
    }


def verify_domain(domain: dict) -> list[str]:
    """把 domain 內每個 subject 的 weighted_up/down 重算一次，跟 Excel 原值對帳。

    回傳 list[str] 的不合紀錄；全對回傳 []。
    """
    errors: list[str] = []
    for subj in domain.get("subjects", []):
        for which in ("up", "down"):
            spec = subj.get(f"weighted_{which}") or {}
            expected = int(spec.get("value") or 0)
            got = compute_subject_weighted(subj.get("cells") or {}, spec)
            if got != expected:
                errors.append(
                    f"  subject row {subj.get('row')} {subj.get('name')!r} {which}: "
                    f"recompute={got} excel={expected} diff={got - expected:+d}"
                )
    for which in ("up", "down"):
        sum_block = domain.get(f"sum_{which}") or {}
        expected = int(sum_block.get("value") or 0)
        got = compute_domain_sum(domain, which)
        if got != expected:
            errors.append(
                f"  domain {domain.get('domain_id')} sum_{which}: "
                f"recompute={got} excel={expected} diff={got - expected:+d}"
            )
    return errors
