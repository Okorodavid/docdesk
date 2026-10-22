"""Docs ingestion: crawl a docs site (GitBook, Mintlify, Docusaurus...) or read a folder
of Markdown files, split pages into sections with deep links, and index them."""

from __future__ import annotations

import re
import time
import urllib.robotparser
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .store import Chunk, Store

USER_AGENT = "CommunityOpsAgent/0.1 (docs indexer)"
SKIP_EXT = re.compile(
    r"\.(png|jpe?g|gif|svg|webp|ico|pdf|zip|gz|tar|mp4|mov|webm|mp3|woff2?|ttf|css|js|json|xml|txt)$",
    re.I,
)
DROP_TAGS = ["script", "style", "noscript", "nav", "footer", "header", "aside", "svg", "form", "button", "iframe"]
HEADINGS = ["h1", "h2", "h3", "h4"]
BLOCKS = ["p", "li", "pre", "td", "th", "blockquote", "dd", "dt"]
MD_EXT = {".md", ".mdx", ".markdown", ".txt"}


@dataclass
class Section:
    heading: str
    anchor: str
    text: str


# ---------------------------------------------------------------- parsing

def _clean(text: str) -> str:
    return re.sub(r"[ \t ]+", " ", text).strip()


def _anchor_for(tag) -> str:
    if tag.get("id"):
        return tag["id"]
    inner = tag.find(attrs={"id": True})
    if inner is not None:
        return inner["id"]
    link = tag.find("a", href=re.compile(r"^#"))
    return link["href"][1:] if link is not None else ""


def html_to_sections(html: str) -> tuple[str, list[Section]]:
    """Return the page title and its text split at h1-h4 headings."""
    soup = BeautifulSoup(html, "lxml")
    title = _clean(soup.title.get_text()) if soup.title else ""
    for tag in soup(DROP_TAGS):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    if not title:
        h1 = root.find("h1")
        title = _clean(h1.get_text()) if h1 else ""

    sections: list[Section] = []
    current = Section(heading="", anchor="", text="")
    parts: list[str] = []
    wanted = HEADINGS + BLOCKS
    for el in root.find_all(wanted):
        if el.name in HEADINGS:
            if parts:
                current.text = "\n".join(parts)
                sections.append(current)
            current = Section(heading=_clean(el.get_text(" ")), anchor=_anchor_for(el), text="")
            parts = []
            continue
        # Skip blocks nested inside another captured block: the parent's text includes them.
        if el.find_parent(BLOCKS) is not None:
            continue
        text = el.get_text("\n") if el.name == "pre" else _clean(el.get_text(" "))
        if text.strip():
            parts.append(("- " + text) if el.name == "li" else text)
    if parts:
        current.text = "\n".join(parts)
        sections.append(current)
    if not sections:  # pages built from bare divs: fall back to all visible text
        text = "\n".join(line for line in (_clean(x) for x in root.get_text("\n").splitlines()) if line)
        if text:
            sections.append(Section(heading=title, anchor="", text=text))
    return title, sections


def slugify(heading: str) -> str:
    """GitHub-style heading anchor."""
    slug = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return re.sub(r" ", "-", slug)


def markdown_to_sections(md: str) -> tuple[str, list[Section]]:
    title = ""
    front = re.match(r"^---\s*\n(.*?)\n---\s*\n", md, re.S)
    if front:
        m = re.search(r"^title:\s*['\"]?(.+?)['\"]?\s*$", front.group(1), re.M)
        title = m.group(1) if m else ""
        md = md[front.end():]
    sections: list[Section] = []
    current = Section("", "", "")
    lines: list[str] = []
    in_code = False
    for line in md.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        m = None if in_code else re.match(r"^(#{1,4})\s+(.+?)\s*#*\s*$", line)
        if m:
            if any(x.strip() for x in lines):
                current.text = "\n".join(lines).strip()
                sections.append(current)
            heading = m.group(2)
            if not title and len(m.group(1)) == 1:
                title = heading
            current = Section(heading, slugify(heading), "")
            lines = []
        else:
            lines.append(line)
    if any(x.strip() for x in lines):
        current.text = "\n".join(lines).strip()
        sections.append(current)
    return title, sections


def chunk_sections(
    sections: Iterable[Section], title: str, page_url: str, max_chars: int = 1200
) -> list[Chunk]:
    """Split sections into chunks of at most ~max_chars, each linked to its section."""
    chunks: list[Chunk] = []
    for sec in sections:
        url = f"{page_url}#{sec.anchor}" if sec.anchor else page_url
        paras = [p for p in re.split(r"\n{2,}|\n(?=- )", sec.text) if p.strip()] or [sec.text]
        buf = ""
        for para in paras:
            while len(para) > max_chars:  # one huge paragraph: split at a line break or space
                if buf:
                    chunks.append(Chunk(buf.strip(), title, sec.heading, url, page_url))
                    buf = ""
                cut = max(para.rfind("\n", 0, max_chars), para.rfind(" ", 0, max_chars))
                if cut < max_chars // 2:
                    cut = max_chars
                chunks.append(Chunk(para[:cut].strip(), title, sec.heading, url, page_url))
                para = para[cut:].lstrip()
            if buf and len(buf) + len(para) + 1 > max_chars:
                chunks.append(Chunk(buf.strip(), title, sec.heading, url, page_url))
                buf = ""
            buf = f"{buf}\n{para}" if buf else para
        if buf.strip():
            chunks.append(Chunk(buf.strip(), title, sec.heading, url, page_url))
    return [c for c in chunks if len(c.text) >= 20 or c.heading]


