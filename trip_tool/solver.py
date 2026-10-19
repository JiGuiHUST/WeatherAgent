# -*- coding: utf-8 -*-
"""顺序求解：带时间窗的开放式车辆路径（TSPTW）。

问题定义（problem 字典）
    n            节点数，0 号是起点
    mins[i][j]   节点间耗时（分钟，整数）
    stay[i]      在第 i 个节点的停留分钟数（0 号为 0）
    windows[i]   第 i 个节点的到达窗口 (lo, hi, peak)，i>=1
    day_start    当天开始（分钟，相对 00:00）
    day_end      当天结束
    max_spots    最多访问几个景点

预留接口
--------
    class MySolver:
        def solve(self, problem) -> list[(node_idx, arrive_min)]
"""
from __future__ import annotations

import logging

logger = logging.getLogger("trip_tool.solver")


class OrtoolsSolver:
    name = "ortools-tsptw"

    def solve(self, problem):
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2

        n = problem["n"]
        mins = problem["mins"]
        stay = problem["stay"]
        windows = problem["windows"]
        day_start = problem["day_start"]
        day_end = problem["day_end"]
        max_spots = problem["max_spots"]

        mgr = pywrapcp.RoutingIndexManager(n, 1, 0)
        rt = pywrapcp.RoutingModel(mgr)
        rt.SetArcCostEvaluatorOfAllVehicles(
            rt.RegisterTransitCallback(lambda f, t: mins[mgr.IndexToNode(f)][mgr.IndexToNode(t)]))

        def transit(f, t):
            a, b = mgr.IndexToNode(f), mgr.IndexToNode(t)
            return mins[a][b] + (stay[a] if a else 0)

        horizon = day_end - day_start
        rt.AddDimension(rt.RegisterTransitCallback(transit), horizon, horizon, False, "Time")
        td = rt.GetDimensionOrDie("Time")
        td.CumulVar(rt.Start(0)).SetRange(0, 0)
        td.CumulVar(rt.End(0)).SetRange(0, horizon)

        # 最多访问 max_spots 个
        rt.AddDimension(rt.RegisterTransitCallback(
            lambda f, t: 1 if mgr.IndexToNode(f) != 0 else 0), 0, max_spots, True, "Count")

        for i in range(1, n):
            idx = mgr.NodeToIndex(i)
            lo, hi, peak = windows[i]
            lo, hi = max(0, lo - day_start), min(horizon, hi - day_start)
            if lo > hi:
                rt.AddDisjunction([idx], 10 ** 6)
                continue
            td.CumulVar(idx).SetRange(lo, hi)
            # 放弃惩罚随适宜度升高：越合适的越不该丢掉
            rt.AddDisjunction([idx], 100 + int(peak) * 4)

        p = pywrapcp.DefaultRoutingSearchParameters()
        p.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        p.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        p.time_limit.FromSeconds(5)
        sol = rt.SolveWithParameters(p)
        if not sol:
            return [], []

        out, idx = [], rt.Start(0)
        while not rt.IsEnd(idx):
            node = mgr.IndexToNode(idx)
            if node != 0:
                out.append((node, day_start + sol.Min(td.CumulVar(idx))))
            idx = sol.Value(rt.NextVar(idx))
        dropped = [i for i in range(1, n)
                   if sol.Value(rt.NextVar(mgr.NodeToIndex(i))) == mgr.NodeToIndex(i)]
        return out, dropped


class GreedySolver:
    """没有 ortools 时的退化实现：每次挑"可行且适宜度最高"的下一站。"""

    name = "greedy"

    def solve(self, problem):
        n = problem["n"]
        mins = problem["mins"]
        stay = problem["stay"]
        windows = problem["windows"]
        day_start = problem["day_start"]
        day_end = problem["day_end"]
        max_spots = problem["max_spots"]

        left = set(range(1, n))
        cur, t, out = 0, day_start, []
        while left and len(out) < max_spots:
            cands = []
            for i in left:
                lo, hi, peak = windows[i]
                arr = max(t + mins[cur][i], lo)
                if arr > hi or arr + stay[i] > day_end:
                    continue
                cands.append((peak, -mins[cur][i], i, arr))
            if not cands:
                break
            cands.sort(reverse=True)
            _, _, i, arr = cands[0]
            out.append((i, arr))
            t = arr + stay[i]
            cur = i
            left.discard(i)
        return out, sorted(left)


def pick_solver(preferred=None):
    """优先用注入的求解器，其次 ortools，最后贪心。"""
    if preferred is not None:
        return preferred
    try:
        import ortools  # noqa: F401
        return OrtoolsSolver()
    except Exception:
        return GreedySolver()
