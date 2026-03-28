from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote_plus

import httpx

from backend.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

_TIMEOUT = 15  # seconds


class AcademicAgent(BaseAgent):
    """Agent 3 -- searches arXiv, Semantic Scholar and CrossRef."""

    def __init__(self, job_id: str):
        super().__init__(name="academic", job_id=job_id)

    # ------------------------------------------------------------------
    async def run(self, topic: str) -> dict:
        await self.report("Buscando papers académicos...", progress=5)

        papers: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            arxiv_task = self._search_arxiv(client, topic)
            ss_task = self._search_semantic_scholar(client, topic)
            cr_task = self._search_crossref(client, topic)

            results = await __import__("asyncio").gather(
                arxiv_task, ss_task, cr_task, return_exceptions=True
            )

        for idx, label in enumerate(["arXiv", "Semantic Scholar", "CrossRef"]):
            if isinstance(results[idx], list):
                papers.extend(results[idx])
                await self.report(
                    f"{label}: {len(results[idx])} resultados", progress=15 + idx * 10
                )
            else:
                logger.warning("%s search failed: %s", label, results[idx])
                await self.report(f"{label}: sin resultados (error)", progress=15 + idx * 10)

        # Deduplicate by normalised title
        papers = self._deduplicate(papers)

        summary = "\n\n".join(
            f"- [{p['title']}] ({p.get('year', '?')}): {p.get('abstract', '')[:500]}"
            for p in papers
        )

        await self.report(
            f"Búsqueda académica completada: {len(papers)} papers.", progress=45
        )

        return {"papers": papers, "summary": summary}

    # ------------------------------------------------------------------
    # arXiv
    # ------------------------------------------------------------------
    async def _search_arxiv(
        self, client: httpx.AsyncClient, topic: str
    ) -> list[dict[str, Any]]:
        encoded = quote_plus(topic)
        url = (
            f"http://export.arxiv.org/api/query"
            f"?search_query=all:{encoded}&max_results=8&sortBy=relevance"
        )
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

    # ------------------------------------------------------------------
    # Semantic Scholar
    # ------------------------------------------------------------------
    async def _search_semantic_scholar(
        self, client: httpx.AsyncClient, topic: str
    ) -> list[dict[str, Any]]:
        encoded = quote_plus(topic)
        url = (
            f"https://api.semanticscholar.org/graph/v1/paper/search"
            f"?query={encoded}&limit=8"
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

    # ------------------------------------------------------------------
    # CrossRef
    # ------------------------------------------------------------------
    async def _search_crossref(
        self, client: httpx.AsyncClient, topic: str
    ) -> list[dict[str, Any]]:
        encoded = quote_plus(topic)
        url = (
            f"https://api.crossref.org/works"
            f"?query={encoded}&rows=5"
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

    # ------------------------------------------------------------------
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
