# trip_tool —— 「输入一个日期，排出武汉游览顺序」的工具

给智能体调用的行程规划工具。**只新增文件，未改动仓库里任何已有文件。**

---

## 一、三种调用方式

```python
# ① 代码里直接调（最简：只要一个日期）
from trip_tool import plan_trip
plan_trip("2026-10-25")            # -> dict，含 days[].stops[] 与 summary_text

# ② 智能体调（OpenAI function-calling）
from trip_tool import TOOLS, dispatch
client.chat.completions.create(model=..., messages=msgs, tools=TOOLS)
result = dispatch(tool_call.function.name, tool_call.function.arguments)

# ③ 命令行
python -m trip_tool.cli --date 2026-10-25 --max-spots 4
```

```bash
# ④ HTTP（不改 run.py，用外部注册）
python app_trip.py                 # -> http://127.0.0.1:5001/api/trip/demo
curl -X POST localhost:5001/api/trip/plan_trip \
     -H 'Content-Type: application/json' -d '{"date":"2026-10-25"}'
```

自检：`python -m trip_tool.selftest`（4 项，断网也能跑）。

---

## 二、输入

**`date` 是唯一必填**，其余都有默认值——模型在信息不全时也敢调。

| 字段 | 默认 | 说明 |
|---|---|---|
| `date` | 今天 | `YYYY-MM-DD` |
| `days` | 1 | 连续几天（1–5） |
| `start` | 洪山广场 09:00 | `{name, lat, lon, time}`，**WGS84** |
| `end_by` | 20:30 | 当天最晚结束 |
| `transport` | mixed | walk / drive / mixed |
| `preferences` | — | 历史人文、湖景、赏花、亲子… |
| `must_visit` / `avoid` | — | 必去 / 排除（id 或中文名） |
| `districts` | — | 限定行政区 |
| `max_spots` | 4 | 一天最多几个景点（1–8） |
| `suit_min` / `rel_band` | 60 / 10 | 调参：对天气有多挑 |
| `weather.hours` | — | 仅测试：注入逐时天气以离线复现 |

## 三、输出

```jsonc
{"ok":true, "elapsed_ms":5146, "city":"武汉",
 "data":{"spots":30,"templates":9,"source":{"kind":"json"}}, "solver":"ortools-tsptw",
 "days":[{"date":"2026-10-21","weekday":"周三",
   "weather":{"source":"open-meteo","precip_total_mm":0,"rain_start":null,"feels_max":18},
   "stops":[{"seq":1,"spot_id":"chuhe_hanjie","name":"楚河汉街","type":"street_semi_outdoor",
             "arrive":"09:12","leave":"11:12","stay_min":120,"suitability":100,
             "weather_at_arrival":{}, "reason":"天气条件良好；街区可边逛边避雨",
             "leg":{"from":"起点","km":2.1,"min":12,"transport":"drive","nav_url":"https://uri.amap.com/..."}}],
   "dropped":[{"spot_id":"wuda","name":"武汉大学","why":"适宜时段 10:00-16:00"}],
   "totals":{"spot_count":4,"travel_km":11.8,"travel_min":46,"end_time":"17:16"}}],
 "warnings":[], "summary_text":"2026-10-21（周三），全天无降水…"}
```

`summary_text` 是给大模型的"人话版"，可直接转述；要画地图再读 `days[].stops`。

---

## 四、数据契约（数据不全也能跑）

工具读 `data/wuhan/` 下三个文件，**任何一个缺失都会降级并给出 warning**，不会崩：

| 文件 | 缺失时的行为 |
|---|---|
| `spots.json` | 降级为内置 8 个示例景点（`datasource._BOOTSTRAP_SPOTS`） |
| `spot_type_templates.json` | 所有景点按"对天气不敏感"处理（70–100 分），排序不再受天气影响 |
| `districts.json` | 气候兜底与行政区筛选失效，其余照常 |

### 景点字段

必须：`id / name / lat / lon / type`（WGS84）

可选：`district / exposure / features.typical_duration_h / open_hours{periods,closed} / best_months / sensitivity_overrides`

### 类型模板（决定"天气怎么影响这个景点"）

```json
{"sensitivity": {"precip": {"weight": 3, "good": "0", "bad": ">=0.5"},
                 "thunder": {"weight": 3, "bad": "true"}}}
```

`weight` 0–3；`good`/`bad` 支持 `">=5"`、`"12-28"`、`"true"`、`"<=3 或 >=33"`。
**只写 bad 时，"未命中 bad" 即视为 good**（否则布尔因子会被误扣分）。

> 新增景点类型 = 加一个模板键；新增景点 = 加一条记录。**不需要改代码。**

---

## 五、预留的扩展接口（`hooks.py`）

| 扩展点 | 换成什么 | 一行代码 |
|---|---|---|
| `spot_source` | 数据库 / 接口 / 别的城市 | `hooks.set_spot_source(obj)` |
| `weather_provider` | 气象局接口、CRA40/GOWFS | `hooks.set_weather_provider(obj)` |
| `scorer` | **训练出来的满意度模型**（把"算法"升级成 AI 的地方） | `hooks.set_scorer(obj)` |
| `matrix_provider` | 自建 OSRM / 高德路径规划 | `hooks.set_matrix_provider(obj)` |
| `solver` | 别的优化器 / 更强的启发式 | `hooks.set_solver(obj)` |
| `clock` | 固定"今天"（回放、测试） | `hooks.set_clock(fn)` |

每个接口的签名都写在对应模块的 docstring 里。

---

## 六、算法（四步）

1. **候选**：半径 / 行政区 / 月份 / 排除项过滤，按"当日最佳适宜度 + 偏好加分"排序，每类型限 2 个（避免一天排四个步行街）
2. **评分**：`100 − Σ(weight × 违规等级)`，阈值全来自模板；无模板的类型按 70–100 的"天气不敏感"处理
3. **时间窗**：阈值 = `max(suit_min, 当日峰值 − rel_band)`，取**连续达标**且评分最高的一段，与开放时间（含 last_entry / 闭馆日）求交；**不跨低谷合并**
4. **排序**：OR-Tools TSPTW（时间维 + 计数维 + 可放弃节点，放弃惩罚 ∝ 适宜度），5 秒内出解；无 ortools 自动退化为贪心

---

## 七、已知限制

- 一天只用一个"最佳连续窗口"（景点分早晚两段开放时只取一段）
- `transport` 未接公交地铁（只有步行/打车/自动）
- AQI 用逐时 PM2.5 近似（与国标 24h 均值口径不同）
- 目前只覆盖武汉（`city` 字段是占位；换城市需准备同名 data 目录）
