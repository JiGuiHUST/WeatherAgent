# 风雨智游气象旅行攻略系统 V1.0

面向东南亚出境旅行者的气象驱控行程规划 Web 应用。将逐时气象预报、景观观赏概率、跨境行程时间线、AI 智能问答与双语研学素材有机结合，帮助用户在出发前全面掌握沿途天气，科学安排行程。

---

## 功能模块

| 模块 | 路由 | 说明 |
|------|------|------|
| 目的地气候规划 | `/` `/strategy` | 二级菜单选择目的地（国内 · 武汉 / 国外 10 国 33 城），生成单城气象旅游攻略，含景点推荐、逐时天气、舒适度评分 |
| 行程规划工具 | `/trip` `/api/trip/*` | 输入日期，按当天逐时天气排出武汉景点时间线；开放时间 + 交通耗时 + TSPTW 求解，可供智能体以 function-calling 调用 |
| 行程气象助手 | `/route` | 输入多城市途经点与停留时间（国内/国外分组勾选），生成逐时气象时间线、景点级预报卡片、景观概率预判及 AI 推荐行程 |
| 气象问答 | `/qa` | 中英双语自然语言问答，结合实时气象数据与大模型生成结构化回答 |
| 气象研学课堂 | `/science` | 沿线伴随式实景科普，含对流雨示意图、研学手册、观测记录表，支持中英双语素材导出 |
| 出行安全指南 | `/safety` | 东南亚各国应急电话、特色活动风险提示、出行准备清单 |
| 语言设置 | 全局 | 一键切换中/英文，所有页面与数据均支持双语展示 |

---

## 技术栈

- **后端**：Python 3.10+ / Flask 2.3+
- **模板引擎**：Jinja2
- **前端**：Bootstrap 5（响应式布局）+ 原生 JavaScript
- **数据计算**：numpy（气象要素计算与景观概率建模）
- **图表绘制**：matplotlib（对流雨示意图等科普素材）
- **行程求解**：OR-Tools（带时间窗的旅行商问题 TSPTW；未安装时退化为贪心排序）
- **大语言模型**：Qwen3-14B（通过 OpenAI 兼容接口调用，用于气象问答与行程规划）
- **数据存储**：JSON 文件（零数据库依赖）
- **国际化**：自研 i18n 翻译键值表（`utils/i18n.py`）

---

## 目录结构

```
ai_travel_weather/
├── run.py                      # Flask 启动入口与路由定义
├── config.py                  # 全局配置（气象接口、LLM、路径常量）
├── requirements.txt            # Python 依赖
├── .env                        # 环境变量（LLM 凭据，需自行创建）
│
├── services/                   # 业务服务层
│   ├── travel_engine.py        # 单城攻略生成
│   ├── destinations.py         # 目的地二级菜单（国内 / 国外分组）
│   ├── forecast_service.py     # 行程逐时预报构建
│   ├── landscape_engine.py     # 景观概率预测
│   ├── itinerary_planner.py    # AI 行程规划
│   ├── qa_engine.py            # 气象问答引擎（含行程工具意图路由）
│   ├── science_engine.py       # 实景科普与素材导出
│   ├── weather_api.py          # 外部气象接口封装
│   ├── llm_client.py           # 大模型客户端（支持 function-calling）
│   └── plot_service.py         # 图表绘制
│
├── utils/                     # 工具层
│   ├── common.py              # 表单校验、时间解析、日期工具
│   ├── i18n.py                # 中英文翻译键值表
│   ├── visual.py              # 天气图标、舒适度图标、概率着色
│   └── cache.py               # SimpleCache TTL 缓存
│
├── templates/                 # Jinja2 页面模板
│   ├── base.html              # 基础布局（导航栏、页脚）
│   ├── index.html             # 目的地气候规划（国内/国外二级菜单）
│   ├── strategy.html          # 单城攻略详情
│   ├── route.html             # 行程气象助手（城市按国内/国外分组）
│   ├── trip.html              # 行程规划工具（/trip）
│   ├── qa.html                # 气象问答
│   ├── science.html           # 气象研学课堂
│   ├── safety.html            # 出行安全指南
│   ├── _itin_cards.html       # 行程卡片片段
│   └── error.html             # 错误页
│
├── static/                    # 静态资源
│   ├── css/                   # 样式文件
│   ├── js/                    # 脚本文件（dest_picker.js / trip.js 等）
│   ├── weather_img/           # 天气图标素材
│   └── *.png                  # 页面截图
│
├── tools/                     # 数据维护脚本
│   └── integrate_wuhan_data.py  # 把武汉 13 区县 / 30 景点并入主数据
│
├── trip_tool/                 # 行程规划工具（蓝本 /api/trip/*，可独立测试）
│
└── data/                      # 数据文件
    ├── city_bbox.json          # 城市坐标与边界（国内武汉 + 东南亚10国33城）
    ├── travel_spots.json       # 景点信息（名称、坐标、分类）
    ├── landscapes.json         # 景观类型与气象适配模型
    ├── knowledge_base.json     # 科研知识点库
    ├── qa_knowledge.json       # 问答知识库
    └── wuhan/                  # 武汉 13 区县、30 景点、开放时间与气象敏感模板
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

在项目根目录创建 `.env` 文件：

```env
OPENAI_API_KEY=your_llm_api_key
OPENAI_BASE_URL=http://your-llm-endpoint/v1
LLM_MODEL=Qwen3-14B
```

> 若不配置 LLM 凭据，气象问答与 AI 行程规划功能将不可用，其余模块正常运行。

### 3. 启动服务

```bash
python run.py
```

浏览器访问 `http://localhost:5000`。

