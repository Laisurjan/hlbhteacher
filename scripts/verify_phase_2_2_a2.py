# -*- coding: utf-8 -*-
"""Phase 2.2 A2 驗證腳本：測試進修部 cell 編輯、日校科目 CRUD、班級數係數調整。

執行：python scripts/verify_phase_2_2_a2.py
結束後還原 school_data.json。
"""

from __future__ import annotations

import json
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from app import app  # noqa: E402

DATA_PATH = os.path.join(HERE, "data", "school_data.json")
BACKUP_PATH = os.path.join(HERE, "data", "school_data.backup_a2.json")


def _load():
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _login(client):
    with client.session_transaction() as sess:
        sess["is_admin"] = True


def _check(label, cond, detail=""):
    mark = "✅" if cond else "❌"
    print(f"  {mark} {label}" + (f"  {detail}" if detail else ""))
    return cond


def _find_day_subject(data, year, domain_id, row):
    day = data["schedule"][year]["day"]
    for dom in day["domains"]:
        if dom.get("domain_id") == domain_id:
            for s in dom["subjects"]:
                if int(s.get("row", -1)) == row:
                    return dom, s
    return None, None


def _find_eve_section(data, year, section_key):
    eve = data["schedule"][year]["evening"]
    for s in eve["sections"]:
        if s.get("section_key") == section_key:
            return s
    return None


def run():
    shutil.copy2(DATA_PATH, BACKUP_PATH)
    print(f"備份 → {BACKUP_PATH}")
    try:
        _run_tests()
    finally:
        shutil.move(BACKUP_PATH, DATA_PATH)
        print("\n已還原 data/school_data.json。")


