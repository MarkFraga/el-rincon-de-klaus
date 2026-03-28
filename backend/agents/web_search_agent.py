from __future__ import annotations

import asyncio
import logging
from typing import Any

import trafilatura
from duckduckgo_search import DDGS

from backend.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT = 10  # seconds per URL
_MAX_CONTENT_CHARS = 2000


class WebSearchAgent(BaseAgent):
    """Agent 1 -- general web search via DuckDuckGo + trafilatura extraction."""

    def __init__(self, job_id: str):
        super().__init__(name="web_search", job_id=job_id)

    # ------------------------------------------------------------------
    async def run(self, topic: str) -> dict:
        await self.report("Generando consultas de búsqueda...", progress=5)

        queries = self._build_queries(topic)
        raw_results: list[dict[str, Any]] = []

        for idx, query in enumerate(queries):
            pct = 10 + int((idx / len(queries)) * 20)
            await self.report(f"Buscando: {query}", progress=pct)
            try:
                hits = await asyncio.to_thread(
                    lambda q=query: DDGS().text(q, max_results=8)
                )
                if hits:
                    raw_results.extend(hits)
            except Exception as exc:
                logger.warning("DuckDuckGo query failed (%s): %s", query, exc)

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique: list[dict[str, Any]] = []
        for r in raw_results:
            url = r.get("href") or r.get("link") or ""
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique.append(r)

        await self.report(
            f"Extrayendo contenido de {len(unique)} fuentes...", progress=35
        )

        sources: list[dict[str, str]] = []
        tasks = [self._extract(r) for r in unique]
        extracted = await asyncio.gather(*tasks, return_exceptions=True)

        for item in extracted:
            if isinstance(item, dict) and item.get("content"):
                sources.append(item)

        summary = "\n\n---\n\n".join(
            f"## {s['title']}\n{s['content']}" for s in sources
        )

        await self.report(
            f"Búsqueda web completada: {len(sources)} fuentes útiles.",
            progress=45,
        )

        return {"sources": sources, "summary": summary}

    # ------------------------------------------------------------------
    @staticmethod
    def _build_queries(topic: str) -> list[str]:
        return [
            topic,
            f"{topic} explicado",
            f"{topic} investigación científica",
            f"{topic} datos curiosos",
        ]

    # ------------------------------------------------------------------
    async def _extract(self, result: dict[str, Any]) -> dict[str, str]:
        url = result.get("href") or result.get("link") or ""
        title = result.get("title", "Sin título")

        if not url:
            return {}

        try:
            downloaded = await asyncio.wait_for(
                asyncio.to_thread(trafilatura.fetch_url, url),
                timeout=_FETCH_TIMEOUT,
            )
            if not downloaded:
                return {}

            text = await asyncio.to_thread(trafilatura.extract, downloaded)
            if not text:
                return {}

            return {
                "title": title,
                "url": url,
                "content": text[:_MAX_CONTENT_CHARS],
            }
        except (asyncio.TimeoutError, Exception) as exc:
            logger.debug("Extraction failed for %s: %s", url, exc)
            return {}
