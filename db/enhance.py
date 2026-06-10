"""
AI-powered enhancements for the xinwenlianbo ontology database.
Uses DeepSeek API (deepseek-v4-flash) to extract structured data from news items:
summaries, keywords, topic classification, named entities, and policy signals.
"""
import sqlite3, json, time
from pypinyin import lazy_pinyin, Style
from ai_client import chat, chat_json


def slugify(text):
    """Generate pinyin slug from Chinese text. e.g. '高质量发展' -> 'gao-zhi-liang-fa-zhan'"""
    return "-".join(lazy_pinyin(text, style=Style.NORMAL))


TOPICS = [
    "政治", "经济", "外交", "军事", "科技", "社会", "文化", "生态",
    "国际关系", "中美关系", "一带一路", "乡村振兴", "高质量发展",
    "改革开放", "党的建设", "法治建设", "民生保障", "国防安全",
]

SYSTEM_PROMPT = """\
You are a senior news analyst specializing in Chinese current affairs. Your task is to read transcripts from 《新闻联播》 (Xinwen Lianbo) — the daily evening news broadcast of China Central Television — and extract structured analytical data.

## Quality Standards

1. **Grounded in the text.** Every extraction must trace back to the broadcast transcript.
2. **Use exact terminology.** Quote the broadcast's own phrasing for keywords, names, and entities.
3. **Be specific.** "王毅会见美国国务卿讨论台湾问题" is useful; "外交活动" is not.
4. **Calibrate relevance scores.** 0.9-1.0 = central story; 0.6-0.8 = major segment; 0.3-0.5 = briefly mentioned.
5. **Policy signals require evidence.** A new policy formulation or notable emphasis shift, not just routine coverage.
6. **Return only valid JSON.** No markdown fences, no commentary.

Always respond in Chinese. Be rigorous, precise, and concise."""

_USER_PROMPT_TEMPLATE = """\
Analyze the following news segment from 《新闻联播》. Extract structured data.

## News Segment

**Title:** {title}

**Content:**
{text}

## JSON Output Schema

Return exactly this JSON structure (no markdown fences, no extra text):

{{
  "summary": {{"short": "2-3句中文摘要（80-150字）"}},
  "keywords": ["关键词1", ...],
  "topics": [{{"name": "主题名（从下方列表选择）", "relevance": 0.0-1.0, "rationale": "依据（15字以内）"}}],
  "entities": {{
    "people": [{{"name": "姓名", "title": "职务"}}],
    "organizations": [{{"name": "机构全称", "type": "government|military|enterprise|international|media|academic"}}],
    "locations": [{{"name": "地名", "level": "国家|省|市|县"}}],
    "policies": [{{"name": "政策/文件全称", "year": null}}]
  }},
  "policy_signals": [{{"signal": "新提法或政策信号", "type": "新提法|表述转变|政策升级|实施方案", "evidence": "依据（一句话）"}}],
  "argument": {{"main_thesis": "核心内容（50字以内）", "supporting_points": ["要点1", "要点2", "要点3"]}}
}}

## Topic Taxonomy (you MUST select from this list)

{topics_json}

## Important

- Return ONLY the JSON object. No markdown fences.
- If the content is truncated or incomplete, set keywords to ["TRUNCATED"]."""


def _infer_org_from_title(title, entities):
    """Try to match a person's title to an organization extracted from the same article."""
    if not title:
        return None
    orgs = entities.get("organizations", []) if isinstance(entities, dict) else []
    for org in orgs[:5]:
        oname = org.get("name", "") if isinstance(org, dict) else str(org)
        if not oname:
            continue
        # Check if title contains org name or key part of it
        for part in oname.split(" "):
            if len(part) >= 3 and part in title:
                return oname
    return None


def enhance_news_item(conn, news_id, title, full_text, max_text_len=4000):
    """Extract structured data from a single news item via DeepSeek API."""
    text = full_text[:max_text_len]
    prompt = _USER_PROMPT_TEMPLATE.format(
        title=title, text=text,
        topics_json=json.dumps(TOPICS, ensure_ascii=False),
    )
    result = chat_json(prompt, SYSTEM_PROMPT)
    if not result:
        return {}
    if "article_analysis" in result:
        result = result["article_analysis"]
    return result


