# 新闻联播 Ontology — Palantir 风格语义层

《新闻联播》文字版的完整 Ontology 落地项目。两阶段交付：Phase 1 数据基础层（抓取→SQLite→AI增强→仪表板） + Phase 2 事件引擎（事件检测→生命周期→AI报告→知识图谱）。

**在线仪表板**: https://1998x-stack.github.io/xinwenlianbo-ontology/visualize/index.html  
**知识图谱**: https://1998x-stack.github.io/xinwenlianbo-ontology/visualize/graph.html  
**代码仓库**: https://github.com/1998x-stack/xinwenlianbo-ontology

---

## 项目结构

```
xinwenlianbo/
├── README.md
│
├── scraper/                          ← 第一阶段：网站抓取
│   ├── config.py         URL、请求头、输出路径
│   ├── scraper.py        requests + BeautifulSoup（cn.govopendata.com）
│   ├── main.py           抓取编排（支持 --days N）
│   └── output/           抓取产出（YYYYMMDD.md，不进 git）
│
├── db/                               ← 第二阶段：数据库 + AI + 事件引擎
│   ├── schema.sql         Phase 1 DDL（4 核心表 + 3 联结表 + 14 索引）
│   ├── schema_v2.sql      Phase 2 迁移（NewsEvent + 4 联结表）
│   ├── import_data.py     Markdown → SQLite 导入（幂等，INSERT OR IGNORE）
│   ├── queries.py         9 个查询函数（6 Phase 1 + 3 Phase 2 事件查询）
│   ├── ai_client.py       DeepSeek API 封装（重试 + 指数退避）
│   ├── enhance.py         AI 增强管道（并发 ThreadPoolExecutor，pypinyin slug）
│   ├── event_engine.py    事件引擎（聚类检测、热度评分、生命周期、AI 报告）
│   ├── main.py            CLI 入口（13 个命令）
│   ├── export_jsonl.py    导出 JSONL + JSON（news/topics/dates/events）
│   └── export_graph.py    知识图谱导出（节点 + 边 + PageRank）
│
├── visualize/                        ← 第三阶段：前端可视化
│   ├── index.html         交互式仪表板（事件 Gantt + 时间线 + 主题 + 人物榜）
│   └── graph.html         知识图谱（D3.js 力导向图，PageRank 节点缩放）
│
└── data/                             ← 导出数据（GitHub Pages 加载）
    ├── news_items.jsonl    386 行新闻记录（~500 KB）
    ├── topics.json          19 主题（含 category 分类）
    ├── dates.json           29 天统计
    ├── events.json          55 事件（AI 命名 + 摘要 + 热度）
    └── graph.json           175 节点 · 533 边（含 PageRank 分数）
```

---

## 当前数据状态

| 实体 | 数量 |
|------|------|
| 新闻条目 | 386 条（29 天：2026-05-12 → 2026-06-09） |
| AI 增强覆盖率 | 376/386 (97%) |
| 人物 | 166 位（496 条链接，37 位有机构归属） |
| 机构 | 512 个（875 条链接） |
| 主题 | 19 个（全部含 category 分类，1056 条链接） |
| 事件 | 55 个（2 集群事件 + 53 单条事件） |
| 知识图谱 | 175 节点 · 533 边 · PageRank 评分 |
| 政策信号 | 318 条 |

---

## 快速开始

```bash
cd xinwenlianbo
pip install pypinyin requests beautifulsoup4

# 1. 抓取数据
cd scraper && python main.py --days 30

# 2. 初始化数据库 + 导入
cd ../db && python main.py setup

# 3. 查看统计
python main.py stats

# 4. AI 增强（需要 DEEPSEEK_API_KEY）
export DEEPSEEK_API_KEY="sk-..."
python main.py enhance --concurrency 6

# 5. 事件检测（Phase 2，需要 DEEPSEEK_API_KEY）
python main.py detect-events

# 6. 导出全部数据 + 知识图谱
python export_jsonl.py
python export_graph.py

# 7. 启动可视化
cd .. && python3 -m http.server 8080
# 仪表板: http://localhost:8080/visualize/index.html
# 知识图谱: http://localhost:8080/visualize/graph.html
```

