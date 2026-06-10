# 新闻联播 Ontology — Palantir 风格语义层

《新闻联播》文字版的完整 Ontology 落地项目。CDP 抓取 → SQLite → AI 增强 → 交互式可视化。

## 快速开始

```bash
cd xinwenlianbo/db
pip install pypinyin websockets

# 1. 抓取数据（需要 Chrome）
cd ../scraper && python main.py --days 30

# 2. 初始化数据库
cd ../db && python main.py setup

# 3. AI 增强（需要 DEEPSEEK_API_KEY）
export DEEPSEEK_API_KEY="sk-..."
python main.py enhance

# 4. 导出 + 可视化
python export_jsonl.py
cd .. && python3 -m http.server 8080
# 打开 http://localhost:8080/visualize/index.html
```

## 项目结构

```
xinwenlianbo/
├── scraper/         CDP 抓取（cn.govopendata.com）
├── db/              SQLite + AI 增强 + 查询 + 导出
├── visualize/       交互式仪表板
└── data/            JSONL 导出数据
```

## 技术栈

- Python 3 + SQLite
- CDP (Chrome DevTools Protocol) 抓取 SPA 页面
- DeepSeek v4 Flash AI 增强
- pypinyin 主题 slug 生成
- 单文件 HTML 仪表板