def persist_enhancement(conn, news_id, result):
    """Persist AI enhancement result to the database. Returns True on success."""
    summary_data = result.get("summary", {})
    if isinstance(summary_data, dict):
        summary = summary_data.get("short", "")
    elif isinstance(summary_data, str):
        summary = summary_data
    else:
        summary = ""
    if not summary:
        return False

    keywords_raw = result.get("keywords", [])
    keywords = json.dumps(keywords_raw, ensure_ascii=False) if keywords_raw else "[]"

    entities = result.get("entities", {})
    tags = json.dumps(entities, ensure_ascii=False) if entities else "{}"

    conn.execute(
        "UPDATE news_item SET summary = ?, keywords = ?, tags = ? WHERE news_id = ?",
        (summary, keywords, tags, news_id),
    )

    # Topic links
    for t in result.get("topics", []):
        tname = t.get("name", "") if isinstance(t, dict) else str(t)
        relevance = t.get("relevance", 0.5) if isinstance(t, dict) else 0.5
        if not tname:
            continue
        tid = slugify(tname)
        conn.execute(
            "INSERT OR IGNORE INTO topic (topic_id, name, category) VALUES (?, ?, '')",
            (tid, tname),
        )
        conn.execute(
            "INSERT OR IGNORE INTO news_topic (news_id, topic_id, relevance_score) VALUES (?, ?, ?)",
            (news_id, tid, relevance),
        )

    # People
    people = entities.get("people", []) if isinstance(entities, dict) else []
    for person in people[:5]:
        pname = person.get("name", "") if isinstance(person, dict) else str(person)
        ptitle = person.get("title", "") if isinstance(person, dict) else ""
        if pname:
            # Try to infer organization from title
            org_id = _infer_org_from_title(ptitle, entities)
            conn.execute(
                "INSERT OR IGNORE INTO person (person_id, name, name_chinese, title, organization_id) VALUES (?, ?, ?, ?, ?)",
                (pname, pname, pname, ptitle, org_id),
            )
            conn.execute(
                "INSERT OR IGNORE INTO news_person (news_id, person_id) VALUES (?, ?)",
                (news_id, pname),
            )

    # Organizations
    orgs = entities.get("organizations", []) if isinstance(entities, dict) else []
    for org in orgs[:5]:
        oname = org.get("name", "") if isinstance(org, dict) else str(org)
        otype = org.get("type", "government") if isinstance(org, dict) else "government"
        if oname:
            conn.execute(
                "INSERT OR IGNORE INTO organization (org_id, name, type) VALUES (?, ?, ?)",
                (oname, oname, otype),
            )
            conn.execute(
                "INSERT OR IGNORE INTO news_organization (news_id, org_id) VALUES (?, ?)",
                (news_id, oname),
            )

    # Policy signals
    signals = result.get("policy_signals", [])
    if signals:
        try:
            tags_dict = json.loads(tags)
        except (json.JSONDecodeError, TypeError):
            tags_dict = {}
        tags_dict["_policy_signals"] = signals
        conn.execute(
            "UPDATE news_item SET tags = ? WHERE news_id = ?",
            (json.dumps(tags_dict, ensure_ascii=False), news_id),
        )

    return True


def enhance_all(conn, limit=0, dry_run=False):
    """Enhance all un-enhanced news items. Idempotent — skips items with summaries.
    Pre-exports JSONL before enhancement so Pages always has complete data."""
    # Pre-export: ensure Pages has current data even if enhancement fails partway
    try:
        from export_jsonl import main as _export
        _export()
    except Exception:
        pass

    cursor = conn.execute(
        "SELECT news_id, title, full_text FROM news_item "
        "WHERE summary IS NULL OR summary = '' "
        "ORDER BY news_id LIMIT ?", (limit if limit > 0 else 9999,)
    )
    items = cursor.fetchall()
    stats = {"total": len(items), "enhanced": 0, "failed": 0, "skipped": 0}

    for i, (nid, title, text) in enumerate(items):
        if not text or len(text) < 50:
            stats["skipped"] += 1
            continue
        print(f"[{i+1}/{len(items)}] {nid}: {title[:50]}...")
        if dry_run:
            stats["skipped"] += 1
            continue
        result = enhance_news_item(conn, nid, title, text)
        if not result:
            stats["failed"] += 1
            print("  FAILED (no response)")
            continue
        ok = persist_enhancement(conn, nid, result)
        conn.commit()
        if not ok:
            stats["failed"] += 1
            print("  FAILED (no summary)")
            continue
        stats["enhanced"] += 1
        nk = len(result.get("keywords", []))
        nt = len(result.get("topics", []))
        ns = len(result.get("policy_signals", []))
        print(f"  OK - {nk} keywords, {nt} topics, {ns} signals")
        time.sleep(0.5)
    return stats


def analyze_topic_evolution(conn, topic_name):
    """Use AI to generate a narrative analysis of how a topic evolved."""
    cursor = conn.execute("""
        SELECT n.news_id, n.broadcast_date, n.title, n.summary, n.full_text
        FROM news_item n
        JOIN news_topic nt ON n.news_id = nt.news_id
        JOIN topic t ON nt.topic_id = t.topic_id
        WHERE t.name = ? OR t.topic_id = ?
        ORDER BY n.broadcast_date
    """, (topic_name, topic_name))
    rows = cursor.fetchall()
    if not rows:
        return "No items found for this topic."

    timeline = []
    for r in rows:
        preview = (r["summary"] or r["full_text"] or "")[:300]
        timeline.append(f"[{r['broadcast_date']}] {r['title']}\n  {preview}")

    prompt = f"""Analyze how the topic "{topic_name}" evolved in 《新闻联播》 coverage:

{chr(10).join(timeline)}

Write a 3-4 paragraph Chinese analysis covering emergence, framing shifts, peak coverage, and policy implications."""

    return chat(prompt, SYSTEM_PROMPT, max_tokens=1500) or "Analysis failed."