# ---------------------------------------------------------------- crawling

def normalize(url: str) -> str:
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def in_scope(url: str, start: str) -> bool:
    u, s = urlparse(url), urlparse(start)
    if u.scheme not in {"http", "https"} or u.netloc != s.netloc:
        return False
    prefix = s.path.rstrip("/")
    return (u.path == prefix or u.path.startswith(prefix + "/") or not prefix) and not SKIP_EXT.search(u.path)


def sitemap_urls(client: httpx.Client, start: str, limit: int = 2000) -> list[str]:
    """Docs platforms usually publish /sitemap.xml; use it to seed the crawl."""
    origin = "{0.scheme}://{0.netloc}".format(urlparse(start))
    found: list[str] = []
    queue = [origin + "/sitemap.xml"]
    seen: set[str] = set()
    while queue and len(found) < limit:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        try:
            resp = client.get(sm)
        except httpx.HTTPError:
            continue
        if resp.status_code != 200:
            continue
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", resp.text)
        for loc in locs:
            if loc.endswith(".xml"):
                queue.append(loc)
            elif in_scope(loc, start):
                found.append(normalize(loc))
    return found


def resolve_scope(client: httpx.Client, start: str, log: Callable[[str], None] = print) -> str:
    """Docs sites often redirect to another host (docs.x.org -> developers.x.org/docs/...).
    If the start URL lands on a different host, scope the crawl to that host's first path segment."""
    try:
        resp = client.get(start)
    except httpx.HTTPError:
        return start
    final = normalize(str(resp.url))
    f = urlparse(final)
    if f.netloc == urlparse(start).netloc:
        return start
    first = f.path.strip("/").split("/")[0]
    scope = f"{f.scheme}://{f.netloc}" + (f"/{first}" if first else "")
    log(f"start URL redirected to {final}; crawling everything under {scope} (override with --scope)")
    return scope


def crawl(
    start_url: str,
    max_pages: int = 150,
    delay: float = 0.3,
    client: httpx.Client | None = None,
    log: Callable[[str], None] = print,
    scope_url: str | None = None,
) -> Iterable[tuple[str, str]]:
    """Yield (url, html) for pages under the scope URL, breadth first, honoring robots.txt."""
    own = client is None
    client = client or httpx.Client(
        headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=20.0
    )
    start = normalize(scope_url) if scope_url else resolve_scope(client, normalize(start_url), log)
    robots = urllib.robotparser.RobotFileParser()
    try:
        r = client.get("{0.scheme}://{0.netloc}/robots.txt".format(urlparse(start)))
        robots.parse(r.text.splitlines() if r.status_code == 200 else [])
    except httpx.HTTPError:
        robots.parse([])

    queue: deque[str] = deque([normalize(start_url)])
    if start != normalize(start_url):
        queue.append(start)
    for url in sitemap_urls(client, start):
        queue.append(url)
    seen: set[str] = set()
    pages = 0
    try:
        while queue and pages < max_pages:
            url = queue.popleft()
            if url in seen:
                continue
            seen.add(url)
            if not robots.can_fetch(USER_AGENT, url):
                log(f"skip (robots.txt): {url}")
                continue
            try:
                resp = client.get(url)
            except httpx.HTTPError as exc:
                log(f"error: {url}: {exc}")
                continue
            if resp.status_code != 200 or "html" not in resp.headers.get("content-type", ""):
                continue
            final = normalize(str(resp.url))
            if not in_scope(final, start) or (final != url and final in seen):
                continue
            seen.add(final)
            pages += 1
            yield final, resp.text
            for a in BeautifulSoup(resp.text, "lxml").find_all("a", href=True):
                link = normalize(urljoin(final, a["href"]))
                if link not in seen and in_scope(link, start):
                    queue.append(link)
            if delay:
                time.sleep(delay)
    finally:
        if own:
            client.close()


# ---------------------------------------------------------------- entry points

def ingest_url(
    store: Store, start_url: str, max_pages: int = 150, client: httpx.Client | None = None,
    log: Callable[[str], None] = print, delay: float = 0.3, scope_url: str | None = None,
) -> tuple[int, int]:
    pages = chunks = 0
    for url, html in crawl(start_url, max_pages=max_pages, client=client, log=log, delay=delay, scope_url=scope_url):
        title, sections = html_to_sections(html)
        page_chunks = chunk_sections(sections, title, url)
        if not page_chunks:
            continue
        store.replace_source(url, title, page_chunks)
        pages += 1
        chunks += len(page_chunks)
        log(f"indexed {len(page_chunks):3d} chunks  {url}")
    return pages, chunks


def ingest_dir(
    store: Store, folder: str | Path, base_url: str | None = None, log: Callable[[str], None] = print
) -> tuple[int, int]:
    """Index Markdown files. With base_url, citations link to base_url/<relative path>."""
    folder = Path(folder)
    pages = chunks = 0
    for path in sorted(p for p in folder.rglob("*") if p.suffix.lower() in MD_EXT and p.is_file()):
        rel = path.relative_to(folder).as_posix()
        page_url = f"{base_url.rstrip('/')}/{rel}" if base_url else path.resolve().as_uri()
        title, sections = markdown_to_sections(path.read_text(encoding="utf-8", errors="replace"))
        page_chunks = chunk_sections(sections, title or path.stem, page_url)
        if not page_chunks:
            continue
        store.replace_source(page_url, title or path.stem, page_chunks)
        pages += 1
        chunks += len(page_chunks)
        log(f"indexed {len(page_chunks):3d} chunks  {rel}")
    return pages, chunks
