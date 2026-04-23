# -*- coding: utf-8 -*-
"""教師員額兩套基本節數的計算。

faithful to teacher.xlsx 原表：
- AH = 正式教師人數（W..AG 加總）
- AI = 職務加權基本節數 (Σ 人數 × 職務節數)
- AK = 代理教師人數
- 基本節數(導師法) = Excel C 欄公式代入 AH/AI/AK
- 基本節數(職務法) = Excel G 欄公式代入 AH/AI/AK
"""

from __future__ import annotations

import re
from typing import Any


_ROW_SUFFIX = re.compile(r"\b(A[HIK])\d+")


def _strip_row(formula: str) -> str:
    """把 'AH5+AK5' 轉成 'AH+AK'，方便代入變數。"""
    return _ROW_SUFFIX.sub(r"\1", formula)


def _safe_eval(formula: str, env: dict[str, float]) -> float:
    return eval(_strip_row(formula), {"__builtins__": {}}, env)


def compute_ah(positions: dict[str, int], override: int | None = None) -> int:
    """AH = 正式教師總人數；若 Excel 原表硬編碼了數字（例：數學 AH=6），就使用它。"""
    if override is not None:
        return int(override)
    return sum(int(v or 0) for v in positions.values())


def compute_ai(
    positions: dict[str, int],
    position_columns: list[dict],
    adjustment: int = 0,
    override: int | None = None,
) -> int:
    """AI = Σ(職務人數 × 職務節數) + Excel 尾部調整（例：資處 -7）。"""
    if override is not None:
        return int(override)
    total = 0
    for spec in position_columns:
        total += int(positions.get(spec["key"], 0) or 0) * spec["rate"]
    return total + int(adjustment or 0)


def compute_base(
    formula: str | None,
    constant: Any,
    env: dict[str, float],
) -> int | None:
    """套用 Excel 的 C 欄或 G 欄公式；若原檔是硬編碼數字就直接回傳。"""
    if formula:
        result = _safe_eval(formula, env)
        return int(result) if isinstance(result, (int, float)) else None
    if constant is not None:
        try:
            return int(constant)
        except (TypeError, ValueError):
            return None
    return None


MODES = ("strict", "homeroom_all")
_HOMEROOM_RATE = 12   # 全導師(保守)模式：假設全員皆導師 12 節
SUBSTITUTE_TEACHER_RATE = 16   # 含代理計算時，代理比照 AG 專任 16 節


