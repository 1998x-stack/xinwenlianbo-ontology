# 新闻联播 Ontology — Palantir 风格语义层

《新闻联播》文字版的完整 Ontology 落地项目。从网站抓取 → SQLite 数据库 → AI 增强分析 → 交互式可视化 → GitHub Pages，全链路实现。

**在线仪表板**: https://1998x-stack.github.io/xinwenlianbo-ontology/visualize/index.html

## 项目结构

```
xinwenlianbo/
├── README.md
│
├── scraper/                          ← 第一阶段：网站抓取
│   ├── config.py         URL、请求头、输出路径
│   ├── scraper.py        requests + BeautifulSoup 抓取（cn.govopendata.com）
│   ├── main.py           抓取编排（支持 --days N）
│   └── output/           抓取产出（YYYYMMDD.md，不进 git）
│
├── db/                               ← 第二阶段：数据库 + AI + 查询
│   ├── schema.sql         DDL（4 核心表 + 3 联结表 + 14 索引）
│   ├── import_data.py     Markdown → SQLite 导入（幂等，INSERT OR IGNORE）
│   ├── queries.py         6 个分析查询函数
│   ├── ai_client.py       DeepSeek API 封装（含重试逻辑）
│   ├── enhance.py         AI 增强管道（并发处理，pypinyin 主题 slug）
│   ├── main.py            CLI 入口（9 个命令）
│   └── export_jsonl.py    数据库 → JSONL/JSON 导出
│
├── visualize/                        ← 第三阶段：前端可视化
│   └── index.html         交互式仪表板（单文件，纯前端，~310 行）
│
└── data/                             ← 导出数据（供仪表板 + GitHub Pages 加载）
    ├── news_items.jsonl    每条新闻一行 JSON（~500 KB / 30 天）
    ├── topics.json          主题汇总
    └── dates.json           每日统计
```

## 快速开始

```bash
cd xinwenlianbo
pip install pypinyin requests beautifulsoup4

# 1. 抓取 30 天数据
cd scraper && python main.py --days 30

# 2. 初始化数据库 + 导入
cd ../db && python main.py setup

# 3. 查看统计
python main.py stats

# 4. AI 增强（需要 DeepSeek API Key）
export DEEPSEEK_API_KEY="sk-..."
python main.py enhance --limit 5       # 先试 5 条
python main.py enhance --concurrency 3 # 全量并发处理

# 5. 导出 + 启动可视化
python export_jsonl.py
cd .. && python3 -m http.server 8080
# 浏览器打开 http://localhost:8080/visualize/index.html
```

## 核心概念

### Ontology 模型

| 层 | 内容 |
|----|------|
| **Object Types (名词)** | NewsItem（新闻条目）、Person（人物）、Organization（机构）、Topic（主题） |
| **Link Types (关系)** | mentionsPerson、mentionsOrg、about（多对多，junction table） |
| **Functions (动词)** | 全文搜索、人物画像、主题演化、日期概览、主题网络、人物对比 |

### 数据流

```
cn.govopendata.com/xinwenlianbo/YYYYMMDD/
  │  scraper/  requests + BeautifulSoup（<h2> 标题 + <div.content-body> 正文）
  ▼
Markdown 文件（29 天，~386 条新闻）
  │  db/import_data.py  解析 ## 标题 + 正文 → news_id = SHA256(date + order)
  ▼
SQLite 数据库（4 表，~3 MB）
  │  db/queries.py       6 个分析查询
  │  db/enhance.py       AI 增强（DeepSeek Flash，concurrency=3）
  ▼
JSONL 导出（386 行自包含记录）
  │  visualize/index.html   fetch() 加载
  ▼
交互式仪表板（搜索 / 时间线 / 主题网络 / 人物榜 / 政策信号）
```

## 解析示例

```
输入: scraper/output/20260609.md

<article class="content-section">
  <h2 class="content-heading">习近平出席金正恩举行的欢迎宴会</h2>
  <div class="content-body">
    <p>当地时间6月8日晚，中共中央总书记、国家主席习近平...</p>
  </div>
</article>
```

↓ 解析 ↓

```json
{
  "news_id": "a1b2c3d4e5f67890",
  "title": "习近平出席金正恩举行的欢迎宴会",
  "full_text": "当地时间6月8日晚，中共中央总书记...",
  "broadcast_date": "2026-06-09",
  "order_in_broadcast": 1
}
```

↓ AI 增强 ↓

```json
{
  "summary": "习近平对朝鲜进行国事访问，与金正恩举行会谈并出席欢迎宴会，双方就深化中朝关系达成重要共识。",
  "keywords": ["习近平", "金正恩", "中朝关系", "国事访问", "平壤"],
  "topics": ["外交", "国际关系"],
  "entities": {
    "people": [{"name": "习近平", "title": "中共中央总书记、国家主席"}],
    "organizations": [{"name": "朝鲜劳动党", "type": "government"}]
  },
  "policy_signals": [{"signal": "中朝关系站在新的历史起点上", "type": "表述转变"}]
}
```

