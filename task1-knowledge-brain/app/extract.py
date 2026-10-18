"""Sitemap parsing and article extraction (BeautifulSoup)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def parse_sitemap(xml_text: str) -> tuple[list[dict], list[str]]:
    """Returns (url_entries, child_sitemaps). Handles <urlset> and <sitemapindex>."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"Malformed sitemap XML: {exc}") from exc
    urls, children = [], []
    for el in root:
        loc = (el.findtext(f"{NS}loc") or el.findtext("loc") or "").strip()
        if not loc:
            continue
        if el.tag.endswith("sitemap"):
            children.append(loc)
        elif el.tag.endswith("url"):
            lastmod = (el.findtext(f"{NS}lastmod") or el.findtext("lastmod") or "").strip() or None
            urls.append({"url": loc, "lastmod": lastmod})
    return urls, children


def is_article_url(url: str) -> bool:
    """Heuristic: skip obvious non-article pages (tags, search, login)."""
    return not re.search(r"/(tag|tags|search|login|register|category|categories)(/|$|\?)", url, re.I)


@dataclass
class ExtractedArticle:
    title: str
    content: str
    headings: list[str]
    images: list[dict] = field(default_factory=list)


def extract_article(html: str, page_url: str) -> ExtractedArticle:
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        t.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    h1 = root.find("h1") or soup.find("h1")
    title = (h1.get_text(" ", strip=True) if h1 else (soup.title.get_text(strip=True) if soup.title else "")).strip()
    if not title:
        raise ValueError("No title found")
    headings = [h.get_text(" ", strip=True) for h in root.find_all(["h2", "h3"])]
    images = []
    for img in root.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        fig = img.find_parent("figure")
        cap = fig.find("figcaption").get_text(" ", strip=True) if fig and fig.find("figcaption") else None
        images.append({"url": urljoin(page_url, src), "alt": img.get("alt"), "caption": cap})
    for fc in root.find_all("figcaption"):
        fc.decompose()
    blocks = []
    for el in root.find_all(["h2", "h3", "p", "li", "pre"]):
        txt = el.get_text(" ", strip=True)
        if txt and txt != title:
            blocks.append(txt)
    content = "\n".join(blocks).strip()
    if len(content) < 20:
        raise ValueError("Article body too short")
    return ExtractedArticle(title, content, headings, images)
