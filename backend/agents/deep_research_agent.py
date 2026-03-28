from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

from backend.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT = 10  # seconds per URL
_MAX_CONTENT_CHARS = 2000


class DeepResearchAgent(BaseAgent):
    """Agent 4 -- deep/obscure research via advanced DuckDuckGo queries + CORE API."""

    def __init__(self, job_id: str):
        super().__init__(name="deep_research", job_id=job_id)

    # ------------------------------------------------------------------
    async def run(self, topic: str) -> dict:
        await self.report("Iniciando búsqueda profunda...", progress=5)

        queries = self._build_queries(topic)
        raw_results: list[dict[str, Any]] = []

        # DuckDuckGo advanced queries
        for idx, query in enumerate(queries):
            pct = 8 + int((idx / len(queries)) * 15)
            await self.report(f"Búsqueda profunda: {query[:60]}...", progress=pct)
            try:
                hits = await asyncio.to_thread(
                    lambda q=query: DDGS().text(q, max_results=8)
                )
                if hits:
                    raw_results.extend(hits)
            except Exception as exc:
                logger.warning("DDG deep query failed (%s): %s", query, exc)

        # CORE API
        await self.report("Consultando CORE API...", progress=28)
        core_results = await self._search_core(topic)
        raw_results.extend(core_results)

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique: list[dict[str, Any]] = []
        for r in raw_results:
            url = r.get("href") or r.get("link") or r.get("url") or ""
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique.append(r)

        await self.report(
            f"Extrayendo contenido de {len(unique)} fuentes profundas...",
            progress=32,
        )

        # Extract text in parallel
        tasks = [self._extract(r) for r in unique]
        extracted = await asyncio.gather(*tasks, return_exceptions=True)

        sources: list[dict[str, str]] = []
        for item in extracted:
            if isinstance(item, dict) and item.get("content"):
                sources.append(item)

        summary = "\n\n---\n\n".join(
            f"## {s['title']}\n{s['content']}" for s in sources
        )

        await self.report(
            f"Búsqueda profunda completada: {len(sources)} fuentes.", progress=45
        )

        return {"sources": sources, "summary": summary}

    # ------------------------------------------------------------------
    @staticmethod
    def _build_queries(topic: str) -> list[str]:
        return [
            f'"{topic}" site:researchgate.net',
            f'"{topic}" site:academia.edu',
            f'"{topic}" filetype:pdf research paper',
            f'"{topic}" preprint 2024 OR 2025 OR 2026',
            f'"{topic}" lesser known research findings',
            f'"{topic}" controversial study',
        ]

    # ------------------------------------------------------------------
    async def _search_core(self, topic: str) -> list[dict[str, Any]]:
        """Search the CORE API. Fail gracefully if unavailable."""
        try:
            from urllib.parse import quote_plus

            encoded = quote_plus(topic)
            url = f"https://api.core.ac.uk/v3/search/works?q={encoded}&limit=8"
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    url, headers={"Authorization": "Bearer free"}
                )
                resp.raise_for_status()
                data = resp.json()

            results: list[dict[str, Any]] = []
            for item in data.get("results", []):
                download_url = item.get("downloadUrl") or item.get("sourceFulltextUrls") or ""
                if isinstance(download_url, list):
                    download_url = download_url[0] if download_url else ""
                results.append({
                    "title": item.get("title", ""),
                    "href": download_url or item.get("links", [{}])[0].get("url", "") if item.get("links") else "",
                    "body": (item.get("abstract") or "")[:_MAX_CONTENT_CHARS],
                })
            return results
        except Exception as exc:
            logger.warning("CORE API failed (skipping): %s", exc)
            return []

    # ------------------------------------------------------------------
    async def _extract(self, result: dict[str, Any]) -> dict[str, str]:
        url = result.get("href") or result.get("link") or result.get("url") or ""
        title = result.get("title", "Sin título")

        # If we already have body text from CORE, use it directly
        body = result.get("body") or ""
        if body and len(body) > 100:
            return {"title": title, "url": url, "content": body[:_MAX_CONTENT_CHARS]}

        if not url:
            return {}

        try:
            async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code != 200:
                    return {}
                html = resp.text

            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)

            if not text or len(text) < 100:
                return {}

            return {
                "title": title,
                "url": url,
                "content": text[:_MAX_CONTENT_CHARS],
            }
        except Exception as exc:
            logger.debug("Deep extraction failed for %s: %s", url, exc)
            return {}