def _run_tests():
    client = app.test_client()

    # -------- 1. 進修部 cell 編輯 --------
    print("\n=== 1) PUT /api/schedule/113/evening/語文/cell (未登入→403) ===")
    res = client.put(
        "/api/schedule/113/evening/語文/cell",
        json={"row": 4, "col": "C", "value": 3},
    )
    _check("未登入回 403", res.status_code == 403, f"status={res.status_code}")

    _login(client)

    print("\n=== 2) PUT 語文 C4: +1 / -1 驗證 subtotal/total_K/required_evening 同步變動 ===")
    before = _load()
    sec = _find_eve_section(before, "113", "語文")
    subj4 = next(s for s in sec["subjects"] if s["row"] == 4)
    before_c = subj4["cells"].get("C")

    # 先做一個 no-op edit（寫入相同值）觸發 recompute，讓 required_evening 達到穩定 baseline
    # （school_data.json 的原始 required_evening 可能是 Excel 匯入時的值，不等於 recompute 結果）
    client.put(
        "/api/schedule/113/evening/語文/cell",
        json={"row": 4, "col": "C", "value": before_c},
    )
    baseline = _load()
    base_sub = next(s for s in _find_eve_section(baseline, "113", "語文")["subjects"] if s["row"] == 4)["subtotal_J"]
    base_total = _find_eve_section(baseline, "113", "語文")["subjects"][0]["total_K"]
    base_req_eve = baseline["years"]["113"]["chinese_social"]["required_evening"]

    # 加 1：value = before_c + 1
    res = client.put(
        "/api/schedule/113/evening/語文/cell",
        json={"row": 4, "col": "C", "value": before_c + 1},
    )
    data = res.get_json()
    _check("status=200", res.status_code == 200, repr(data))
    _check(
        "subtotals_new[4] = base+1",
        data["subtotals_new"]["4"] == base_sub + 1,
        f"base={base_sub} now={data['subtotals_new']['4']}",
    )
    _check(
        "total_K_new = base+1",
        data["total_K_new"] == base_total + 1,
        f"base={base_total} now={data['total_K_new']}",
    )

    after = _load()
    sub_after = next(s for s in _find_eve_section(after, "113", "語文")["subjects"] if s["row"] == 4)
    _check("cells.C 已寫入", sub_after["cells"].get("C") == before_c + 1)
    req_eve_after = after["years"]["113"]["chinese_social"]["required_evening"]
    _check(
        "required_evening 增 1",
        req_eve_after == base_req_eve + 1,
        f"base={base_req_eve} after={req_eve_after}",
    )

    # 還原
    client.put(
        "/api/schedule/113/evening/語文/cell",
        json={"row": 4, "col": "C", "value": before_c},
    )
    restored = _load()
    rc = next(s for s in _find_eve_section(restored, "113", "語文")["subjects"] if s["row"] == 4)
    _check("cells.C 已還原", rc["cells"].get("C") == before_c)

    # -------- 2. 日校科目新增/改名/刪除 --------
    print("\n=== 3) POST /api/schedule/113/chinese_social/subject (新增『測試科目』) ===")
    before = _load()
    chinese = next(
        d for d in before["schedule"]["113"]["day"]["domains"] if d["domain_id"] == "chinese_social"
    )
    before_rows = {int(s["row"]) for s in chinese["subjects"]}

    res = client.post(
        "/api/schedule/113/chinese_social/subject",
        json={"name": "測試科目"},
    )
    data = res.get_json()
    _check("status=200", res.status_code == 200, repr(data))
    new_row = data.get("row")
    _check("回傳 row 為新值", isinstance(new_row, int) and new_row not in before_rows)

    after = _load()
    chinese_a = next(
        d for d in after["schedule"]["113"]["day"]["domains"] if d["domain_id"] == "chinese_social"
    )
    new_subj = next((s for s in chinese_a["subjects"] if int(s["row"]) == new_row), None)
    _check("新 subject 存在", new_subj is not None)
    _check("name = 測試科目", new_subj and new_subj.get("name") == "測試科目")
    _check("cells 為空", new_subj and new_subj.get("cells") == {})
    # 檢查 coef 是否從第一個科目複製
    first_coef_up = (chinese_a["subjects"][0].get("weighted_up") or {}).get("coef") or {}
    new_coef_up = (new_subj.get("weighted_up") or {}).get("coef") or {}
    _check(
        "coef_up 結構複製自 template（同 keys）",
        set(first_coef_up.keys()) == set(new_coef_up.keys()),
    )

    print("\n=== 4) PATCH .../subject/<new_row> 改名為『測試A』 ===")
    res = client.patch(
        f"/api/schedule/113/chinese_social/subject/{new_row}",
        json={"name": "測試A"},
    )
    data = res.get_json()
    _check("status=200", res.status_code == 200, repr(data))
    _check("name=測試A", data.get("name") == "測試A")

    print("\n=== 5) DELETE .../subject/<new_row> ===")
    res = client.delete(f"/api/schedule/113/chinese_social/subject/{new_row}")
    data = res.get_json()
    _check("status=200", res.status_code == 200, repr(data))
    after2 = _load()
    chinese_b = next(
        d for d in after2["schedule"]["113"]["day"]["domains"] if d["domain_id"] == "chinese_social"
    )
    _check(
        "subject 已移除",
        all(int(s["row"]) != new_row for s in chinese_b["subjects"]),
    )
    # 從 sum range.rows 移除
    for which in ("sum_up", "sum_down"):
        block = chinese_b.get(which) or {}
        rows = (block.get("range") or {}).get("rows") or []
        _check(
            f"{which}.range.rows 不含 {new_row}",
            new_row not in rows,
        )

    # -------- 3. 班級數係數 --------
    print("\n=== 6) PATCH /api/schedule/113/class_count/F (new_count=0, 測試歸零) ===")
    # 用 113 某個含 F 欄係數的 subject 觀察；找一個 coef 含 F 的
    before3 = _load()
    target_subj = None
    target_dom = None
    for dom in before3["schedule"]["113"]["day"]["domains"]:
        for s in dom["subjects"]:
            coef = (s.get("weighted_up") or {}).get("coef") or {}
            if "F" in coef and coef["F"] > 0:
                target_subj = s
                target_dom = dom
                break
        if target_subj:
            break
    if not target_subj:
        _check("113 day 有含 F 欄 coef 的 subject", False)
        return

    before_f_coef = target_subj["weighted_up"]["coef"]["F"]
    before_wu = target_subj["weighted_up"]["value"]
    before_sum_up = target_dom["sum_up"]["value"]

    # 改成 0（其他 subject 也會跟著改；會影響多個 domain）
    res = client.patch(
        "/api/schedule/113/class_count/F",
        json={"new_count": 0},
    )
    data = res.get_json()
    _check("status=200", res.status_code == 200, repr(data))
    _check("success=True", data.get("success") is True)
    touched = data.get("touched_subjects") or data.get("touched") or 0
    _check("touched_subjects > 0", touched > 0, f"touched_subjects={touched}")

    after3 = _load()
    t_dom_a = next(
        d for d in after3["schedule"]["113"]["day"]["domains"] if d["domain_id"] == target_dom["domain_id"]
    )
    t_sub_a = next(s for s in t_dom_a["subjects"] if int(s["row"]) == int(target_subj["row"]))
    _check(
        "coef[F] = 0",
        (t_sub_a.get("weighted_up") or {}).get("coef", {}).get("F") == 0,
    )
    # F 欄 coef=0 後 weighted 應該 < before（F 欄 cell 有值才會扣）
    _check(
        "weighted_up 不大於 before",
        t_sub_a["weighted_up"]["value"] <= before_wu,
        f"before={before_wu} after={t_sub_a['weighted_up']['value']}",
    )
    _check(
        "sum_up 不大於 before",
        t_dom_a["sum_up"]["value"] <= before_sum_up,
    )

    # 還原 F 欄係數
    res = client.patch(
        "/api/schedule/113/class_count/F",
        json={"new_count": before_f_coef},
    )
    data = res.get_json()
    _check("還原 F 係數 status=200", res.status_code == 200)

    restored = _load()
    t_dom_r = next(
        d for d in restored["schedule"]["113"]["day"]["domains"] if d["domain_id"] == target_dom["domain_id"]
    )
    t_sub_r = next(s for s in t_dom_r["subjects"] if int(s["row"]) == int(target_subj["row"]))
    _check(
        "coef[F] 還原成原值",
        (t_sub_r.get("weighted_up") or {}).get("coef", {}).get("F") == before_f_coef,
    )
    _check(
        "weighted_up 還原",
        t_sub_r["weighted_up"]["value"] == before_wu,
        f"before={before_wu} restored={t_sub_r['weighted_up']['value']}",
    )

    print("\n全部通過。")


if __name__ == "__main__":
    run()
