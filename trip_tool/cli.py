# -*- coding: utf-8 -*-
"""命令行：python -m trip_tool.cli --date 2026-10-25

不启 Flask，直接跑一次规划，便于调试、写演示脚本、做批量回归。
"""
from __future__ import annotations

import argparse
import json
import sys

from . import planner


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m trip_tool.cli")
    ap.add_argument("--date", default=None, help="出行日期 YYYY-MM-DD，缺省为明天")
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--max-spots", type=int, default=4)
    ap.add_argument("--transport", default="mixed", choices=["walk", "drive", "mixed"])
    ap.add_argument("--end-by", default="20:30")
    ap.add_argument("--start-name", default=None)
    ap.add_argument("--start-lat", type=float, default=None)
    ap.add_argument("--start-lon", type=float, default=None)
    ap.add_argument("--prefer", nargs="*", default=None)
    ap.add_argument("--must", nargs="*", default=None)
    ap.add_argument("--avoid", nargs="*", default=None)
    ap.add_argument("--districts", nargs="*", default=None)
    ap.add_argument("--radius", type=float, default=30)
    ap.add_argument("--suit-min", type=int, default=None)
    ap.add_argument("--rel-band", type=int, default=None)
    ap.add_argument("--data-dir", default=None, help="自定义数据目录（测数据缺失用）")
    ap.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = ap.parse_args(argv)

    req = {"days": args.days, "max_spots": args.max_spots, "transport": args.transport,
           "end_by": args.end_by, "max_radius_km": args.radius}
    if args.date:
        req["date"] = args.date
    if args.prefer:
        req["preferences"] = args.prefer
    if args.must:
        req["must_visit"] = args.must
    if args.avoid:
        req["avoid"] = args.avoid
    if args.districts:
        req["districts"] = args.districts
    if args.suit_min is not None:
        req["suit_min"] = args.suit_min
    if args.rel_band is not None:
        req["rel_band"] = args.rel_band
    if args.data_dir:
        req["data_dir"] = args.data_dir
    start = {}
    if args.start_name:
        start["name"] = args.start_name
    if args.start_lat is not None:
        start["lat"] = args.start_lat
    if args.start_lon is not None:
        start["lon"] = args.start_lon
    if start:
        req["start"] = start

    res = planner.plan(req)
    if args.json:
        json.dump(res, sys.stdout, ensure_ascii=False, indent=2)
        return 0 if res.get("ok") else 1

    print(res.get("summary_text") or res.get("error") or res)
    print("\n数据源: %s ｜ 求解器: %s ｜ 耗时: %s ms"
          % (res.get("data", {}).get("source", {}).get("kind"),
             res.get("solver"), res.get("elapsed_ms")))
    for w in res.get("warnings") or []:
        print("[警告]", w)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
