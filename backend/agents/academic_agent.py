from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote_plus

import httpx

from backend.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

_TIMEOUT = 25
_MAX_RETRIES = 2
_RETRY_DELAY = 2  # seconds between retries


class AcademicAgent(BaseAgent):
    """Agent 3 -- massive academic search across arXiv, Semantic Scholar and CrossRef."""

    def __init__(self, job_id: str):
        super().__init__(name="academic", job_id=job_id)

    async def _call_with_retry(
        self,
        func,
        client: httpx.AsyncClient,
        query: str,
        api_name: str,
        query_index: int,
    ) -> list[dict[str, Any]]:
        """Call an API function with retry logic and timeout handling."""
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                result = await asyncio.wait_for(
                    func(client, query),
                    timeout=_TIMEOUT + 5,  # slightly above httpx timeout
                )
                return result
            except asyncio.TimeoutError:
                logger.warning(
                    "%s query %d timed out (attempt %d/%d)",
                    api_name, query_index, attempt, _MAX_RETRIES,
                )
            except Exception as exc:
                logger.warning(
                    "%s query %d failed (attempt %d/%d): %s",
                    api_name, query_index, attempt, _MAX_RETRIES, exc,
                )
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_RETRY_DELAY)
        return []

    async def run(self, topic: str, smart_queries: list[str] | None = None) -> dict:
        await self.report("Buscando papers academicos en multiples fuentes...", progress=5)

        # Use smart queries if provided, otherwise fall back to basic variations
        query_variations = smart_queries if smart_queries else self._build_query_variations(topic)
        papers: list[dict[str, Any]] = []
        arxiv_total = 0
        ss_total = 0
        cr_total = 0

        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            # Search arXiv with multiple queries
            await self.report("Buscando en arXiv (multiples queries)...", progress=8)
            for i, q in enumerate(query_variations[:4]):
                result = await self._call_with_retry(
                    self._search_arxiv, client, q, "arXiv", i + 1,
                )
                papers.extend(result)
                arxiv_total += len(result)
                await self.report(f"arXiv query {i+1}/4: {len(result)} papers", progress=8 + i * 3)

            logger.info("arXiv total: %d papers", arxiv_total)
            await self.report(f"arXiv completado: {arxiv_total} papers encontrados.", progress=20)

            # Search Semantic Scholar with multiple queries
            await self.report("Buscando en Semantic Scholar...", progress=22)
            for i, q in enumerate(query_variations[:3]):
                result = await self._call_with_retry(
                    self._search_semantic_scholar, client, q, "SemanticScholar", i + 1,
                )
                papers.extend(result)
                ss_total += len(result)
                await self.report(f"Semantic Scholar query {i+1}/3: {len(result)} papers", progress=22 + i * 3)
                await asyncio.sleep(1)  # rate limit

            logger.info("Semantic Scholar total: %d papers", ss_total)
            await self.report(f"Semantic Scholar completado: {ss_total} papers encontrados.", progress=30)

            # CrossRef with multiple queries
            await self.report("Buscando en CrossRef...", progress=32)
            for i, q in enumerate(query_variations[:3]):
                result = await self._call_with_retry(
                    self._search_crossref, client, q, "CrossRef", i + 1,
                )
                papers.extend(result)
                cr_total += len(result)
                await self.report(f"CrossRef query {i+1}/3: {len(result)} papers", progress=32 + i * 3)

            logger.info("CrossRef total: %d papers", cr_total)
            await self.report(f"CrossRef completado: {cr_total} papers encontrados.", progress=40)

        papers = self._deduplicate(papers)

        summary = "\n\n".join(
            f"- [{p['title']}] ({p.get('year', '?')}): {p.get('abstract', '')[:800]}"
            for p in papers
        )

        logger.info(
            "Academic search complete: arXiv=%d, SemanticScholar=%d, CrossRef=%d, unique=%d",
            arxiv_total, ss_total, cr_total, len(papers),
        )
        await self.report(
            f"Busqueda academica completada: {len(papers)} papers unicos "
            f"(arXiv: {arxiv_total}, SS: {ss_total}, CrossRef: {cr_total}).",
            progress=45,
        )
        return {"papers": papers, "summary": summary}

    @staticmethod
    def _build_query_variations(topic: str) -> list[str]:
        return [
            topic,
            f"{topic} review",
            f"{topic} recent advances",
            f"{topic} meta-analysis",
            f"{topic} experimental results",
        ]

    async def _search_arxiv(self, client: httpx.AsyncClient, topic: str) -> list[dict[str, Any]]:
        encoded = quote_plus(topic)
        url = f"https://export.arxiv.org/api/query?search_query=all:{encoded}&max_results=20&sortBy=relevance"
        resp = await client.get(url)
        resp.raise_for_status()

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(resp.text)
        papers: list[dict[str, Any]] = []

        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            abstract_el = entry.find("atom:summary", ns)
            published_el = entry.find("atom:published", ns)
            link_el = entry.find("atom:id", ns)

            authors: list[str] = []
            for author_el in entry.findall("atom:author", ns):
                name_el = author_el.find("atom:name", ns)
                if name_el is not None and name_el.text:
                    authors.append(name_el.text.strip())

            year = ""
            if published_el is not None and published_el.text:
                year = published_el.text[:4]

            papers.append({
                "title": (title_el.text or "").strip() if title_el is not None else "",
                "authors": ", ".join(authors),
                "year": year,
                "abstract": (abstract_el.text or "").strip() if abstract_el is not None else "",
                "source": "arXiv",
                "url": (link_el.text or "").strip() if link_el is not None else "",
            })

        return papers

    async def _search_semantic_scholar(self, client: httpx.AsyncClient, topic: str) -> list[dict[str, Any]]:
        encoded = quote_plus(topic)
        url = (
            f"https://api.semanticscholar.org/graph/v1/paper/search"
            f"?query={encoded}&limit=20"
            f"&fields=title,abstract,authors,year,citationCount,url,externalIds"
        )
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

        papers: list[dict[str, Any]] = []
        for item in data.get("data", []):
            authors_list = item.get("authors") or []
            authors_str = ", ".join(a.get("name", "") for a in authors_list)

            doi = ""
            ext = item.get("externalIds") or {}
            if isinstance(ext, dict):
                doi = ext.get("DOI", "")

            papers.append({
                "title": item.get("title", ""),
                "authors": authors_str,
                "year": str(item.get("year", "")),
                "abstract": item.get("abstract") or "",
                "source": "Semantic Scholar",
                "url": item.get("url") or (f"https://doi.org/{doi}" if doi else ""),
            })

        return papers

    async def _search_crossref(self, client: httpx.AsyncClient, topic: str) -> list[dict[str, Any]]:
        encoded = quote_plus(topic)
        url = (
            f"https://api.crossref.org/works"
            f"?query={encoded}&rows=15"
            f"&select=DOI,title,author,published-print,abstract"
        )
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

        papers: list[dict[str, Any]] = []
        for item in data.get("message", {}).get("items", []):
            titles = item.get("title") or []
            title = titles[0] if titles else ""

            author_list = item.get("author") or []
            authors_str = ", ".join(
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in author_list
            )

            pub = item.get("published-print") or {}
            date_parts = pub.get("date-parts", [[]])
            year = str(date_parts[0][0]) if date_parts and date_parts[0] else ""

            doi = item.get("DOI", "")

            papers.append({
                "title": title,
                "authors": authors_str,
                "year": year,
                "abstract": item.get("abstract") or "",
                "source": "CrossRef",
                "url": f"https://doi.org/{doi}" if doi else "",
            })

        return papers

    @staticmethod
    def _deduplicate(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for p in papers:
            key = p.get("title", "").lower().strip()[:80]
            if key and key not in seen:
                seen.add(key)
                unique.append(p)
        return unique