---

## 核心概念

### Ontology 模型

| 层 | Phase 1 | Phase 2 新增 |
|----|---------|-------------|
| **Object Types** | NewsItem, Person, Organization, Topic | **NewsEvent**（事件） |
| **Link Types** | mentionsPerson, mentionsOrg, about | **coversEvent** (many:many), **relatedTo** (Event↔Event), **involvesPerson**, **involvesOrg** |
| **Functions** | 全文搜索、人物画像、主题演化、日期概览、主题网络、人物对比 | 事件检测(clustering)、热度评分、重要性分类、生命周期状态机、AI 事件报告 |

### 事件生命周期状态机

```
[新闻聚类检测] → emerging → developing → peak → declining → resolved → archived
                    │            │          │         │
                    └────────────┴──────────┴─────────┘
                           (30天无报道 → archived)
```

### 数据流

```
cn.govopendata.com/xinwenlianbo/YYYYMMDD/
  │  scraper/  requests + BeautifulSoup
  │  <h2 class="content-heading"> 标题，<div class="content-body"> 正文
  ▼
Markdown 文件（29 天，386 条新闻）
  │  db/import_data.py  news_id = SHA256(broadcast_date + order)
  ▼
SQLite 数据库（13 表，~2.4 MB）
  │  db/queries.py       9 个查询函数
  │  db/enhance.py       AI 增强（DeepSeek Flash，ThreadPoolExecutor）
  │  db/event_engine.py  事件检测 + 热度 + 状态 + AI 报告
  ▼
JSONL + JSON 导出（386 行 + 55 事件 + 175 节点图谱）
  │  visualize/index.html   仪表板 fetch() 加载
  │  visualize/graph.html   图谱 D3.js force simulation
  ▼
GitHub Pages 静态托管
```

---

## 解析示例

### 抓取 → 结构化

```html
输入: https://cn.govopendata.com/xinwenlianbo/20260609/

<article class="content-section">
  <h2 class="content-heading">习近平出席金正恩举行的欢迎宴会</h2>
  <div class="content-body">
    <p>当地时间6月8日晚，中共中央总书记、国家主席习近平...</p>
  </div>
</article>
```

↓ `scraper.py` 解析 ↓

```json
{
  "news_id": "a1b2c3d4e5f67890",
  "title": "习近平出席金正恩举行的欢迎宴会",
  "full_text": "当地时间6月8日晚，中共中央总书记...",
  "broadcast_date": "2026-06-09",
  "order_in_broadcast": 1
}
```

### AI 增强

↓ `enhance.py` (DeepSeek Flash) ↓

```json
{
  "summary": "习近平对朝鲜进行国事访问，与金正恩举行会谈并出席欢迎宴会，双方就深化中朝关系达成重要共识。",
  "keywords": ["习近平", "金正恩", "中朝关系", "国事访问", "平壤"],
  "topics": [{"name": "外交", "relevance": 1.0}, {"name": "国际关系", "relevance": 0.9}],
  "entities": {
    "people": [{"name": "习近平", "title": "中共中央总书记、国家主席"}],
    "organizations": [{"name": "朝鲜劳动党", "type": "government"}]
  },
  "policy_signals": [{"signal": "中朝关系站在新的历史起点上", "type": "表述转变"}]
}
```

### 事件检测

↓ `event_engine.py` （主题聚类 + 时间窗口 + AI 命名）↓

```json
{
  "event_id": "082effe4...",
  "name": "习近平2026年朝鲜国事访问",
  "type": "diplomatic",
  "importance": "critical",
  "status": "peak",
  "heat_score": 87.8,
  "first_date": "2026-06-07",
  "last_date": "2026-06-09",
  "news_count": 15,
  "summary": "2026年6月7日至9日，习近平对朝鲜进行国事访问，与金正恩举行会谈..."
}
```

---

## CLI 命令参考

