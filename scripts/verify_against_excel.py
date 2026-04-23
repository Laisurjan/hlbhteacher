# -*- coding: utf-8 -*-
"""把 calculator 算出來的數字 vs Excel 原檔 data_only 的結果逐格比對。

任何差異都印出；全對就印 ✅ ALL MATCH。
"""

from __future__ import annotations

import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from utils.calculator import calc_summary  # noqa: E402


def _load_school_data() -> dict:
    path = os.path.join(HERE, "data", "school_data.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _diff(label: str, got, expected) -> str | None:
    """Excel 空白格 = 0，計算結果 None 也視為 0；避免邊緣列（如全民國防）誤報。"""
    def _norm(v):
        return 0 if v is None else v
    if got is None and expected is None:
        return None
    try:
        if int(_norm(got)) == int(_norm(expected)):
            return None
        return f"  [{label}] got={got} expected={expected} diff={int(_norm(got))-int(_norm(expected)):+d}"
    except (TypeError, ValueError):
        return f"  [{label}] got={got!r} expected={expected!r}"


def verify(school_data: dict) -> int:
    snapshot = school_data["excel_raw_snapshot"]
    total_fail = 0

    for year in school_data["available_years"]:
        # Excel 原檔語義：
        #   C/K (base_homeroom) 公式 (AH+AK)*X → 本就含代理，用 include_sub=True 比對
        #   G   (base_position) 公式 AI+adj    → 本就不含代理，用 include_sub=False 比對
        #   E/I/M (diff_*) 跟著對應的 base 走
        #   O   (future_base) 公式 (AH+AK)*X → 同 C/K，用 include_sub=True
        #   AH/AI/AK 原始值與 include_sub 無關（這三個欄位固定回傳原始值）
        summary_incl = calc_summary(school_data, year, include_substitute=True)
        summary_excl = calc_summary(school_data, year, include_substitute=False)
        rows_incl = {r["domain_id"]: r for r in summary_incl["rows"]}
        rows_excl = {r["domain_id"]: r for r in summary_excl["rows"]}
        print(f"\n=== Year {year} ===")

        for dom_id in rows_incl:
            # 全民國防是教官支援，Excel 該列無公式、E/I/M 為手工填值，不納入驗收
            if dom_id == "national_defense":
                print(f"⏭  {dom_id} ({rows_incl[dom_id]['domain_name']}) 略過（軍訓教官手工列）")
                continue
            row_incl = rows_incl[dom_id]
            row_excl = rows_excl[dom_id]
            raw_by_section = snapshot[dom_id]
            problems: list[str] = []

            if year == "113":
                raw = raw_by_section["113"]
                problems.append(_diff("C base_homeroom", row_incl["base_homeroom"], raw.get("C")))
                problems.append(_diff("G base_position", row_excl["base_position"], raw.get("G")))
                problems.append(_diff("D required",      row_incl["required_hours"], raw.get("D")))
                problems.append(_diff("D required_total", row_incl["required_total"], raw.get("D")))
                problems.append(_diff("E diff_homeroom", row_incl["diff_homeroom"], raw.get("E")))
                problems.append(_diff("I diff_position", row_excl["diff_position"], raw.get("I")))
                problems.append(_diff("AH formal_count", row_incl["AH_formal_count"], raw.get("AH")))
                problems.append(_diff("AI weighted",      row_incl["AI_weighted_hours"], raw.get("AI")))
                problems.append(_diff("AK substitute",   row_incl["AK_substitute"], raw.get("AK")))
                # 115 未來預估（以 113 AH/AI/AK 代入 O 欄公式計算；公式 (AH+AK)*X 本身含代理）
                future_raw = raw_by_section.get("115_future", {})
                problems.append(_diff("O future_base",  row_incl["future_base"], future_raw.get("O")))
                # Phase 2.1 新欄位：day + evening == total
                if row_incl["required_day"] + row_incl["required_evening"] != row_incl["required_total"]:
                    problems.append(
                        f"  [required_day+eve!=total] day={row_incl['required_day']} eve={row_incl['required_evening']} total={row_incl['required_total']}"
                    )
            else:  # 114
                raw = raw_by_section["114"]
                problems.append(_diff("K base_homeroom", row_incl["base_homeroom"], raw.get("K")))
                problems.append(_diff("L required",      row_incl["required_hours"], raw.get("L")))
                problems.append(_diff("L required_total", row_incl["required_total"], raw.get("L")))
                problems.append(_diff("M diff_homeroom", row_incl["diff_homeroom"], raw.get("M")))
                if row_incl["required_day"] + row_incl["required_evening"] != row_incl["required_total"]:
                    problems.append(
                        f"  [required_day+eve!=total] day={row_incl['required_day']} eve={row_incl['required_evening']} total={row_incl['required_total']}"
                    )

            problems = [p for p in problems if p]
            if problems:
                total_fail += len(problems)
                print(f"❌ {dom_id} ({row_incl['domain_name']})")
                for p in problems:
                    print(p)
            else:
                print(f"✅ {dom_id} ({row_incl['domain_name']})")

    if total_fail == 0:
        print("\n✅ ALL MATCH")
        return 0
    print(f"\n❌ {total_fail} 個欄位差異")
    return 1


if __name__ == "__main__":
    data = _load_school_data()
    sys.exit(verify(data))
