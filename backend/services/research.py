import asyncio
import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from backend.services.web import USER_AGENT


class ResearchUnavailable(RuntimeError):
    pass


class WikipediaResearch:
    api_url = "https://en.wikipedia.org/w/api.php"

    async def collect(self, query: str, limit: int) -> list[dict[str, str]]:
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrlimit": limit,
            "prop": "extracts|info",
            "exintro": 1,
            "explaintext": 1,
            "inprop": "url",
            "format": "json",
            "formatversion": 2,
        }
        try:
            payload = await asyncio.to_thread(self._fetch, params)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise ResearchUnavailable("The free research source is currently unavailable.") from exc
        pages = payload.get("query", {}).get("pages", [])
        sources = []
        for page in pages:
            title = page.get("title", "Untitled")
            excerpt = page.get("extract", "").strip()
            if not excerpt:
                continue
            sources.append(
                {
                    "title": title,
                    "url": page.get(
                        "fullurl", f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
                    ),
                    "excerpt": excerpt[:4_000],
                }
            )
        if not sources:
            raise ResearchUnavailable("No relevant research sources were found.")
        return sources

    def _fetch(self, params: dict) -> dict:
        request = Request(
            f"{self.api_url}?{urlencode(params)}",
            headers={"User-Agent": USER_AGENT},
        )
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
