"""Small browsing tasks: search the web (DuckDuckGo's HTML results page) and open public pages.

Guards, all in this file:
- Only http/https on the standard ports, and only hosts whose every address is a public internet
  address: never this computer, the home network or cloud metadata (checked again on every
  redirect). This stops a page or a planted note from pointing the assistant at the app's own
  API or a router.
- Read at most 2 MB of HTML or plain text, with a 15 s timeout, no cookies, no scripts run.
- Pages come back as plain text (at most ~5,000 characters) plus a few links to follow.
Everything returned is untrusted: agent.py scans it, wraps it and treats it like a file read,
and once the user's files are in a chat these tools need approval (a URL can carry data out).

DNS rebinding: the name is resolved once, every address is checked, and the connection goes to
that checked address (the real name still goes in the Host header and in TLS, so certificates are
verified against it). A hostile DNS server can't answer "public" for the check and "private" for
the connection, because there is no second lookup. Proxy settings from the environment are
ignored for the same reason: a proxy would connect wherever it liked.
"""

from __future__ import annotations

import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from backend.core.config import Settings
from backend.services.http import tls_context
from backend.services.tools import ToolError, ToolResult
from backend.services.web import MAX_QUERY_CHARS, USER_AGENT

SEARCH_URL = "https://html.duckduckgo.com/html/"
MAX_URL_CHARS = 2000
MAX_BYTES = 2_000_000
MAX_TEXT_CHARS = 5000
MAX_LINKS = 15
MAX_REDIRECTS = 5
TEXT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")


# ---------- address checks ----------


def _public_addresses(host: str) -> str:
    """Raise unless every address the host resolves to is on the public internet; return one."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ToolError(f"Couldn't find the site {host}.") from exc
    addresses = [ipaddress.ip_address(info[4][0].split("%")[0]) for info in infos]
    if not addresses:
        raise ToolError(f"Couldn't find the site {host}.")
    for address in addresses:
        if not address.is_global or address.is_multicast:
            raise ToolError("That address is on this computer or a private network, so it's blocked.")
    return str(addresses[0])


def check_url(url: str) -> str:
    return _checked(url)[0]


def _checked(url: str) -> tuple[str, str]:
    """(url, the public address it was checked against). Connect to that address, not the name."""
    url = url.strip()
    if len(url) > MAX_URL_CHARS:
        raise ToolError("That link is too long.")
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ToolError("Only http:// and https:// web pages can be opened.")
    if parts.username or parts.password:
        raise ToolError("Links with a user name or password in them aren't opened.")
    if parts.port not in (None, 80, 443):
        raise ToolError("Only web pages on the standard ports (80 and 443) can be opened.")
    return url, _public_addresses(parts.hostname)


def _pinned(url: str, address: str) -> tuple[str, dict, dict]:
    """The request URL with the host replaced by the checked address, plus the Host header and
    the TLS name, so the server and its certificate are still checked against the real name."""
    parts = urlparse(url)
    ip = f"[{address}]" if ":" in address else address
    netloc = f"{ip}:{parts.port}" if parts.port else ip
    host = parts.hostname + (f":{parts.port}" if parts.port else "")
    extensions = {"sni_hostname": parts.hostname} if parts.scheme == "https" else {}
    return parts._replace(netloc=netloc).geturl(), {"Host": host}, extensions


# ---------- fetching ----------


def _fetch(url: str, *, data: dict | None = None) -> tuple[str, str, str]:
    """GET (or POST data) with every redirect re-checked. Returns (final url, content type, text)."""
    with httpx.Client(timeout=15, verify=tls_context(), follow_redirects=False, trust_env=False,
                      headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9"}) as client:
        for _ in range(MAX_REDIRECTS + 1):
            url, address = _checked(url)
            target, headers, extensions = _pinned(url, address)
            method = "POST" if data is not None else "GET"
            with client.stream(method, target, data=data, headers=headers, extensions=extensions) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    data = None  # a redirect after a POST is followed as a GET
                    continue
                if response.status_code >= 400:
                    raise ToolError(f"The site answered with error {response.status_code}.")
                kind = response.headers.get("content-type", "").split(";")[0].strip().lower()
                if kind and kind not in TEXT_TYPES:
                    raise ToolError(f"That link is a {kind} file, not a web page.")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        break
                # The URL by name, not the address it was fetched from.
                return url, kind, bytes(body[:MAX_BYTES]).decode(response.encoding or "utf-8", "replace")
        raise ToolError("The page redirected too many times.")


# ---------- reading HTML ----------

SKIP = {"script", "style", "noscript", "svg", "template", "iframe", "head", "nav", "footer", "form", "button", "select"}
BLOCKS = {"p", "div", "section", "article", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol", "pre"}


class PageReader(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base, self.title, self.parts, self.links = base, "", [], []
        self._skip, self._in_title, self._link = 0, False, None

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag in SKIP:
            self._skip += 1
        if tag in BLOCKS:
            self.parts.append("\n")
        if tag == "a" and not self._skip:
            href = dict(attrs).get("href") or ""
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                self._link = [urljoin(self.base, href), ""]

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in SKIP and self._skip:
            self._skip -= 1
        if tag == "a" and self._link:
            url, text = self._link
            if text.strip() and len(self.links) < 200:
                self.links.append({"text": " ".join(text.split())[:80], "url": url[:500]})
            self._link = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)
            if self._link:
                self._link[1] += data

    def text(self) -> str:
        lines = (" ".join(line.split()) for line in "".join(self.parts).splitlines())
        return "\n".join(line for line in lines if line)


class SearchReader(HTMLParser):
    """DuckDuckGo's HTML results: a.result__a (title + link) followed by a.result__snippet."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results, self._field = [], None

    def handle_starttag(self, tag, attrs):
        classes = (dict(attrs).get("class") or "").split()
        if tag == "a" and "result__a" in classes:
            self.results.append({"title": "", "url": _real_link(dict(attrs).get("href", "")), "snippet": ""})
            self._field = "title"
        elif tag == "a" and "result__snippet" in classes and self.results:
            self._field = "snippet"

    def handle_endtag(self, tag):
        if tag == "a":
            self._field = None

    def handle_data(self, data):
        if self._field and self.results:
            self.results[-1][self._field] += data


