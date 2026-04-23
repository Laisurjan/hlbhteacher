# -*- coding: utf-8 -*-
"""檢查 school_data.json 的 schedule 結構是否合理。

- schedule.<year>.day.sections 每個 section 列印科目數與 cells 總和
- schedule.<year>.evening.sections 同上
- 附帶列印每個 domain × year 的 required_day/evening/total，供目視檢查
"""

from __future__ import annotations

import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from utils.schedule_eval import verify_domain  # noqa: E402


def _load() -> dict:
    path = os.path.join(HERE, "data", "school_data.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _sum_cells(section: dict) -> int:
    total = 0
    for subj in section.get("subjects", []):
        for v in subj.get("cells", {}).values():
            if isinstance(v, (int, float)):
                total += int(v)
    return total


def main() -> int:
    data = _load()
    print(f"schema_version = {data.get('schema_version')}")
    if data.get("schema_version") != 2:
        print("  ⚠️ schema_version 不是 2，請重跑 utils/excel_parser.py")
        return 1

    print("\n=== Schedule sections ===")
    for year, div_map in (data.get("schedule") or {}).items():
        print(f"\n- {year} 學年度")
        day = (div_map or {}).get("day")
        if day:
            layout = day.get("layout", {})
            print(f"    day: {len(day.get('class_columns', []))} 班格, {len(day.get('domains', []))} 領域段  layout={layout}")
            for dm in day.get("domains", []):
                did = dm.get("domain_id") or "(未對映)"
                n_sub = len(dm.get("subjects", []))
                total = _sum_cells(dm)
                up = dm.get("sum_up", {})
                rng = up.get("range", {})
                print(f"      - {did:<22} rows {rng.get('start')}..{rng.get('end')} tail={rng.get('tail'):+d}  {n_sub} 科目  節數合計 {total}  sum_up.value={up.get('value')}")
        else:
            print("    day: (無資料)")
        eve = (div_map or {}).get("evening")
        if eve:
            print(f"    evening: {len(eve.get('class_columns', []))} 班格, {len(eve.get('sections', []))} 領域段")
            for s in eve.get("sections", []):
                key = s.get("section_key", "?")
                n_sub = len(s.get("subjects", []))
                total = _sum_cells(s)
                print(f"      - {key}: {n_sub} 科目, 節數合計 {total}")
        else:
            print("    evening: (無資料)")

    print("\n=== Subject weighted_up/down recompute vs Excel ===")
    total_err = 0
    for year, div_map in (data.get("schedule") or {}).items():
        day = (div_map or {}).get("day")
        if not day:
            continue
        for dm in day.get("domains", []):
            errs = verify_domain(dm)
            did = dm.get("domain_id") or "(未對映)"
            if errs:
                total_err += len(errs)
                print(f"  ❌ {year} {did}")
                for e in errs:
                    print(e)
            else:
                print(f"  ✅ {year} {did} ({len(dm.get('subjects', []))} 科目 / sum 全對)")
    if total_err:
        print(f"\n❌ 加權重算共 {total_err} 筆不合")
        return 1
    print("\n✅ 加權公式 round-trip 全對（cells × coef + const == Excel 值）")

    print("\n=== Per domain × year required_day / evening / total ===")
    for year in data.get("available_years", []):
        print(f"\n- {year}")
        y = data["years"].get(str(year), {})
        for dom in data.get("domains", []):
            state = y.get(dom["id"], {})
            day = state.get("required_day")
            eve = state.get("required_evening")
            tot = state.get("required_total")
            rh  = state.get("required_hours")
            ok = (day or 0) + (eve or 0) == (tot or 0) == (rh or 0)
            marker = "✅" if ok else "❌"
            print(f"  {marker} {dom['id']:<20} day={day:>4} eve={eve:>3} total={tot:>4} required_hours={rh}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
