"""Open itinerary with disjoint arrival windows and service duration."""
from __future__ import annotations


def windows_for(problem, node):
    value = problem["windows"][node]
    return value if isinstance(value, list) else [value]


class GreedySolver:
    name = "greedy"

    def solve(self, problem):
        left = set(range(1, problem["n"]))
        cur, clock, out = 0, problem["day_start"], []
        while left and len(out) < problem["max_spots"]:
            options = []
            for i in left:
                for lo, hi, fit in windows_for(problem, i):
                    arrive = max(clock + problem["mins"][cur][i], lo)
                    if arrive <= hi and arrive + problem["stay"][i] <= problem["day_end"]:
                        priority = 1000 if i in problem.get("must_nodes", []) else 0
                        options.append((priority + fit - problem["mins"][cur][i] * .3, -arrive, i, arrive))
            if not options:
                break
            _, _, cur, arrive = max(options)
            out.append((cur, arrive))
            clock = arrive + problem["stay"][cur]
            left.remove(cur)
        return out, sorted(left)


class OrtoolsSolver:
    name = "ortools-tsptw"

    def solve(self, problem):
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2
        n, start, end = problem["n"], problem["day_start"], problem["day_end"]
        mgr = pywrapcp.RoutingIndexManager(n + 1, 1, [0], [n])
        route = pywrapcp.RoutingModel(mgr)

        def cost(a, b):
            x, y = mgr.IndexToNode(a), mgr.IndexToNode(b)
            return 0 if y == n else problem["mins"][x][y]

        def duration(a, b):
            x, y = mgr.IndexToNode(a), mgr.IndexToNode(b)
            return problem["stay"][x] + (0 if y == n else problem["mins"][x][y])

        route.SetArcCostEvaluatorOfAllVehicles(route.RegisterTransitCallback(cost))
        route.AddDimension(route.RegisterTransitCallback(duration), end-start, end, False, "Time")
        dim = route.GetDimensionOrDie("Time")
        dim.CumulVar(route.Start(0)).SetRange(start, start)
        dim.CumulVar(route.End(0)).SetRange(start, end)
        route.AddDimension(route.RegisterTransitCallback(lambda a,b: int(0 < mgr.IndexToNode(a) < n)),
                           0, problem["max_spots"], True, "Count")
        for i in range(1, n):
            idx = mgr.NodeToIndex(i)
            windows = sorted(windows_for(problem, i))
            dim.CumulVar(idx).SetRange(windows[0][0], windows[-1][1])
            for a, b in zip(windows, windows[1:]):
                if a[1] + 1 <= b[0] - 1:
                    dim.CumulVar(idx).RemoveInterval(a[1] + 1, b[0] - 1)
            if i not in problem.get("must_nodes", []):
                route.AddDisjunction([idx], 200 + int(max(w[2] for w in windows)) * 5)
            route.AddVariableMinimizedByFinalizer(dim.CumulVar(idx))
        param = pywrapcp.DefaultRoutingSearchParameters()
        param.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
        param.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        param.time_limit.FromMilliseconds(900)
        solution = route.SolveWithParameters(param)
        if not solution:
            return [], list(range(1, n))
        out, idx = [], route.Start(0)
        while not route.IsEnd(idx):
            node = mgr.IndexToNode(idx)
            if node:
                out.append((node, solution.Min(dim.CumulVar(idx))))
            idx = solution.Value(route.NextVar(idx))
        dropped = [i for i in range(1, n) if solution.Value(route.NextVar(mgr.NodeToIndex(i))) == mgr.NodeToIndex(i)]
        return out, dropped


def pick_solver(preferred=None):
    if preferred:
        return preferred
    try:
        import ortools
        return OrtoolsSolver()
    except ImportError:
        return GreedySolver()
