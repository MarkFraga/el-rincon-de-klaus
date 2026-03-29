from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from backend.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT = 12
_MAX_CONTENT_CHARS = 3000
_MAX_FORUM_CHARS = 5000  # Forums get more space -- discussion content is richer

# Domains that are forums/discussion sites
_FORUM_DOMAINS = {
    "reddit.com", "old.reddit.com", "www.reddit.com",
    "quora.com", "www.quora.com", "es.quora.com",
    "forocoches.com", "www.forocoches.com",
    "burbuja.info", "www.burbuja.info",
    "mediavida.com", "www.mediavida.com",
    "stackexchange.com", "stackoverflow.com",
}


def _is_forum_url(url: str) -> bool:
    try:
        domain = urlparse(url).netloc.lower()
        return any(domain.endswith(fd) for fd in _FORUM_DOMAINS)
    except Exception:
        return False


def _is_reddit_url(url: str) -> bool:
    try:
        domain = urlparse(url).netloc.lower()
        return "reddit.com" in domain
    except Exception:
        return False


class WebSearchAgent(BaseAgent):
    """Agent 1 -- massive general web search via DuckDuckGo with forum awareness."""

    def __init__(self, job_id: str):
        super().__init__(name="web_search", job_id=job_id)

    async def run(self, topic: str, smart_queries: list[str] | None = None) -> dict:
        await self.report("Iniciando busqueda web...", progress=5)

        queries = smart_queries if smart_queries else self._build_queries(topic)
        raw_results: list[dict[str, Any]] = []

        # Reuse a single DDGS instance to avoid rate-limit issues
        try:
            from duckduckgo_search import DDGS
            ddgs = DDGS()
        except Exception as exc:
            logger.error("Failed to init DuckDuckGo: %s", exc)
            await self.report("Error inicializando DuckDuckGo, reintentando...", progress=6)
            await asyncio.sleep(2)
            try:
                from duckduckgo_search import DDGS
                ddgs = DDGS()
            except Exception:
                await self.report("DuckDuckGo no disponible, saltando busqueda web.", progress=45)
                return {"sources": [], "summary": ""}

        for idx, query in enumerate(queries):
            pct = 5 + int((idx / len(queries)) * 25)
            await self.report(f"Buscando ({idx+1}/{len(queries)}): {query[:50]}...", progress=pct)

            for attempt in range(2):
                try:
                    hits = await asyncio.to_thread(ddgs.text, query, max_results=15)
                    if hits:
                        raw_results.extend(hits)
                        logger.info("Web query '%s': %d results", query[:40], len(hits))
                    break
                except Exception as exc:
                    logger.warning("DDG query attempt %d failed (%s): %s", attempt + 1, query[:40], exc)
                    if attempt == 0:
                        await asyncio.sleep(2)
                    else:
                        logger.error("DDG query permanently failed: %s", query[:40])

            await asyncio.sleep(0.8)

        await self.report(f"Encontrados {len(raw_results)} resultados brutos", progress=32)

        # Deduplicate
        seen_urls: set[str] = set()
        unique: list[dict[str, Any]] = []
        for r in raw_results:
            url = r.get("href") or r.get("link") or ""
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique.append(r)

        await self.report(f"Extrayendo contenido de {len(unique)} fuentes...", progress=35)

        sources: list[dict[str, str]] = []
        for batch_start in range(0, len(unique), 8):
            batch = unique[batch_start:batch_start + 8]
            tasks = [self._extract(r) for r in batch]
            extracted = await asyncio.gather(*tasks, return_exceptions=True)
            for item in extracted:
                if isinstance(item, dict) and item.get("content"):
                    sources.append(item)

        summary = "\n\n---\n\n".join(
            f"## {s['title']}\n{s['content']}" for s in sources
        )

        await self.report(f"Busqueda web completada: {len(sources)} fuentes utiles.", progress=45)
        logger.info("WebSearchAgent finished: %d sources from %d queries", len(sources), len(queries))
        return {"sources": sources, "summary": summary}

    @staticmethod
    def _build_queries(topic: str) -> list[str]:
        """Fallback queries when no smart queries are provided."""
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

        # Route to specialized extractor based on URL type
        if _is_reddit_url(url):
            return await self._extract_reddit(url, title)
        if _is_forum_url(url):
            return await self._extract_forum(url, title)
        return await self._extract_standard(url, title)

    async def _extract_standard(self, url: str, title: str) -> dict[str, str]:
        """Standard page extraction."""
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
            logger.debug("Standard extraction failed for %s: %s", url, exc)
            return {}

    async def _extract_reddit(self, url: str, title: str) -> dict[str, str]:
        """Extract Reddit post + top comments via JSON API."""
        try:
            # Convert to JSON endpoint
            json_url = re.sub(r'/?(\?.*)?$', '.json', url.split('?')[0])
            if not json_url.endswith('.json'):
                json_url += '.json'

            async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(
                    json_url,
                    headers={"User-Agent": "Mozilla/5.0 (podcast-research-bot)"},
                )
                if resp.status_code != 200:
                    # Fallback to standard extraction
                    return await self._extract_standard(url, title)

                data = resp.json()

            if not isinstance(data, list) or len(data) < 2:
                return await self._extract_standard(url, title)

            # Extract post content
            post_data = data[0].get("data", {}).get("children", [{}])[0].get("data", {})
            post_title = post_data.get("title", title)
            post_body = post_data.get("selftext", "")
            subreddit = post_data.get("subreddit", "")
            score = post_data.get("score", 0)

            parts = [f"[Reddit r/{subreddit} | Score: {score}]", post_title]
            if post_body:
                parts.append(post_body[:1500])

            # Extract top comments (sorted by score)
            comments_data = data[1].get("data", {}).get("children", [])
            comment_texts = []
            for c in comments_data[:15]:
                cd = c.get("data", {})
                body = cd.get("body", "")
                cscore = cd.get("score", 0)
                if body and cscore > 1 and body != "[deleted]" and body != "[removed]":
                    comment_texts.append(f"[+{cscore}] {body[:500]}")

            if comment_texts:
                parts.append("\n--- MEJORES COMENTARIOS ---")
                parts.extend(comment_texts)

            content = "\n\n".join(parts)

            return {
                "title": f"[Reddit] {post_title}",
                "url": url,
                "content": content[:_MAX_FORUM_CHARS],
                "source_type": "forum",
            }
        except Exception as exc:
            logger.debug("Reddit extraction failed for %s: %s", url, exc)
            return await self._extract_standard(url, title)

    async def _extract_forum(self, url: str, title: str) -> dict[str, str]:
        """Extract forum thread content with replies."""
        try:
            async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code != 200:
                    return {}
                html = resp.text

            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
                tag.decompose()

            # Try to find post/reply containers (common forum patterns)
            posts = []
            # Discourse / phpBB / vBulletin / generic patterns
            for selector in [
                "div.post", "div.message", "article.post",
                "div.post-content", "div.messageContent",
                "div.bbp-reply-content", "div.entry-content",
                "div.answer", "div.reply",
            ]:
                found = soup.select(selector)
                if found:
                    posts = found
                    break

            if posts:
                parts = [f"[Foro] {title}"]
                for p in posts[:10]:
                    text = p.get_text(separator="\n", strip=True)
                    if text and len(text) > 30:
                        parts.append(text[:800])
                content = "\n\n---\n\n".join(parts)
            else:
                # Fallback to full page text
                text = soup.get_text(separator="\n", strip=True)
                if not text or len(text) < 100:
                    return {}
                content = f"[Foro] {title}\n\n{text}"

            return {
                "title": f"[Foro] {title}",
                "url": url,
                "content": content[:_MAX_FORUM_CHARS],
                "source_type": "forum",
            }
        except Exception as exc:
            logger.debug("Forum extraction failed for %s: %s", url, exc)
            return {}