```bash
cd xinwenlianbo/db

# === 数据库管理 ===
python main.py setup                       # 创建数据库 + 导入数据
python main.py setup --force-reimport      # 强制重新导入
python main.py stats                       # 统计概览

# === Phase 1 查询 ===
python main.py search "习近平"              # 全文搜索（标题 + 正文 + 摘要）
python main.py person "习近平"              # 人物画像（频次 + 主题分布 + 机构）
python main.py topic "外交"                 # 主题演化时间线
python main.py date "2026-06-09"           # 单日内容概览（含人物、机构）
python main.py network "外交"               # 主题共现网络

# === AI 增强 ===
python main.py enhance                     # 批量增强（并发 3 线程，幂等）
python main.py enhance --limit 10          # 只处理 10 条
python main.py enhance --concurrency 6     # 6 线程并发
python main.py enhance --dry-run           # 预览待处理条目
python main.py analyze-topic "外交"         # AI 主题演化叙事分析

# === Phase 2 事件引擎 ===
python main.py detect-events               # 运行事件检测管道（聚类+AI命名+评分+导出）
python main.py events                      # 列出所有事件（按热度排序）
python main.py events --status=emerging    # 筛选新兴事件
python main.py events --importance=critical # 筛选重大事件
python main.py event <event_id>            # 事件详情（时间线+关键人物+关联事件）
python main.py event-report <event_id>     # AI 生成事件分析报告

# === 导出 ===
python export_jsonl.py                     # 导出 JSONL + JSON（4 个文件）
python export_graph.py                     # 导出知识图谱（graph.json, 含 PageRank）
```

---

## 仪表板

`visualize/index.html` — 单文件交互式数据浏览器：

**Phase 1 面板**:
- 搜索框：标题、摘要、关键词、人物（Ctrl+K 聚焦）
- 时间线图：每日新闻数量柱状图（点击筛选日期）
- 主题网格：Top 15 主题气泡（点击筛选）
- 新闻列表：可滚动卡片，展示人物、关键词、AI 摘要
- 人物榜：Top 15 高频人物（点击筛选）
- 政策信号面板：检测到的 318 条政策信号
- 详情弹窗：AI 摘要、关键词、主题、人物、机构、政策信号、正文预览

**Phase 2 面板**:
- 事件 Gantt 时间线：Top 10 事件，颜色编码重要性（critical=红, major=橙, notable=蓝, routine=灰）
- 事件详情弹窗：AI 事件摘要、完整时间线、关键人物
- 新兴事件列表：状态为 emerging/developing 的事件

**交互**: 全部联动 — 点击任意图表元素全局筛选，URL hash 状态可分享

## 知识图谱

`visualize/graph.html` — D3.js 力导向图：

- **175 节点**: 100 新闻(蓝) · 30 人物(红) · 30 机构(绿) · 15 主题(橙)
- **533 条边**: mentions（新闻→人物/机构）· about（新闻→主题）· co_occur（人物共现）
- **PageRank 节点缩放**: 节点半径 = baseSize + PageRank × 20，中心节点更大
- **交互**: 拖拽节点、滚轮缩放、按类型筛选、悬浮提示
- **人物共现**: 同一新闻中出现 ≥2 次的人物对建立红色连线

---

## 技术选型与设计决策

| 决策 | 理由 |
|------|------|
| **requests + BeautifulSoup** | 页面是 SSR — `<main class="article-content">` 中有完整文本，无需浏览器渲染 |
| **SQLite** | 零配置、单文件 2.4 MB、CJK LIKE 无需分词器、INSERT OR IGNORE 幂等导入 |
| **news_id = SHA256(date + order)** | 播出顺序比标题更稳定，重抓时 ID 不变 |
| **pypinyin 自动 slug** | `lazy_pinyin("高质量发展")` → `gao-zhi-liang-fa-zhan`，无需硬编码映射 |
| **ThreadPoolExecutor 并发增强** | 6 线程并行调用 DeepSeek API，速度提升 ~6x |
| **预导出** | `enhance_all()` 开始前先 export，Pages 始终有完整数据 |
| **反规范化 JSONL** | 每条记录自包含 people/organizations/topics，前端零查询 |
| **单文件 HTML** | 无框架依赖，fetch() 加载静态 JSON，GitHub Pages 直接托管 |
| **D3.js CDN 加载** | 知识图谱页面唯一外部依赖，主流 CDN 稳定可靠 |
| **无向图 PageRank** | 边双向流动，避免二分图中 news 节点入度为 0 的问题 |
| **主题聚类 + 孤立回退** | 泛主题（经济/国际关系/社会）排除 + 未聚类条目自动创建单条事件 |
| **topic.category 硬编码映射** | AI 不输出 category，19 行映射表解决，避免增加 prompt 复杂度 |

