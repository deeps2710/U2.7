from __future__ import annotations

import html
import base64
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from typing import Any


DEFAULT_TIMEOUT_SECONDS = 8.0
MAX_QUERY_LENGTH = 180


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class WebSearchResponse:
    status: str
    query: str
    answer: str
    results: tuple[WebSearchResult, ...] = ()
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["results"] = [item.to_dict() for item in self.results]
        return payload


def search_web(query: str, *, limit: int = 3, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> WebSearchResponse:
    clean_query = normalize_query(query)
    if not clean_query:
        return WebSearchResponse("blocked", clean_query, "I need a specific search query before I can look that up.")

    try:
        bounded_limit = max(1, min(limit, 5))
        if _needs_current_search(clean_query):
            results = _search_bing(clean_query, limit=bounded_limit, timeout=timeout)
            if not results:
                results = _search_duckduckgo(clean_query, limit=bounded_limit, timeout=timeout)
            if not results:
                results = _search_wikipedia(clean_query, limit=bounded_limit, timeout=timeout)
        else:
            results = _search_wikipedia(clean_query, limit=bounded_limit, timeout=timeout)
            if not results:
                results = _search_bing(clean_query, limit=bounded_limit, timeout=timeout)
            if not results:
                results = _search_duckduckgo(clean_query, limit=bounded_limit, timeout=timeout)
    except Exception as exc:
        return WebSearchResponse(
            "error",
            clean_query,
            f"I could not reach the web search provider right now: {exc}",
            error=str(exc),
        )

    if not results:
        return WebSearchResponse("not_found", clean_query, f"I searched for {clean_query}, but I did not find useful results.")

    answer = summarize_results(clean_query, results)
    return WebSearchResponse("success", clean_query, answer, tuple(results))


def summarize_results(query: str, results: list[WebSearchResult]) -> str:
    lines = [f"I found this on the web for {query}:"]
    for index, result in enumerate(results[:3], start=1):
        detail = f"{index}. {result.title}"
        if result.snippet:
            detail += f" - {result.snippet}"
        lines.append(detail)
    lines.append("Sources: " + "; ".join(result.url for result in results[:3]))
    return "\n".join(lines)


def normalize_query(query: str) -> str:
    clean = " ".join(str(query or "").strip().split())
    return clean[:MAX_QUERY_LENGTH]


def _needs_current_search(query: str) -> bool:
    return bool(re.search(r"\b(latest|current|today|news|weather|price|score|stock|202\d|now)\b", query, flags=re.IGNORECASE))


def _search_duckduckgo(query: str, *, limit: int, timeout: float) -> list[WebSearchResult]:
    params = urllib.parse.urlencode({"q": query, "kl": "us-en"})
    url = f"https://duckduckgo.com/html/?{params}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 ULTRON/2.7 local assistant",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        page = response.read().decode("utf-8", errors="replace")

    parser = DuckDuckGoHTMLParser()
    parser.feed(page)
    return parser.results[:limit]


def _search_bing(query: str, *, limit: int, timeout: float) -> list[WebSearchResult]:
    params = urllib.parse.urlencode({"q": query})
    url = f"https://www.bing.com/search?{params}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 ULTRON/2.7 local assistant",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        page = response.read().decode("utf-8", errors="replace")

    results: list[WebSearchResult] = []
    for block in re.findall(r'<li class="b_algo".*?</li>', page, flags=re.IGNORECASE | re.DOTALL):
        link = re.search(r"<h2[^>]*>\s*<a[^>]+href=\"(?P<href>[^\"]+)\"[^>]*>(?P<title>.*?)</a>", block, flags=re.IGNORECASE | re.DOTALL)
        if not link:
            continue
        href = _decode_bing_url(html.unescape(link.group("href")))
        title = _clean_html(link.group("title"))
        snippet_match = re.search(r"<p[^>]*>(?P<snippet>.*?)</p>", block, flags=re.IGNORECASE | re.DOTALL)
        snippet = _clean_html(snippet_match.group("snippet")) if snippet_match else ""
        if title and href and href.startswith(("http://", "https://")) and not any(item.url == href for item in results):
            results.append(WebSearchResult(title=title, url=href, snippet=snippet))
        if len(results) >= limit:
            break
    return results


def _search_wikipedia(query: str, *, limit: int, timeout: float) -> list[WebSearchResult]:
    params = urllib.parse.urlencode(
        {
            "action": "opensearch",
            "search": query,
            "limit": limit,
            "namespace": 0,
            "format": "json",
        }
    )
    url = f"https://en.wikipedia.org/w/api.php?{params}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ULTRON/2.7 local assistant (personal use)"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8", errors="replace")
    import json

    data = json.loads(payload)
    if not isinstance(data, list) or len(data) < 4:
        return []
    titles = data[1] if isinstance(data[1], list) else []
    snippets = data[2] if isinstance(data[2], list) else []
    urls = data[3] if isinstance(data[3], list) else []
    results = []
    for title, snippet, item_url in zip(titles, snippets, urls):
        if isinstance(title, str) and isinstance(item_url, str):
            summary = str(snippet or "").strip() or _wikipedia_summary(title, timeout=timeout)
            results.append(WebSearchResult(title=title, url=item_url, snippet=summary))
    return results[:limit]


def _wikipedia_summary(title: str, *, timeout: float) -> str:
    slug = urllib.parse.quote(title.replace(" ", "_"), safe="")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ULTRON/2.7 local assistant (personal use)", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8", errors="replace")
        import json

        data = json.loads(payload)
    except Exception:
        return ""
    extract = data.get("extract") if isinstance(data, dict) else ""
    return str(extract or "").strip()


class DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[WebSearchResult] = []
        self._in_result_link = False
        self._in_snippet = False
        self._current_href = ""
        self._current_title: list[str] = []
        self._current_snippet: list[str] = []
        self._pending_result: tuple[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        classes = set(attrs_dict.get("class", "").split())
        if tag == "a" and ("result__a" in classes or "result-link" in classes):
            self._in_result_link = True
            self._current_href = attrs_dict.get("href", "")
            self._current_title = []
        elif tag in {"a", "div"} and ("result__snippet" in classes or "result-snippet" in classes):
            self._in_snippet = True
            self._current_snippet = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_result_link:
            title = _clean_text(" ".join(self._current_title))
            url = _decode_duckduckgo_url(self._current_href)
            self._pending_result = (title, url) if title and url else None
            self._in_result_link = False
            self._current_href = ""
            self._current_title = []
        elif tag in {"a", "div"} and self._in_snippet:
            snippet = _clean_text(" ".join(self._current_snippet))
            if self._pending_result:
                title, url = self._pending_result
                if not any(item.url == url for item in self.results):
                    self.results.append(WebSearchResult(title=title, url=url, snippet=snippet))
                self._pending_result = None
            self._in_snippet = False
            self._current_snippet = []

    def handle_data(self, data: str) -> None:
        if self._in_result_link:
            self._current_title.append(data)
        elif self._in_snippet:
            self._current_snippet.append(data)

    def close(self) -> None:
        if self._pending_result:
            title, url = self._pending_result
            if not any(item.url == url for item in self.results):
                self.results.append(WebSearchResult(title=title, url=url))
        super().close()


def _decode_duckduckgo_url(url: str) -> str:
    if not url:
        return ""
    value = html.unescape(url)
    parsed = urllib.parse.urlparse(value)
    query = urllib.parse.parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return query["uddg"][0]
    if value.startswith("//"):
        return "https:" + value
    return value


def _decode_bing_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if "bing.com" not in parsed.netloc:
        return url
    query = urllib.parse.parse_qs(parsed.query)
    encoded = (query.get("u") or [""])[0]
    if not encoded:
        return url
    value = encoded[2:] if encoded.startswith("a1") else encoded
    try:
        padded = value + ("=" * (-len(value) % 4))
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except Exception:
        return url
    return decoded if decoded.startswith(("http://", "https://")) else url


def _clean_text(value: str) -> str:
    text = html.unescape(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _clean_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return _clean_text(text)
