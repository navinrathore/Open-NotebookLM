"""
Search & Add Service
Simple Web Search + Top10 Crawling Functionality
"""
import asyncio
import httpx
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from workflow_engine.logger import get_logger

log = get_logger(__name__)


class SearchAndAddService:
    """Search & Add Service"""

    def __init__(self):
        self.timeout = 30.0

    async def search_and_crawl(
        self,
        query: str,
        top_k: int = 10,
        search_provider: str = "serper",
        search_api_key: str = None,
    ) -> Dict[str, Any]:
        """
        Search and crawl Top K results.

        Args:
            query: Search query
            top_k: Return top K results
            search_provider: Search engine provider
            search_api_key: Search API key

        Returns:
            {
                "success": bool,
                "query": str,
                "sources": List[{
                    "title": str,
                    "url": str,
                    "snippet": str,
                    "content": str,  # Crawled full content
                    "crawl_success": bool
                }]
            }
        """
        log.info(f"[SearchAndAdd] Starting search: {query}, top_k={top_k}")

        try:
            # 1. Execute search
            search_results = await self._search(
                query, top_k, search_provider, search_api_key
            )

            if not search_results:
                return {
                    "success": False,
                    "query": query,
                    "sources": [],
                    "error": "No results returned from search"
                }

            # 2. Concurrently crawl all results
            crawl_tasks = [
                self._crawl_url(result["url"], result["title"])
                for result in search_results[:top_k]
            ]
            crawled_contents = await asyncio.gather(*crawl_tasks, return_exceptions=True)

            # 3. Merge search results and crawled content
            sources = []
            for i, result in enumerate(search_results[:top_k]):
                crawl_result = crawled_contents[i]

                if isinstance(crawl_result, Exception):
                    log.warning(f"[SearchAndAdd] Crawl failed for {result['url']}: {crawl_result}")
                    sources.append({
                        **result,
                        "content": result["snippet"],  # Fallback to snippet
                        "crawl_success": False
                    })
                else:
                    sources.append({
                        **result,
                        "content": crawl_result,
                        "crawl_success": True
                    })

            log.info(f"[SearchAndAdd] Completed, successfully crawled {sum(s['crawl_success'] for s in sources)}/{len(sources)} pages")

            return {
                "success": True,
                "query": query,
                "sources": sources
            }

        except Exception as e:
            log.error(f"[SearchAndAdd] Execution failed: {e}")
            return {
                "success": False,
                "query": query,
                "sources": [],
                "error": str(e)
            }

    async def _search(
        self,
        query: str,
        top_k: int,
        provider: str,
        api_key: str = None
    ) -> List[Dict[str, str]]:
        """Execute search"""
        if provider == "serper":
            return await self._search_serper(query, top_k, api_key)
        else:
            raise ValueError(f"Unsupported search provider: {provider}")

    async def _search_serper(
        self,
        query: str,
        top_k: int,
        api_key: str = None
    ) -> List[Dict[str, str]]:
        """Search using Serper API"""
        import os
        api_key = api_key or os.getenv("SERPER_API_KEY")

        if not api_key:
            raise ValueError("SERPER_API_KEY is not configured")

        url = "https://google.serper.dev/search"
        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "q": query,
            "num": top_k
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("organic", [])[:top_k]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", "")
            })

        return results

    async def _crawl_url(self, url: str, title: str) -> str:
        """
        Crawl content of a single URL.

        Args:
            url: Target URL
            title: Page title

        Returns:
            Crawled text content (Markdown format)
        """
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            ) as client:
                response = await client.get(url)
                response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.text, "html.parser")

            # Remove scripts and styles
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()

            # Extract main content
            # Prioritize common content containers
            main_content = None
            for selector in ["article", "main", ".content", "#content", ".post", ".entry"]:
                main_content = soup.select_one(selector)
                if main_content:
                    break

            if not main_content:
                main_content = soup.body

            if not main_content:
                return f"# {title}\n\nUnable to extract page content"

            # Extract text
            text = main_content.get_text(separator="\n", strip=True)

            # Clean up extra blank lines
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            text = "\n\n".join(lines)

            # Limit length (avoid being too long)
            max_chars = 50000
            if len(text) > max_chars:
                text = text[:max_chars] + "\n\n...(Content truncated)"

            # Format as Markdown
            markdown = f"# {title}\n\n**Source:** {url}\n\n---\n\n{text}"

            return markdown

        except Exception as e:
            log.error(f"[SearchAndAdd] Failed to crawl {url}: {e}")
            raise

    def format_sources_as_markdown(self, sources: List[Dict[str, Any]]) -> str:
        """Format multiple sources into a single Markdown document"""
        md_parts = []

        for i, source in enumerate(sources, 1):
            md_parts.append(f"# Source {i}: {source['title']}")
            md_parts.append(f"\n**URL:** {source['url']}")
            md_parts.append(f"\n**Crawl Status:** {'✓ Success' if source['crawl_success'] else '✗ Failed'}")
            md_parts.append("\n---\n")
            md_parts.append(source['content'])
            md_parts.append("\n\n" + "="*80 + "\n\n")

        return "".join(md_parts)