def _real_link(href: str) -> str:
    """DuckDuckGo sometimes wraps results as //duckduckgo.com/l/?uddg=<the real url>."""
    parts = urlparse(href if "://" in href else f"https:{href}")
    if parts.hostname and parts.hostname.endswith("duckduckgo.com") and parts.path.startswith("/l/"):
        return parse_qs(parts.query).get("uddg", [href])[0]
    return href


# ---------- the tools ----------


def web_search(settings: Settings, arguments: dict) -> ToolResult:
    query = " ".join(str(arguments.get("query", "")).split())
    if not query:
        raise ToolError("A query is required.")
    if len(query) > MAX_QUERY_CHARS:
        raise ToolError(f"The query is too long (over {MAX_QUERY_CHARS} characters).")
    try:
        _, _, html = _fetch(SEARCH_URL, data={"q": query})
    except httpx.HTTPError as exc:
        raise ToolError("Web search couldn't be reached. Check the internet connection.") from exc
    reader = SearchReader()
    reader.feed(html)
    results = [
        {"title": " ".join(r["title"].split()), "url": r["url"], "snippet": " ".join(r["snippet"].split())[:300]}
        for r in reader.results if r["url"].startswith(("http://", "https://"))
    ][:6]
    if not results:
        return ToolResult(f"No web results for “{query}”.", {"query": query, "results": []})
    return ToolResult(
        f"Searched the web for “{query}” ({len(results)} results). First: {results[0]['title']}",
        {"query": query, "results": results, "source": "DuckDuckGo"},
    )


def open_page(settings: Settings, arguments: dict) -> ToolResult:
    url = check_url(str(arguments.get("url", "")))
    try:
        final, kind, body = _fetch(url)
    except httpx.HTTPError as exc:
        raise ToolError(f"Couldn't open the page ({type(exc).__name__}).") from exc
    if kind == "text/plain":
        title, text, links = urlparse(final).path.rsplit("/", 1)[-1] or final, body, []
    else:
        reader = PageReader(final)
        reader.feed(body)
        title, text, links = " ".join(reader.title.split()), reader.text(), reader.links
    cut = len(text) > MAX_TEXT_CHARS
    page = {
        "url": final, "title": title[:200], "text": text[:MAX_TEXT_CHARS] + ("\n[…cut: the page continues]" if cut else ""),
        "links": [link for link in links if link["url"].startswith(("http://", "https://"))][:MAX_LINKS],
    }
    gist = " ".join(text.split())[:160]
    return ToolResult(f"Opened {title[:80] or final}: {gist}…", page)
