import httpx

from communityops.ingest import (
    chunk_sections,
    crawl,
    html_to_sections,
    in_scope,
    ingest_dir,
    ingest_url,
    markdown_to_sections,
    normalize,
    slugify,
)
from .conftest import FIXTURES, PAGE_URL


def test_html_sections_keep_content_and_drop_chrome():
    title, sections = html_to_sections((FIXTURES / "bridge.html").read_text(encoding="utf-8"))
    assert title == "Bridge FAQ | Example Protocol Docs"
    text = "\n".join(s.text for s in sections)
    assert "7 days" in text and "Prove" in text and "bridge status --tx 0xabc123" in text
    assert "Twitter" not in text and "Copyright" not in text and "analytics" not in text
    by_heading = {s.heading: s for s in sections}
    assert by_heading["How long do withdrawals take?"].anchor == "withdrawal-time"
    # Anchor found on a link inside the heading.
    assert by_heading["My bridge transaction is stuck pending"].anchor == "stuck-transaction"


def test_chunks_link_to_sections():
    title, sections = html_to_sections((FIXTURES / "bridge.html").read_text(encoding="utf-8"))
    chunks = chunk_sections(sections, title, PAGE_URL)
    urls = {c.url for c in chunks}
    assert f"{PAGE_URL}#withdrawal-time" in urls
    assert f"{PAGE_URL}#fees" in urls
    assert all(c.source == PAGE_URL for c in chunks)


def test_long_sections_are_split_under_limit():
    from communityops.ingest import Section

    para = "word " * 100  # 500 chars
    sec = Section("Big", "big", "\n\n".join([para] * 6))
    chunks = chunk_sections([sec], "T", "https://x.org/p", max_chars=1200)
    assert len(chunks) >= 3
    assert all(len(c.text) <= 1200 for c in chunks)
    huge = Section("Huge", "", "x" * 3000)
    assert all(len(c.text) <= 1200 for c in chunk_sections([huge], "T", "https://x.org/p"))
    # A long single paragraph is cut between words, not inside one.
    words = Section("Words", "", " ".join(f"token{i}" for i in range(600)))
    pieces = chunk_sections([words], "T", "https://x.org/p")
    assert len(pieces) > 1 and all(len(c.text) <= 1200 for c in pieces)
    assert all(c.text.split()[0].startswith("token") and c.text.split()[-1].startswith("token") for c in pieces)
    rebuilt = " ".join(c.text for c in pieces).split()
    assert rebuilt == words.text.split()


def test_markdown_sections_frontmatter_and_code_blocks():
    md = (
        "---\ntitle: Staking guide\n---\n"
        "Intro text about staking.\n\n"
        "## Unstaking period\nUnstaking takes 21 days.\n\n"
        "```bash\n# not a heading\nexample unstake\n```\n"
        "### Rewards & APR\nRewards are paid every epoch.\n"
    )
    title, sections = markdown_to_sections(md)
    assert title == "Staking guide"
    headings = [s.heading for s in sections]
    assert headings == ["", "Unstaking period", "Rewards & APR"]
    assert "# not a heading" in sections[1].text
    assert sections[2].anchor == "rewards--apr"


def test_slugify_matches_github_style():
    assert slugify("How do I bridge USDC?") == "how-do-i-bridge-usdc"


def test_scope_and_normalize():
    start = "https://docs.example.org/docs"
    assert in_scope("https://docs.example.org/docs/bridge", start)
    assert not in_scope("https://docs.example.org/blog/post", start)
    assert not in_scope("https://evil.org/docs/bridge", start)
    assert not in_scope("https://docs.example.org/docs/logo.png", start)
    assert normalize("https://docs.example.org/docs/bridge/#fees") == "https://docs.example.org/docs/bridge"


