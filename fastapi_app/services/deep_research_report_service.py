"""
Deep Research Report: Get search results first, then pass to LLM to generate a long report.
LLM must output the title on the first line, used for naming the source (caller adds [report] prefix).
"""
from __future__ import annotations

import re
from typing import Tuple

import httpx

from workflow_engine.logger import get_logger

log = get_logger(__name__)

SYSTEM_PROMPT = """You are a Deep Research Assistant. You will be given a research topic and a set of web search results (title, link, snippet for each). Your task is to write one comprehensive, structured research report in the specified language.

Requirements:
1. The FIRST line of your response MUST be exactly: Title: <short title in the specified language, no more than 40 characters, no newline>
2. Then a blank line, then the full report body.
3. Use the search results as sources and evidence; cite or summarize them where relevant.
4. Organize with clear sections (e.g. Introduction, Key Points, Analysis, Conclusion).
5. Be thorough and objective. No other meta-commentary."""

USER_PROMPT_TEMPLATE = """[Topic]:
{topic}

[Language]: {language}

[Web search results]:
{search_context}

Please write a detailed research report. The first line must be: Title: <short title in the specified language>. Then a blank line, then the full report content."""


def _parse_title_and_content(raw: str, topic: str) -> Tuple[str, str]:
    """Parse the first line 'Title: xxx' and the body from LLM output; use 'topic' as title if missing."""
    raw = (raw or "").strip()
    if not raw:
        return (topic[:40] or "Deep Research Report", "")
    first_line, _, rest = raw.partition("\n")
    m = re.match(r"^Title:\s*(.+)$", first_line.strip(), re.IGNORECASE)
    if m:
        title = m.group(1).strip()[:40]
        content = rest.lstrip("\n")
        return (title or topic[:40], content)
    return (topic[:40] or "Deep Research Report", raw)


def generate_report_from_search(
    topic: str,
    search_context: str,
    *,
    api_url: str,
    api_key: str,
    model: str = "deepseek-v3.2",
    language: str = "en",
) -> Tuple[str, str]:
    """
    Call LLM to generate a long research report based on topic and search_context.
    Returns (report_title, report_body); title used for naming the source (caller adds [report] prefix).
    """
    url = api_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"
    user_content = USER_PROMPT_TEMPLATE.format(
        topic=topic,
        language=language,
        search_context=search_context or "(No search results, please improvise based on the topic)",
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.7,
        "max_tokens": 16000,
    }
    log.info(
        "[deep_research_report] LLM Input: model=%s, url=%s, topic=%r, search_context_len=%s, user_content_preview=%s",
        model,
        url,
        topic[:100],
        len(search_context or ""),
        (user_content[:500] + "..." if len(user_content) > 500 else user_content),
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        log.warning("[deep_research_report] LLM call failed: %s", e)
        raise
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(data.get("error", "No choices in response"))
    raw = (choices[0].get("message") or {}).get("content") or ""
    raw = raw.strip()
    title, content = _parse_title_and_content(raw, topic)
    log.info(
        "[deep_research_report] LLM Output: title=%r, report_len=%s, preview=%s",
        title,
        len(content),
        (content[:400] + "..." if len(content) > 400 else content),
    )
    return (title, content)
