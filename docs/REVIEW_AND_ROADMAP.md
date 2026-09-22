# 源码审查与改造路线图（2026-09-22）

## 当前结构与数据语义

` scraper → Markdown → SQLite (schema.sql / schema_v2.sql) → AI 增强与事件聚类 → JSONL/JSON → GitHub Pages `。

已审查的关键代码：`scraper/{main,scraper}.py`、`db/{main,import_data,queries,ai_client,event_engine,export_jsonl,export_graph}.py`、两份 SQLite schema、`visualize/index.html`。本次检查为静态源码审查与新增离线回归测试；**没有对真实采集站点、现有完整数据库、DeepSeek API 或浏览器部署执行端到端验收**。

## 本次已实施

- `db/import_data.py`：导入前开启 SQLite 外键约束；校验 `YYYYMMDD.md` 的实际日期与非空文章；全部文件共用一个事务；回滚重复 ID 对应不同内容的导入，而非静默跳过；检查 `PRAGMA foreign_key_check` 的结果。相同原始内容的重入保留已存的人工/AI 增强字段。
- `db/export_graph.py`：基于输出新闻选取实体；图谱关联仅指向已输出节点；人物共现仅统计当前图谱选中的新闻；处理 PageRank 的孤立节点权重。
- `tests/test_data_integrity.py`：以临时 SQLite 数据库进行独立测试；CI 覆盖 Python 3.10–3.13，并执行编译检查及 CLI 启动检查。

### 兼容性与操作警告

- 为兼容已有关联记录，新闻 ID 仍是播出日期 + 条目顺序的哈希；**它不能证明在新闻顺序改变之后对应的是同一条新闻**。新导入遇到标题或全文冲突时会终止整个批次并抛出提示。请先人工核对来源、备份数据库和相关增强/事件关系，再决定是否采用显式迁移流程；不要直接删除生产数据后重导。
- 本次没有重写已跟踪的 `data/*.json*`；它们是既有快照，不能被解释为已用修改后的算法重新计算过的数据。要生成新图谱，应在独立测试数据库上执行导出并检查变化。
- `db/main.py setup --force-reimport` 不再能忽略内容冲突；原有 `setup` 也不会自动修复错误的来源顺序或跨表引用。

## 后续优先实施项目及验收标准

### P0：前端信任边界

当前 `visualize/index.html` 使用 `innerHTML`/`insertAdjacentHTML` 拼接新闻、人物、事件、摘要、搜索词等动态内容。按 OWASP DOM XSS 指南重写动态内容渲染：对文本节点使用 `textContent`，对结构使用安全 DOM API，对受控属性使用明确的允许列表；避免只针对个别字段进行局部转义。新增浏览器层回归测试，分别覆盖 JSONL 字段、URL hash 搜索条件及事件弹窗，确保注入的标记仅作为普通文本出现。**本 PR 没有修复现有网页的这项风险，因此不要把现有网页视为已完成安全加固。**

### P0：数据来源与推断边界

新增 `source_url`、`source_retrieved_at`、`source_hash`、`extraction_method`、`model_name`、`model_version`、`review_status` 等可追溯字段或独立断言表。事件类别、关联关系、重要性与展望均应标记为“算法推断”或“人工核实”，不能把某一次节目报道或 AI 生成摘要直接等同于已独立核实的事实。禁止在证据不足时将默认事件类别硬编码为 `political`，也不应把共现关系自动显示成因果关系。数据覆盖的起止日期应直接来自数据，而不是将历史快照描述为实时新闻。

### P1：事件引擎幂等与失败恢复

当前 `run_event_pipeline` 启动时直接清空全部事件表，并在后续多个阶段 `commit`；第三方调用失败可能使已有事件数据丢失或留下部分结果。应改用临时表或生成代次 `pipeline_run_id`，在完整验证之后执行原子切换，并保留最近一次成功结果；补充 API 超时、429、无效 JSON、SQLite 写锁和部分聚类失败的故障注入测试。验证“旧结果仍可用、没有半成品发布、重复执行结果可预测”。

### P1：采集与导出可靠性

采集器需要有界重试、来源响应结构变化报警、每日抓取状态、URL 与采集时间保留、Markdown 元数据的无损解析。导出器需要在一致的 SQLite 只读快照中生成文件、先写临时文件后原子替换，并在发布前校验 JSON/JSONL 格式与关系引用；加入缺表、空集、损坏数据和静态站点加载冒烟测试。

### P2：真正的本体语义层

目前结构更接近关系型实体—关系表与 JSON 图谱，不能仅凭目录名称视为完整 OWL/RDF 本体。设计明确的 `NewsItem`、`NewsEvent`、`Person`、`Organization`、`Topic`、`SourceDocument`、`Assertion` 及其关系语义，给每条断言保留原文证据位置、来源、生成过程及置信度。采用 W3C PROV-O 建模来源/活动，RDF/SHACL 执行基于 shape 的数据验证；先在受控数据样本上验证实体消歧、时间范围、多对多关系、事件拆分/合并、错误回滚，再考虑全量迁移。

### P2：前端可视化改进

增加“原始报道 / AI 推断 / 人工确认”标识、来源链接、日期覆盖区间、筛选结果与全量数据计数的区分、可访问性与移动端适配。图谱提供节点/边类型图例、来源详情、固定随机种子或稳定排序、边数限制与按需加载；将共现、主题关联和人工确认的因果关系用不同视觉编码展示，避免把中心性指标等同于现实重要性。

## 本地验证

```bash
python -m pip install requests beautifulsoup4 pypinyin
python -m compileall -q db scraper tests
python -m unittest discover -s tests -v
python db/main.py --help
python scraper/main.py --help
```

该测试集使用临时数据库，既不需要 API key，也不会修改仓库的 `data/` 快照。

## 外部技术参考

- SQLite foreign key enforcement and validation: https://www.sqlite.org/foreignkeys.html and https://www.sqlite.org/pragma.html#pragma_foreign_key_check
- OWASP DOM-based XSS Prevention: https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html
- W3C PROV-O: https://www.w3.org/TR/prov-o/
- W3C SHACL: https://www.w3.org/TR/shacl/
