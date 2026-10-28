# 风雨智游 2.1 · 气象驱动文旅工作台

面向武汉游客与小型文旅团队的本地 Web 应用。以真实逐时天气、景点开放时间和路网耗时约束行程，支持天气变化重排、证据解释、DeepSeek 工具问答和可打印行程单。

## 启动

```powershell
.\.venv\Scripts\python.exe serve.py
```

打开 http://127.0.0.1:5000 。上级目录的 `启动.bat` 亦可使用。当前使用 Waitress，仅监听本机，调试模式默认关闭。

首次安装：Python 3.10+，创建 `.venv` 并安装 `requirements.txt`。将 `.env.example` 复制为 `.env`，填写自己的模型密钥。本机凭据已配置，请勿把 `.env` 放入公开代码包。

## 功能

- 文旅工作台 `/`、`/trip`：真实天气曲线、互动地图、自定义地图起点、景点筛选、完整停留约束、路线与导航。
- 数据变化：刷新真实预报并重排，保留原行程对照和变更说明。
- 天气推演：单独标注的人工降雨情景，不能当作真实预报。
- 行程导出：可打印 HTML / 浏览器保存 PDF / 带来源证据的 JSON；当前浏览器恢复上次行程。
- 气象助手：DeepSeek OpenAI 兼容接口，真实 `plan_trip` / `list_spots` 工具调用。
- 保留模块：`/destinations` 攻略、`/route` 多城天气、`/qa` 中英问答、`/science` 研学及四类导出、`/safety` 安全指南。

## 数据与边界

统一天气入口优先使用已获权限并激活的华风爱科。本机已通过真实定位、72 小时逐时预报与天气预警检查，国内预报已核对 `LocalSource.Id=7`。试用为 30 天、500 次/天、5 QPS，具体有效期与延期以控制台为准。注册、免费试用、延期和配置见 [华风爱科接入说明](docs/华风爱科注册申请与接入.md)。

当前华风适配器支持真实预报与明确标注的人工模拟，未开通历史产品；工作台日期范围为今天至后天，实际需有完整停留及转场时段。显式切换 Open-Meteo 后才可使用其历史回放。不会在华风接口失败时偷偷切换天气源，也不合成气候值。路网使用 OSRM，失败时明示距离估算；不是实时拥堵预测。地图由 Leaflet / OpenStreetMap 提供，瓦片需要网络。景观适宜指数为规则分数，不是概率。

未知或低可信度开放时间不自动安排；已更新6个重点场馆的官方常规开放资料，节假日与临时公告仍优先。系统不查询门票库存，不代预约，不提供AQI。武汉具体行程由约束工具校验，其他城市AI行程明确标注为需要核实的建议。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/evaluate_scenarios.py
# 下列会使用真实联网服务和已配置模型
.\.venv\Scripts\python.exe tools/live_check.py
.\.venv\Scripts\python.exe tools/check_additional.py
```

完整交付说明、测试记录与模拟对照见 [docs/交付说明.md](docs/交付说明.md)。

## 关键结构

- `services/live_weather.py`：统一真实天气源、缓存、时间和来源。
- `trip_tool/planner_core.py` / `solver.py` / `opening.py`：停留窗口、约束求解、最终核验。
- `services/travel_api.py`：规划、重排、推演、会话保存、导出与助手接口。
- `templates/workspace.html` / `static/css/workspace.css` / `static/js/workspace.js`：文旅工作台。
- `data/wuhan/spots.json`：景点、开放时间、预约提示与来源。

密钥、服务器端会话和运行缓存均被 Git 忽略。未配置公网运营所需的账户、HTTPS和容量设施，本版本交付范围为本机辅助规划。
