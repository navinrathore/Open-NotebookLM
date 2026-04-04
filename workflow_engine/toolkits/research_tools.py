"""
Web search tool, consistent with Paper2Any.
Supports SerpAPI (engine=google or engine=baidu), Google CSE, Brave, Bocha.
Provides fetch_page_text to crawl the main text of a webpage for source details display.
"""
from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

import httpx


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: List[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts)


def _strip_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", html)
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        return ""
    text = parser.get_text()
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_page_text(url: str, max_chars: int = 50000) -> str:
    """
    Crawls many URLs corresponding to the page's HTML and extracts the main text for source details display.
    """
    if not url or not url.strip().startswith(("http://", "https://")):
        return ""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; OpenNotebook/1.0; +https://opennotebook.ai)"
    }
    try:
        with httpx.Client(timeout=20, headers=headers, follow_redirects=True) as client:
            resp = client.get(url.strip())
            resp.raise_for_status()
            content_type = (resp.headers.get("content-type") or "").lower()
            if "text/html" not in content_type:
                return "[Not an HTML page, cannot parse content]"
            html = resp.text
    except Exception as e:
        return f"[Crawl failed: {e}]"
    text = _strip_html(html)
    if max_chars and len(text) > max_chars:
        return text[:max_chars] + "\n\n... (Truncated)"
    return text or "[Page has no main content]"

BOCHA_WEB_SEARCH_URL = "https://api.bocha.cn/v1/web-search"


def _safe_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.netloc or url
    except Exception:
        return url


def serpapi_search(query: str, api_key: str, engine: str = "google", num: int = 10) -> List[Dict[str, Any]]:
    """
    SerpAPI search, supports Google and Baidu (engine="google" | "baidu").
    Returns in 1:1 format with Fast Research: [{ "title", "link", "snippet" }].
    """
    params = {
        "engine": engine,
        "q": query,
        "api_key": api_key,
        "num": num,
    }
    with httpx.Client(timeout=20) as client:
        resp = client.get("https://serpapi.com/search.json", params=params)
        resp.raise_for_status()
        data = resp.json()

    results: List[Dict[str, Any]] = []
    for item in data.get("organic_results", [])[:num]:
        url = (item.get("link") or item.get("url") or "").strip()
        snippet = item.get("snippet") or item.get("snippet_highlighted_words") or ""
        if isinstance(snippet, list):
            snippet = " ".join(str(s) for s in snippet)
        results.append({
            "title": (item.get("title") or snippet or "Untitled").strip(),
            "link": url,
            "snippet": (snippet or "").strip(),
            "source": _safe_domain(url),
        })
    return results


def google_cse_search(
    query: str, api_key: str, cx: str, num: int = 10, start: int = 1
) -> List[Dict[str, Any]]:
    """Google Custom Search Engine."""
    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "num": max(1, min(10, num)),
        "start": max(1, start),
    }
    with httpx.Client(timeout=20) as client:
        resp = client.get("https://www.googleapis.com/customsearch/v1", params=params)
        resp.raise_for_status()
        data = resp.json()

    results: List[Dict[str, Any]] = []
    for item in data.get("items", [])[:num]:
        url = (item.get("link") or "").strip()
        snippet = (item.get("snippet") or "").strip()
        results.append({
            "title": (item.get("title") or snippet or "Untitled").strip(),
            "link": url,
            "snippet": snippet,
            "source": _safe_domain(url),
        })
    return results


def brave_search(query: str, api_key: str, count: int = 10) -> List[Dict[str, Any]]:
    """Brave Search API."""
    headers = {"X-Subscription-Token": api_key}
    params = {"q": query, "count": max(1, min(20, count))}
    with httpx.Client(timeout=20, headers=headers) as client:
        resp = client.get("https://api.search.brave.com/res/v1/web/search", params=params)
        resp.raise_for_status()
        data = resp.json()

    results: List[Dict[str, Any]] = []
    for item in data.get("web", {}).get("results", [])[:count]:
        url = (item.get("url") or "").strip()
        results.append({
            "title": (item.get("title") or item.get("description") or "Untitled").strip(),
            "link": url,
            "snippet": (item.get("description") or "").strip(),
            "source": _safe_domain(url),
        })
    return results


def bocha_web_search(
    query: str,
    api_key: str,
    count: int = 10,
    *,
    summary: bool = True,
    freshness: str = "noLimit",
) -> List[Dict[str, Any]]:
    """
    Bocha AI Web Search API (https://api.bocha.cn/v1/web-search).
    Auth: Authorization: Bearer {API KEY}.
    Returns unified format: [{ "title", "link", "snippet" }], snippet prioritizes summary field.
    """
    from workflow_engine.logger import get_logger
    log = get_logger(__name__)

    payload: Dict[str, Any] = {
        "query": query,
        "count": max(1, min(50, count)),
        "summary": summary,
        "freshness": freshness,
    }
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }

    log.debug(f"Bocha search request: query={query[:100]}, count={count}")

    try:
        with httpx.Client(timeout=25) as client:
            resp = client.post(BOCHA_WEB_SEARCH_URL, json=payload, headers=headers)
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPStatusError as e:
        log.error(f"Bocha API HTTP error: {e.response.status_code}, {e.response.text[:200]}")
        raise RuntimeError(f"Bocha API request failed: HTTP {e.response.status_code}")
    except Exception as e:
        log.error(f"Bocha API request exception: {type(e).__name__}: {str(e)}")
        raise
    
    # Check response code
    code = body.get("code")
    if code != 200:
        msg = body.get("msg") or body.get("message") or "Unknown error"
        log.error(f"Bocha API returned error: code={code}, message={msg}")
        raise RuntimeError(f"Bocha API returned code={code}: {msg}")

    # Parse response data
    data = body.get("data")
    if not data:
        log.warning("No data field in Bocha API response")
        return []

    web_pages = data.get("webPages")
    if not web_pages:
        log.warning("No webPages field in Bocha API response")
        return []

    items = web_pages.get("value") or []
    log.info(f"Bocha search returned {len(items)} results")

    results: List[Dict[str, Any]] = []
    for item in items[:count]:
        url = (item.get("url") or "").strip()
        if not url:
            continue
        name = (item.get("name") or "").strip() or "Untitled"
        snippet = (item.get("summary") or item.get("snippet") or "").strip()
        results.append({
            "title": name,
            "link": url,
            "snippet": snippet,
            "source": _safe_domain(url),
        })

    log.debug(f"Bocha search successfully returned {len(results)} valid results")
    return results
