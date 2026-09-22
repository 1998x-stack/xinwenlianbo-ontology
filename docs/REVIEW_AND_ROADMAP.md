# 源码审查与改造路线图（2026-09-22）

## 架构与审查范围

`scraper → Markdown → SQLite → AI 增强 / 事件引擎 → JSONL / JSON → GitHub Pages`。

已审查采集、导入、两份数据库 schema、查询、AI 调用、事件管道、导出和两个可视化页面。测试范围为临时 SQLite 数据库、静态代码/脚本检查及 CLI 启动；**尚未完成真实网站、完整生产数据库、第三方 AI 和浏览器的端到端验收**。仓库已有的 `data/*.json*` 是历史快照，不代表此次代码修改后的重新生成结果。

## 已实施并提交到本 PR

- `db/import_data.py`：严格校验日期、来源文件与条目；批次事务和异常回滚；开启外键检查；相同原文重复导入保持现有增强字段；相同日期/位置出现内容变化时拒绝静默覆盖。
- `db/export_graph.py`：仅根据当前选中的新闻生成实体节点与有效关联边；共现局限在选中新闻中；孤立节点 PageRank 权重重新分配。
- `visualize/index.html`：重建统计、时间线、主题、人物、事件、新闻检索及详情弹窗；动态内容通过 `textContent`/安全 DOM API 构建；来源链接限定 `http/https`，显示数据覆盖范围及推断提示。
- `visualize/graph.html`：D3 提示信息及错误改用文本节点；忽略无效端点；支持类型筛选、键盘选择、详情与图例。
- `tests/`、`.github/workflows/ci.yml`：临时 SQLite 回归、前端危险 DOM sink 静态检查、Node.js 语法检查、Python 3.10–3.13 编译和 CLI 启动检查。

### 数据兼容性注意事项

原有 `news_id` 由日期+播出顺序生成。它无法在来源重新排序后自动识别同一篇报道，因此导入遇到 ID/内容冲突时**主动停止**。请先核对原始数据、备份现有数据库及 AI/事件关联，再设计显式迁移；不能把 `--force-reimport` 当作消除内容冲突的开关。当前修改未重新导出仓库中的任何历史 JSON 数据，亦未更改现有 schema。

## 继续实施的计划及验收标准

**P0：端到端安全和可视化验收。** 在真实浏览器中检查仪表板、图谱、键盘导航、移动端、模态框焦点、D3 CDN 失败和数据加载失败。使用受控的特殊字符样本检查 JSONL、图谱标签、URL hash 和事件摘要只能呈现文本；目前静态安全测试不是浏览器安全审计。

**P0：证据与本体可信度。** 为 NewsItem、NewsEvent、Person、Organization、Topic 及其关系补充来源 URL、采集时间、原文 hash、证据片段、抽取方式、模型版本、人工复核状态。将原始报道、AI 推断、人工确认分层展示；不能将共现自动描述成因果，亦不应在未确定类别时默认所有事件为 `political`。给出数据日期范围，避免把历史快照误读为实时新闻。

**P1：事件管道原子发布。** 当前 `run_event_pipeline` 首先清空事件表，并在多个阶段提交；AI/数据库错误可能让先前结果丢失或留下半成品。建议使用隔离的工作表/运行代次，在全量校验后原子切换。验收：注入网络超时、429、无效 JSON、SQLite 锁后，上一成功结果仍可用，重复运行没有不可解释的漂移。

**P1：采集、查询和导出。** 为抓取增加重试上限、来源结构变化提示与 provenance；导出期间使用一致的只读快照，写临时文件后原子替换。检验中断、缺表、空集、异常日期、损坏 JSON、真实数据全量图谱以及 CLI 所有命令；优化 `get_date_summary` 的 N+1 查询和全文搜索实现。

**P2：真正的语义本体。** 现有 SQL 关系和 JSON 图谱还不是完整 OWL/RDF 本体。先明确实体、断言与关系类型及语义边界，再参照 W3C PROV-O 建模数据生成过程、使用 RDF/SHACL 验证约束；在小样本证明实体消歧、事件拆合、来源追溯和错误回滚后迁移全量数据。图谱应显示关系性质及证据，不把 PageRank 直接解释为现实重要性。

## 复现测试

```bash
python -m pip install requests beautifulsoup4 pypinyin
python -m compileall -q db scraper tests
python -m unittest discover -s tests -v
python db/main.py --help
python scraper/main.py --help
```

测试不需要 API key，使用独立临时数据库，不修改仓库的 `data/` 快照。

## 技术依据

- SQLite: https://www.sqlite.org/foreignkeys.html
- OWASP DOM XSS: https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html
- W3C PROV-O: https://www.w3.org/TR/prov-o/
- W3C SHACL: https://www.w3.org/TR/shacl/
