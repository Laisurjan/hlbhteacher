# -*- coding: utf-8 -*-
"""驗證 Google 登入 + 角色權限：

  - 未登入：頁面 302→/login、API 401
  - 校外 email（@gmail.com）：login 拒收
  - 校內非管理員：可看頁面與讀 API；寫 API 403
  - 三個白名單：可看可寫
"""

from __future__ import annotations

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from app import app  # noqa: E402
from utils import auth as auth_mod  # noqa: E402


def _check(label, cond, detail=""):
    mark = "✅" if cond else "❌"
    print(f"  {mark} {label}" + (f"  {detail}" if detail else ""))
    return cond


def _set_session(client, email, role, name=None):
    with client.session_transaction() as s:
        if email is None:
            s.pop("user_email", None); s.pop("user_role", None); s.pop("user_name", None)
        else:
            s["user_email"] = email
            s["user_role"] = role
            s["user_name"] = name or email.split("@")[0]


def main():
    client = app.test_client()

    print("=== 未登入 ===")
    _set_session(client, None, None)
    r = client.get("/")
    _check("/ → 302", r.status_code == 302, f"status={r.status_code} loc={r.headers.get('Location')}")
    r = client.get("/courses")
    _check("/courses → 302", r.status_code == 302)
    r = client.get("/schedule")
    _check("/schedule → 302", r.status_code == 302)
    r = client.get("/compare")
    _check("/compare → 302", r.status_code == 302)
    r = client.get("/api/summary")
    _check("/api/summary → 401", r.status_code == 401)
    r = client.get("/api/schedule/113")
    _check("/api/schedule/113 → 401", r.status_code == 401)
    r = client.put("/api/schedule/113/chinese_social/cell", json={"row": 5, "col": "F", "value": 3})
    _check("PUT cell 未登入 → 403", r.status_code == 403)
    r = client.get("/login")
    _check("/login 公開 → 200", r.status_code == 200)

    print("\n=== 角色判定（純函數） ===")
    _check("admin: academy@hlbh.hlc.edu.tw",
           auth_mod.role_for_email("academy@hlbh.hlc.edu.tw") == "admin")
    _check("admin: aca_sec@hlbh.hlc.edu.tw",
           auth_mod.role_for_email("aca_sec@hlbh.hlc.edu.tw") == "admin")
    _check("admin: walala@hlbh.hlc.edu.tw",
           auth_mod.role_for_email("walala@hlbh.hlc.edu.tw") == "admin")
    _check("viewer: 任意 @hlbh.hlc.edu.tw",
           auth_mod.role_for_email("teacher123@hlbh.hlc.edu.tw") == "viewer")
    _check("拒絕：@gmail.com",
           auth_mod.role_for_email("someone@gmail.com") is None)
    _check("拒絕：類似但不同（@hlbh.hlc.edu.tw.evil.com）",
           auth_mod.role_for_email("a@hlbh.hlc.edu.tw.evil.com") is None)
    _check("大小寫不敏感",
           auth_mod.role_for_email("Academy@HLBH.HLC.EDU.TW") == "admin")

    print("\n=== viewer 模擬（teacher@hlbh.hlc.edu.tw） ===")
    _set_session(client, "teacher@hlbh.hlc.edu.tw", "viewer", "張老師")
    r = client.get("/")
    _check("/ → 200", r.status_code == 200)
    body = r.get_data(as_text=True)
    _check("頁面顯示「張老師」", "張老師" in body)
    _check("不顯示「(管理員)」標", "(管理員)" not in body)
    r = client.get("/api/summary?year=113")
    _check("/api/summary 200", r.status_code == 200)
    r = client.put("/api/schedule/113/chinese_social/cell", json={"row": 5, "col": "F", "value": 3})
    _check("PUT cell viewer → 403", r.status_code == 403)
    r = client.patch("/api/schedule/113/class_count/F", json={"new_count": 1})
    _check("PATCH class_count viewer → 403", r.status_code == 403)

    print("\n=== admin 模擬（academy@hlbh.hlc.edu.tw） ===")
    _set_session(client, "academy@hlbh.hlc.edu.tw", "admin", "教務處")
    r = client.get("/")
    _check("/ → 200", r.status_code == 200)
    body = r.get_data(as_text=True)
    _check("頁面顯示「教務處」", "教務處" in body)
    _check("顯示「(管理員)」標", "(管理員)" in body)
    r = client.get("/api/me")
    me = r.get_json() or {}
    _check("/api/me 回 admin", (me.get("user") or {}).get("role") == "admin")

    print("\n=== /api/google_login 沒設 GOOGLE_CLIENT_ID → 401 ===")
    os.environ.pop("GOOGLE_CLIENT_ID", None)
    r = client.post("/api/google_login", json={"credential": "fake"})
    _check("status=401", r.status_code == 401)
    _check("含『未設定』訊息", "GOOGLE_CLIENT_ID" in r.get_data(as_text=True))

    print("\n=== logout ===")
    r = client.post("/api/logout")
    _check("logout 200", r.status_code == 200)
    r = client.get("/")
    _check("/ 之後 → 302", r.status_code == 302)


if __name__ == "__main__":
    main()
