from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

from backend.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT = 12
_MAX_CONTENT_CHARS = 3000


class WebSearchAgent(BaseAgent):
    """Agent 1 -- massive general web search via DuckDuckGo."""

    def __init__(self, job_id: str):
        super().__init__(name="web_search", job_id=job_id)

    async def run(self, topic: str) -> dict:
        await self.report("Generando consultas de busqueda masiva...", progress=5)

        queries = self._build_queries(topic)
        raw_results: list[dict[str, Any]] = []

        for idx, query in enumerate(queries):
            pct = 5 + int((idx / len(queries)) * 25)
            await self.report(f"Buscando ({idx+1}/{len(queries)}): {query[:50]}...", progress=pct)
            try:
                hits = await asyncio.to_thread(
                    lambda q=query: DDGS().text(q, max_results=15)
                )
                if hits:
                    raw_results.extend(hits)
            except Exception as exc:
                logger.warning("DuckDuckGo query failed (%s): %s", query, exc)
            await asyncio.sleep(0.5)  # rate limit courtesy

        seen_urls: set[str] = set()
        unique: list[dict[str, Any]] = []
        for r in raw_results:
            url = r.get("href") or r.get("link") or ""
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique.append(r)

        await self.report(f"Extrayendo contenido de {len(unique)} fuentes...", progress=35)

        # Extract in batches of 10 to avoid overwhelming
        sources: list[dict[str, str]] = []
        for batch_start in range(0, len(unique), 10):
            batch = unique[batch_start:batch_start + 10]
            tasks = [self._extract(r) for r in batch]
            extracted = await asyncio.gather(*tasks, return_exceptions=True)
            for item in extracted:
                if isinstance(item, dict) and item.get("content"):
                    sources.append(item)

        summary = "\n\n---\n\n".join(
            f"## {s['title']}\n{s['content']}" for s in sources
        )

        await self.report(f"Busqueda web completada: {len(sources)} fuentes utiles.", progress=45)
        return {"sources": sources, "summary": summary}

    @staticmethod
    def _build_queries(topic: str) -> list[str]:
        return [
            topic,
            f"{topic} explicacion detallada",
            f"{topic} investigacion cientifica",
            f"{topic} datos curiosos sorprendentes",
            f"{topic} historia y origenes",
            f"{topic} ultimos descubrimientos 2024 2025",
            f"{topic} debate cientifico controversia",
            f"{topic} expertos opinion",
            f"{topic} estadisticas datos reales",
            f"{topic} futuro predicciones",
            f"{topic} como funciona mecanismo",
            f"{topic} impacto sociedad consecuencias",
        ]

    async def _extract(self, result: dict[str, Any]) -> dict[str, str]:
        url = result.get("href") or result.get("link") or ""
        title = result.get("title", "Sin titulo")

        if not url:
            return {}

        try:
            async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code != 200:
                    return {}
                html = resp.text

            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
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
            logger.debug("Extraction failed for %s: %s", url, exc)
            return {}