def calc_domain_summary(
    domain_meta: dict,
    year_state: dict,
    position_columns: list[dict],
    mode: str = "strict",
    include_substitute: bool = False,
) -> dict:
    """單一領域 × 單一年度的摘要結果。

    mode:
      - 'strict'        = 現職務計算（寬鬆）。AI 依 positions × 職務節數 + 調整 + override。
      - 'homeroom_all'  = 全導師計算（保守）。AI = AH × 12（不套 override、不套 adjustment）。
    include_substitute: True 時代理一致併入 — AH += AK、AI += AK×16（strict）或
                       (AH+AK)×12（homeroom_all），env.AK 傳入原 AK；這樣 base_homeroom、
                       base_position、avg_overload 都會跟著變。對外回傳的 AH_formal_count /
                       AI_weighted_hours / AK_substitute 仍維持「原始正式教師」語義。
    """
    if mode not in MODES:
        raise ValueError(f"未知 mode: {mode}；可用：{MODES}")

    positions = year_state.get("positions", {})
    sub_count = int(year_state.get("substitute_count", 0) or 0)
    required_day   = int(year_state.get("required_day", 0) or 0)
    required_eve   = int(year_state.get("required_evening", 0) or 0)
    required_total = year_state.get("required_total")
    if required_total is None:
        required_total = year_state.get("required_hours", 0)
    required_total = int(required_total or 0)
    required = required_total  # 向後相容：對外暴露的 required_hours 一律用合計

    ah = compute_ah(positions, override=domain_meta.get("ah_override"))
    if mode == "homeroom_all":
        ai = ah * _HOMEROOM_RATE
    else:
        ai = compute_ai(
            positions,
            position_columns,
            adjustment=domain_meta.get("ai_adjustment", 0),
            override=domain_meta.get("ai_override"),
        )

    extra_sub = sub_count if include_substitute else 0
    # 重點：env.AH 保持原始 ah 不動（因為導師法公式是 (AH+AK)*X，AH 加 AK 會雙重計算）；
    # 代理進場只體現在 env.AK（給導師法用）與 env.AI（給職務法用，加上 AK*16 當專任代理貢獻）。
    if mode == "homeroom_all":
        ai_eff = (ah + extra_sub) * _HOMEROOM_RATE
    else:
        ai_eff = ai + extra_sub * SUBSTITUTE_TEACHER_RATE
    env = {"AH": ah, "AI": ai_eff, "AK": extra_sub}

    base_homeroom = compute_base(
        domain_meta.get("base_homeroom_formula"),
        domain_meta.get("base_homeroom_constant"),
        env,
    )
    base_position = compute_base(
        domain_meta.get("base_position_formula"),
        domain_meta.get("base_position_constant"),
        env,
    )
    future_base = compute_base(
        domain_meta.get("future_base_formula"),
        domain_meta.get("future_base_constant"),
        env,
    )

    teacher_count = ah + extra_sub
    avg_overload_position = None
    if base_position is not None and teacher_count > 0:
        gap = required - base_position
        avg_overload_position = round(gap / teacher_count, 2)

    # Excel 空白格視為 0（例：全民國防無正式教師，C/G 欄為空）
    diff_homeroom = required - (base_homeroom or 0)
    diff_position = required - (base_position or 0)

    return {
        "domain_id":   domain_meta["id"],
        "domain_name": domain_meta["name"],
        "AH_formal_count":    ah,
        "AI_weighted_hours":  ai,
        "AK_substitute":      sub_count,
        "base_homeroom":  base_homeroom,
        "base_position":  base_position,
        "future_base":    future_base,
        "required_hours":   required,
        "required_day":     required_day,
        "required_evening": required_eve,
        "required_total":   required_total,
        "diff_homeroom":  diff_homeroom,
        "diff_position":  diff_position,
        "avg_overload_position": avg_overload_position,
        "formula": {
            "homeroom": domain_meta.get("base_homeroom_formula")
                        or str(domain_meta.get("base_homeroom_constant")),
            "position": domain_meta.get("base_position_formula")
                        or str(domain_meta.get("base_position_constant")),
            "future":   domain_meta.get("future_base_formula") or "",
        },
        "remark": {
            "substitute_note": domain_meta.get("substitute_note", ""),
            "name_list":       domain_meta.get("name_list", ""),
            "remark_person":   domain_meta.get("remark_person", ""),
            "remark_event":    domain_meta.get("remark_event", ""),
            "future_note":     domain_meta.get("future_note", ""),
        },
    }


def calc_summary(
    school_data: dict,
    year: str,
    mode: str = "strict",
    include_substitute: bool = False,
) -> dict:
    if year not in school_data["years"]:
        raise ValueError(f"未知學年度: {year}；可用：{school_data['available_years']}")

    year_data = school_data["years"][year]
    rows = []
    totals = {
        "AH_formal_count": 0, "AK_substitute": 0,
        "base_homeroom": 0, "base_position": 0,
        "required_hours": 0, "required_day": 0, "required_evening": 0, "required_total": 0,
    }

    for meta in school_data["domains"]:
        state = year_data.get(meta["id"], {})
        row = calc_domain_summary(
            meta, state, school_data["position_columns"],
            mode=mode, include_substitute=include_substitute,
        )
        rows.append(row)

        totals["AH_formal_count"] += row["AH_formal_count"] or 0
        totals["AK_substitute"]   += row["AK_substitute"] or 0
        for k in ("base_homeroom", "base_position", "required_hours",
                  "required_day", "required_evening", "required_total"):
            v = row.get(k)
            totals[k] += v if v is not None else 0

    totals["diff_homeroom"] = totals["required_hours"] - totals["base_homeroom"]
    totals["diff_position"] = totals["required_hours"] - totals["base_position"]

    return {
        "year":   year,
        "mode":   mode,
        "include_substitute": include_substitute,
        "rows":   rows,
        "totals": totals,
    }