## 设计决策记录

### 为什么 topic.category 用硬编码映射而非让 AI 输出？

AI prompt 已经要求模型从 18 个主题中选择 + 输出 relevance + rationale。再加 category 会增加 prompt 复杂度，且 category 是固定的（经济↔Economy，外交↔Politics），不需要 AI 判断。硬编码 19 行映射更简单、确定性更高。

### 为什么事件聚类排除泛主题（经济/国际关系/社会）？

"经济"标签出现在 169/386 条新闻中，"国际关系"出现在 136 条。如果所有共享这些主题的条目都连接，整个图会坍缩成一个巨型集群。排除 Top 3 泛主题后，聚类基于更具体的主题（如"外交""军事""科技"），产生有意义的 55 个事件。

### 为什么 PageRank 用无向图？

原始有向图所有边从 news → entity，news 节点入度为 0。PageRank 在这种图上退化为出度计数。改为无向图（边双向流动）后，中心性在 news ↔ entity 之间双向传播，news 节点获得有意义的分数。

---

## 数据源

- **网站**: [cn.govopendata.com/xinwenlianbo](https://cn.govopendata.com/xinwenlianbo)
- **覆盖范围**: 2007 年至今的每日新闻联播文字版
- **更新频率**: 每日晚间 ~19:30 CST 后可用
- **页面结构**: 服务端渲染（SSR），`<article class="content-section">` 内含 `<h2 class="content-heading">` 标题 + `<div class="content-body">` 正文

## 扩展指南

### 扩展到 90 天

```bash
cd scraper && python main.py --days 90
cd ../db && python main.py setup --force-reimport
python main.py enhance --concurrency 6
python main.py detect-events
python export_jsonl.py && python export_graph.py
cd .. && git add data/ && git commit -m "data: expand to 90 days" && git push
```

### 换用其他 LLM

修改 `db/ai_client.py` 中的 `DEEPSEEK_BASE` 和 `DEFAULT_MODEL`，接口兼容 OpenAI 格式：

```python
from ai_client import chat
result = chat(prompt, model="gpt-4o", base="https://api.openai.com")
```

### 自定义主题分类

编辑 `db/enhance.py` 中的 `TOPICS` 列表和 `TOPIC_CATEGORIES` 映射，重新运行 `python main.py enhance` 即可。当前 19 个主题：政治(Economy)、经济(Economy)、外交(Politics)、军事(Military)、科技(Technology)、社会(Society)、文化(Culture)、生态(Environment)、国际关系(Politics)、中美关系(Politics)、一带一路(Economy)、乡村振兴(Economy)、高质量发展(Economy)、改革开放(Economy)、党的建设(Politics)、法治建设(Law)、民生保障(Society)、国防安全(Military)、基础设施(Economy)。

### 调整事件聚类阈值

编辑 `db/event_engine.py` 中 `run_event_pipeline()` 的参数：
- `time_window_days`：时间窗口（默认 5 天）
- `min_items`：最小条目数（默认 2）
- `concurrency`：AI 并发数（默认 3）
- `exclude_top_topics`：排除的泛主题数（`detect_events()` 内部，默认 3）

## 相关文档

- `docs/superpowers/specs/2026-06-10-xinwenlianbo-phase1-design.md` — Phase 1 设计文档
- `docs/superpowers/specs/2026-06-10-xinwenlianbo-phase2-design.md` — Phase 2 事件引擎设计
- `docs/superpowers/specs/2026-06-10-xinwenlianbo-phase3-design.md` — Phase 3 自动化运营设计
- `docs/superpowers/plans/2026-06-10-xinwenlianbo-phase1.md` — Phase 1 实施计划
- `docs/superpowers/plans/2026-06-10-xinwenlianbo-phase2.md` — Phase 2 实施计划
- `docs/xinwenlianbo-ontology.md` — 原始企业级 Ontology 设计
