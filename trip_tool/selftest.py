# -*- coding: utf-8 -*-
"""自检：python -m trip_tool.selftest

覆盖四件事，任何一项失败都会返回非 0：
  1. 工具契约能被正常调用（含 JSON 字符串入参）
  2. 注入天气后结果可复现，且下雨时室内景点排进雨窗
  3. 数据文件缺失时能降级到内置示例并给出警告
  4. 非法日期被拒
"""
from __future__ import annotations

import sys

from .contract import dispatch, validate


def _hours(precip_hours=(13, 14, 15, 16), thunder=False):
    rows = []
    for h in range(24):
        rain = h in precip_hours
        rows.append({
            "hour": h, "tmp": 26.0 if rain else 28.0,
            "precip": 3.0 if rain else 0.0,
            "precip_prob": 95 if rain else 10,
            "apparent_temp": 33.0 if rain else 28.0,
            "wind10_speed": 2.0, "wind_gusts": 4.0,
            "visibility": 3.0 if rain else 15.0,
            "uv_index": 2.0, "thunder": thunder, "aqi": 45,
        })
    return rows


def t_contract():
    res = dispatch("plan_trip", '{"date":"2026-10-25","max_spots":3}')
    assert res.get("ok"), res
    assert res["days"] and res["days"][0]["stops"], res
    return "plan_trip 可调用（JSON 字符串入参），返回 %d 个景点" % len(res["days"][0]["stops"])


def t_injected():
    req = {"date": "2026-10-25", "max_spots": 4, "weather": {"hours": _hours()}}
    a = dispatch("plan_trip", dict(req))
    b = dispatch("plan_trip", dict(req))
    assert a["ok"] and b["ok"], (a.get("warnings"), b.get("warnings"))
    sig = lambda r: [(s["name"], s["arrive"]) for s in r["days"][0]["stops"]]
    assert sig(a) == sig(b), "同样输入两次结果不一致：%s vs %s" % (sig(a), sig(b))

    rain = set(range(13, 17))
    stops = a["days"][0]["stops"]
    indoor_in_rain = [s["name"] for s in stops
                      if s["type"] == "indoor" and int(s["arrive"][:2]) in rain]
    return ("注入天气可复现；雨窗(13-17)内安排的室内景点：%s"
            % ("、".join(indoor_in_rain) if indoor_in_rain else "无（说明该时段无室内候选）"))


def t_missing_data():
    res = dispatch("plan_trip", {"date": "2026-10-25", "data_dir": r"D:\__no_such_dir__",
                                 "max_spots": 2})
    assert res.get("ok"), res
    assert any("降级" in w for w in res.get("warnings", [])), res.get("warnings")
    assert res["data"]["source"]["kind"] == "bootstrap", res["data"]
    return "数据缺失时降级为内置示例（%d 个景点）" % res["data"]["spots"]


def t_bad_input():
    ok, err = validate({"date": "2026/10/25"})
    assert not ok and "YYYY-MM-DD" in err, err
    res = dispatch("plan_trip", {"date": "not-a-date"})
    assert not res.get("ok"), res
    return "非法日期被拒绝（%s）" % res.get("error")


def main():
    cases = [("工具契约", t_contract), ("注入天气/可复现", t_injected),
             ("数据缺失降级", t_missing_data), ("非法输入", t_bad_input)]
    failed = 0
    for name, fn in cases:
        try:
            print("[PASS] %-12s %s" % (name, fn()))
        except AssertionError as e:
            failed += 1
            print("[FAIL] %-12s %s" % (name, e))
        except Exception as e:
            failed += 1
            print("[ERR ] %-12s %s: %s" % (name, type(e).__name__, e))
    print("\n%d 项通过，%d 项失败" % (len(cases) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