---

## 目的地二级菜单

首页「目的地」是一个两级菜单（`services/destinations.py` + `static/js/dest_picker.js`）：

- **一级**：国内 / 国外 → 国家（国内按省级行政区聚合，如「中国 · 湖北」）
- **二级**：该国家下的城市（国外 10 国 33 城；国内为武汉）
- 行程页 `/route` 的城市勾选同样按「国内 · 中国 · 湖北 / 国外 · 越南 …」分组

国内数据由 `tools/integrate_wuhan_data.py` 从同事提供的 `data/wuhan/` 生成：
13 个区县的 bbox 并集作为城市边界，气候取 13 区县均值，景点按气象敏感类型映射到
「文化地标 / 城市海滩 / 亲子乐园」等标准卡片区。脚本可重复执行（已存在则跳过）。

---

## 行程规划工具（trip_tool）的接入方式

| 入口 | 说明 |
|------|------|
| `/trip` | 站点页面：选日期 + 最多景点数 + 交通方式，异步调用 `/api/trip/plan_trip` 渲染时间线 |
| `/api/trip/*` | `trip_tool.server.bp` 蓝本，在 `run.py` 的 `create_app()` 中 `register_blueprint` 挂载 |
| 智能体问答 | `services/llm_client.ask_with_tools()` 把 `trip_tool.TOOLS` 作为 function-calling 工具传给大模型；`services/qa_engine.py` 另有确定性意图路由（问句含「武汉/黄鹤楼/东湖…」+「行程/规划/一日游…」时直接调用工具，无需大模型） |

工具内部流程：Open-Meteo 逐时天气 → 景点气象敏感度评分 → 时间窗 × 开放时间求交 → OR-Tools TSPTW 排序。
`ortools` 未安装时自动退化为贪心排序（仍可出结果，排序质量下降）。

---

## 数据说明

| 文件 | 内容 | 规模 |
|------|------|------|
| `city_bbox.json` | 城市中英文名、国家、经纬度、边界框 | 武汉 + 东南亚10国33城 |
| `travel_spots.json` | 景点名称、坐标、分类标签、推荐时长 | 200+ 景点 |
| `data/wuhan/` | 武汉 13 区县、30 景点、开放时间、气象敏感模板 | 30 景点 / 9 类模板 |
| `landscapes.json` | 景观类型、气象适配条件、评分权重 | 30+ 景观类型 |
| `knowledge_base.json` | 气象科普知识点（中英双语） | — |
| `qa_knowledge.json` | 常见问答模板与关键词映射 | — |

---

## 气象数据来源

系统通过 `services/weather_api.py` 调用外部气象接口，获取指定经纬度的逐小时预报数据，包括温度、降水、云量、风力、能见度等要素。接口地址与 Token 在 `config.py` 中配置。

调用结果通过 `utils/cache.py` 的 SimpleCache 进行 TTL 缓存（默认 600 秒），避免重复请求。

---

## 景观概率模型

`services/landscape_engine.py` 基于 numpy 对每种景观类型计算气象适配度评分，综合考虑以下因子：

- 云量（影响日出日落、星空观赏）
- 降水概率（影响户外活动）
- 能见度（影响观景、摄影）
- 风力等级（影响海上活动、高空观景）
- 温度舒适度

评分结果以概率等级（高/中/低）和颜色标注呈现，帮助用户判断最佳观赏时段。

---

## 国际化

`utils/i18n.py` 维护中英双语翻译键值表，通过 `translate(key, lang)` 函数统一取值。页面语言通过 URL 参数 `?lang=en` 或导航栏语言按钮切换，Session 记忆用户偏好。

所有界面文案、页面标题、导航菜单、安全指南内容均支持双语。

---

## 许可证

本项目为私有软件，版权归著作权人所有。