def _site():
    pages = {
        "/robots.txt": ("text/plain", "User-agent: *\nDisallow: /docs/private\n"),
        "/sitemap.xml": (
            "application/xml",
            "<urlset><url><loc>https://docs.example.org/docs/bridge</loc></url>"
            "<url><loc>https://docs.example.org/blog/news</loc></url></urlset>",
        ),
        "/docs": (
            "text/html",
            '<html><body><main><h1>Docs home</h1><p>Welcome to the Example docs index page.</p>'
            '<a href="/docs/bridge">Bridge</a> <a href="/docs/private/keys">Private</a>'
            '<a href="https://other.org/x">Off-site</a></main></body></html>',
        ),
        "/docs/bridge": ("text/html", (FIXTURES / "bridge.html").read_text(encoding="utf-8")),
        "/docs/private/keys": ("text/html", "<html><body><p>secret page should not be fetched</p></body></html>"),
    }
    fetched = []

    def handler(request: httpx.Request):
        fetched.append(request.url.path)
        if request.url.host != "docs.example.org" or request.url.path not in pages:
            return httpx.Response(404)
        ctype, body = pages[request.url.path]
        return httpx.Response(200, headers={"content-type": ctype}, text=body)

    return httpx.Client(transport=httpx.MockTransport(handler)), fetched


def test_crawl_respects_scope_and_robots():
    client, fetched = _site()
    urls = [u for u, _ in crawl("https://docs.example.org/docs", client=client, delay=0, log=lambda m: None)]
    assert urls == ["https://docs.example.org/docs", "https://docs.example.org/docs/bridge"]
    assert "/docs/private/keys" not in fetched
    assert "/blog/news" not in fetched


def test_crawl_follows_start_redirect_to_another_host():
    page = (FIXTURES / "bridge.html").read_text(encoding="utf-8")

    def handler(request: httpx.Request):
        host, path = request.url.host, request.url.path
        if host == "docs.example.org":
            return httpx.Response(301, headers={"location": "https://developers.example.org/docs/start"})
        if path == "/sitemap.xml":
            return httpx.Response(200, headers={"content-type": "application/xml"},
                                  text="<urlset><url><loc>https://developers.example.org/docs/bridge</loc></url>"
                                       "<url><loc>https://developers.example.org/docs/start</loc></url>"
                                       "<url><loc>https://developers.example.org/pricing</loc></url></urlset>")
        if path in ("/docs/start", "/docs/bridge", "/pricing"):
            return httpx.Response(200, headers={"content-type": "text/html"}, text=page)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    logs = []
    urls = [u for u, _ in crawl("https://docs.example.org/concepts", client=client, delay=0, log=logs.append)]
    assert urls == ["https://developers.example.org/docs/start", "https://developers.example.org/docs/bridge"]
    assert any("redirected" in m for m in logs)
    # An explicit scope overrides the guess.
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    urls = [u for u, _ in crawl("https://developers.example.org/docs/bridge", client=client, delay=0,
                                log=lambda m: None, scope_url="https://developers.example.org/docs/bridge")]
    assert urls == ["https://developers.example.org/docs/bridge"]


def test_ingest_url_end_to_end(store):
    client, _ = _site()
    pages, chunks = ingest_url(store, "https://docs.example.org/docs", client=client, delay=0, log=lambda m: None)
    assert pages == 2 and chunks >= 4
    # Re-ingesting replaces pages instead of duplicating them.
    client, _ = _site()
    ingest_url(store, "https://docs.example.org/docs", client=client, delay=0, log=lambda m: None)
    assert store.doc_counts() == (2, chunks)


def test_ingest_dir_uses_base_url(store, tmp_path):
    (tmp_path / "guides").mkdir()
    (tmp_path / "guides" / "staking.md").write_text("# Staking\n\n## Unstaking\nUnstaking takes 21 days.\n", encoding="utf-8")
    pages, _ = ingest_dir(store, tmp_path, base_url="https://github.com/org/repo/blob/main/docs", log=lambda m: None)
    assert pages == 1
    hit = store.search("unstaking days")[0]
    assert hit.url == "https://github.com/org/repo/blob/main/docs/guides/staking.md#unstaking"