## CLI 命令参考

```bash
cd xinwenlianbo/db

# 数据库管理
python main.py setup                       # 创建数据库 + 导入数据
python main.py setup --force-reimport      # 强制重新导入
python main.py stats                       # 统计概览

# 查询
python main.py search "习近平"              # 全文搜索（标题 + 正文）
python main.py person "习近平"              # 人物画像（出现频次 + 主题分布 + 机构）
python main.py topic "外交"                 # 主题演化时间线
python main.py date "2026-06-09"           # 单日内容概览
python main.py network "外交"               # 主题共现网络

# AI 增强（需要 DEEPSEEK_API_KEY）
python main.py enhance                     # 批量增强（并发 3 线程）
python main.py enhance --limit 10          # 只处理 10 条
python main.py enhance --concurrency 5     # 5 线程并发
python main.py enhance --dry-run           # 预览待处理条目（不调 API）
python main.py analyze-topic "外交"         # AI 主题演化叙事分析

# 导出与可视化
python export_jsonl.py                     # 导出 JSONL + JSON
```

## 仪表板

`visualize/index.html` 是一个单文件交互式数据浏览器：

- **搜索框**：按标题、摘要、关键词、人物搜索（Ctrl+K 聚焦）
- **时间线图**：每日新闻数量柱状图（点击筛选日期）
- **主题网格**：Top 15 主题气泡（点击筛选主题）
- **新闻列表**：可滚动卡片列表，展示标题、人物、关键词、摘要
- **人物榜**：Top 15 高频人物（点击筛选人物）
- **政策信号面板**：检测到的政策信号汇总
- **详情弹窗**：AI 摘要、关键词、主题、人物、机构、政策信号、正文预览
- **全部联动**：点击任意图表元素 → 全局筛选
- **URL 状态**：`#date=2026-06-09&topic=外交` 格式，筛选结果可分享

## 技术选型与设计决策

| 决策 | 理由 |
|------|------|
| **requests + BeautifulSoup** 而非 CDP | 页面是 SSR — `<main class="article-content">` 中有完整文本，无需浏览器渲染 |
| **SQLite** | 零配置、单文件、CJK LIKE 无需分词器、INSERT OR IGNORE 幂等导入 |
| **news_id = SHA256(date + order)** | 播出顺序比标题更稳定，重抓时 ID 不变 |
| **pypinyin 自动 slug** | `lazy_pinyin("高质量发展")` → `gao-zhi-liang-fa-zhan`，无需硬编码映射表 |
| **并发增强 (ThreadPoolExecutor)** | 3 线程并行调用 DeepSeek API，速度提升 ~3x |
| **预导出** | `enhance_all()` 开始前先运行 export，确保 Pages 始终有完整数据 |
| **反规范化 JSONL** | 每条记录自包含 people/organizations/topics，前端零查询 |
| **单文件 HTML 仪表板** | 无框架依赖，fetch() 加载静态 JSONL，GitHub Pages 直接托管 |

## 数据源

- **网站**: [cn.govopendata.com/xinwenlianbo](https://cn.govopendata.com/xinwenlianbo)
- **覆盖范围**: 2007 年至今的每日新闻联播文字版
- **更新频率**: 每日晚间 ~19:30 CST 后可用
- **页面结构**: 服务端渲染（SSR），`<article class="content-section">` 内含 `<h2>` 标题 + `<div class="content-body">` 正文

## 扩展到更多天数

```bash
# 抓取 90 天
cd scraper && python main.py --days 90

# 重新导入（force 模式）
cd ../db && python main.py setup --force-reimport

# 增强新增条目（幂等，自动跳过已处理的）
python main.py enhance --concurrency 3

# 导出并提交
python export_jsonl.py
cd .. && git add data/ && git commit -m "data: expand to 90 days" && git push
```

## 换用其他 LLM

修改 `db/ai_client.py` 中的 `DEEPSEEK_BASE` 和 `DEFAULT_MODEL`，接口兼容 OpenAI 格式：

```python
from ai_client import chat
result = chat(prompt, model="gpt-4o", base="https://api.openai.com")
```

## 自定义主题分类

编辑 `db/enhance.py` 中的 `TOPICS` 列表，重新运行增强即可。当前 18 个主题：政治、经济、外交、军事、科技、社会、文化、生态、国际关系、中美关系、一带一路、乡村振兴、高质量发展、改革开放、党的建设、法治建设、民生保障、国防安全。

## 相关文档

- `docs/superpowers/specs/2026-06-10-xinwenlianbo-phase1-design.md` — Phase 1 设计文档
- `docs/superpowers/specs/2026-06-10-xinwenlianbo-phase2-design.md` — Phase 2 事件引擎设计
- `docs/superpowers/specs/2026-06-10-xinwenlianbo-phase3-design.md` — Phase 3 自动化运营设计
- `docs/superpowers/plans/2026-06-10-xinwenlianbo-phase1.md` — Phase 1 实施计划
- `docs/xinwenlianbo-ontology.md` — 原始企业级 Ontology 设计
