# -*- coding: utf-8 -*-
"""Phase 2.2 A1 驗證腳本：手動改 cell、建新學年、看效果是否正確。

執行：python scripts/verify_phase_2_2_a1.py
本腳本會：
  1. 備份 data/school_data.json 為 data/school_data.backup.json
  2. 透過 Flask test client 測試 3 支新 API
  3. 結束後還原 school_data.json，避免污染資料
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
BACKUP_PATH = os.path.join(HERE, "data", "school_data.backup.json")


def _load():
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _login(client):
    # 測試用：直接寫 session（不走 /api/login 避免撞 settings hash）
    with client.session_transaction() as sess:
        sess["is_admin"] = True


def _check(label, cond, detail=""):
    mark = "✅" if cond else "❌"
    print(f"  {mark} {label}" + (f"  {detail}" if detail else ""))
    return cond


def run():
    # 備份
    shutil.copy2(DATA_PATH, BACKUP_PATH)
    print(f"備份 → {BACKUP_PATH}")
    try:
        _run_tests()
    finally:
        # 還原
        shutil.move(BACKUP_PATH, DATA_PATH)
        print("\n已還原 data/school_data.json。")


def _run_tests():
    client = app.test_client()

    print("\n=== 1) GET /api/schedule/113 ===")
    res = client.get("/api/schedule/113")
    data = res.get_json()
    _check("status=200", res.status_code == 200, f"status={res.status_code}")
    _check("success=True", data.get("success") is True)
    _check("schedule.day 含 domains", len(data["schedule"]["day"].get("domains", [])) > 0)
    _check("含 domain_names", bool(data.get("domain_names")))

    print("\n=== 2) PUT /api/schedule/113/chinese_social/cell  (未登入→403) ===")
    res = client.put(
        "/api/schedule/113/chinese_social/cell",
        json={"row": 5, "col": "F", "value": 5},
    )
    _check("未登入回 403", res.status_code == 403, f"status={res.status_code}")

    _login(client)

    print("\n=== 3) PUT /api/schedule/113/chinese_social/cell  (F5: 3→5，應 +4 節) ===")
    snap_before = _load()
    before_wu  = snap_before["schedule"]["113"]["day"]["domains"][0]["subjects"][0]["weighted_up"]["value"]
    before_sum = snap_before["schedule"]["113"]["day"]["domains"][0]["sum_up"]["value"]
    before_req = snap_before["years"]["113"]["chinese_social"]["required_day"]

    res = client.put(
        "/api/schedule/113/chinese_social/cell",
        json={"row": 5, "col": "F", "value": 5},
    )
    data = res.get_json()
    _check("status=200", res.status_code == 200, f"status={res.status_code}")
    _check("success=True", data.get("success") is True, repr(data))
    _check(
        "weighted_up 72→76",
        data["weighted_up_new"] == before_wu + 4,
        f"before={before_wu} after={data['weighted_up_new']}",
    )
    _check(
        "sum_up 112→116",
        data["sum_up_new"] == before_sum + 4,
        f"before={before_sum} after={data['sum_up_new']}",
    )
    _check(
        "required_day 103→107",
        data["required_day_new"] == before_req + 4,
        f"before={before_req} after={data['required_day_new']}",
    )

    # 確認檔案真的寫入
    snap_after = _load()
    f5_after = snap_after["schedule"]["113"]["day"]["domains"][0]["subjects"][0]["cells"].get("F")
    _check("cells.F 已寫入 5", f5_after == 5, f"got={f5_after}")

    # /api/summary 驗證首頁會跟著變
    res = client.get("/api/summary?year=113")
    summary = res.get_json()
    cs_row = next(r for r in summary["rows"] if r["domain_id"] == "chinese_social")
    _check(
        "summary.chinese_social.required_day = 107",
        cs_row["required_day"] == before_req + 4,
        f"got={cs_row['required_day']}",
    )

    # 把 F 改回 3（手動測試：blur 時按 tab 等）
    res = client.put(
        "/api/schedule/113/chinese_social/cell",
        json={"row": 5, "col": "F", "value": 3},
    )
    data = res.get_json()
    _check("還原 F5=3", data.get("success") is True and data["required_day_new"] == before_req)

    print("\n=== 4) 建 115 學年（copy_structure_from=114） ===")
    # 先確認 115 尚未存在
    d = _load()
    if "115" in d.get("available_years", []):
        print("  ⚠️ 115 已在 available_years，跳過建立測試")
    else:
        res = client.post("/api/year/115", json={"copy_structure_from": "114"})
        data = res.get_json()
        _check("status=200", res.status_code == 200, f"status={res.status_code}  resp={data}")
        _check("success=True", data.get("success") is True)
        _check("available_years 含 115", "115" in (data.get("available_years") or []))

        d2 = _load()
        day115 = d2["schedule"]["115"]["day"]
        _check("schedule.115.day 有 domains", len(day115.get("domains", [])) > 0)

        # cells 全清空
        all_empty = all(
            (subj.get("cells") == {} or subj.get("cells") is None)
            for dom in day115["domains"]
            for subj in dom.get("subjects", [])
        )
        _check("所有 subject.cells 清空", all_empty)

        # weighted/sum values 全 0
        all_zero_w = all(
            ((subj.get("weighted_up") or {}).get("value", 0) == 0 and
             (subj.get("weighted_down") or {}).get("value", 0) == 0)
            for dom in day115["domains"]
            for subj in dom.get("subjects", [])
        )
        _check("所有 weighted_up/down value = 0", all_zero_w)
        all_zero_s = all(
            ((dom.get("sum_up") or {}).get("value", 0) == 0 and
             (dom.get("sum_down") or {}).get("value", 0) == 0)
            for dom in day115["domains"]
        )
        _check("所有 sum_up/down value = 0", all_zero_s)

        # /api/summary?year=115 全 0
        res = client.get("/api/summary?year=115")
        summary = res.get_json()
        totals = summary.get("totals") or {}
        _check("summary 115.totals.required_day = 0",  totals.get("required_day") == 0)
        _check("summary 115.totals.required_evening = 0", totals.get("required_evening") == 0)
        _check("summary 115.totals.required_total = 0", totals.get("required_total") == 0)
        # base_position 受 top-level domains 常數影響（例 chinese_social AI+26），非 0 是正常的


if __name__ == "__main__":
    run()
