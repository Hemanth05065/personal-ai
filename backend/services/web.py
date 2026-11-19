"""Free, no-account web lookups: Wikipedia, DuckDuckGo Instant Answers and Open-Meteo weather.

What leaves this computer is only the query (or place name) the model sends, capped in length.
Everything that comes back is untrusted text: agent.py scans it, wraps it as untrusted data, and
treats it like a file read, so Do-it mode asks before any later write. Once files have been read
in a chat, a lookup itself needs approval (a planted note could try to send file text out
inside a search query). ASSISTANT_WEB_LOOKUPS_ENABLED=false removes these tools entirely.
"""

from __future__ import annotations

from datetime import date

import httpx

from backend.core.config import Settings
from backend.services.http import tls_context
from backend.services.tools import ToolError, ToolResult

MAX_QUERY_CHARS = 200
# Wikipedia refuses (403) a User-Agent without a URL in it. This one names no person or repo.
USER_AGENT = "LocalAssistant/0.1 (personal use; https://www.mediawiki.org/wiki/API:Etiquette)"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
DUCKDUCKGO_API = "https://api.duckduckgo.com/"
GEOCODING_API = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_API = "https://api.open-meteo.com/v1/forecast"

# WMO weather codes, as Open-Meteo reports them.
WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains", 80: "light showers",
    81: "showers", 82: "violent showers", 85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with heavy hail",
}


def _get(url: str, params: dict) -> dict:
    """One GET returning JSON. Tests replace this function; nothing else touches the network."""
    with httpx.Client(timeout=10, verify=tls_context(), headers={"User-Agent": USER_AGENT}) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        return response.json()


def _text(arguments: dict, name: str) -> str:
    value = " ".join(str(arguments.get(name, "")).split())
    if not value:
        raise ToolError(f"A {name} is required.")
    if len(value) > MAX_QUERY_CHARS:
        raise ToolError(f"The {name} is too long (over {MAX_QUERY_CHARS} characters).")
    return value


def _wikipedia(query: str) -> list[dict]:
    payload = _get(WIKIPEDIA_API, {
        "action": "query", "generator": "search", "gsrsearch": query, "gsrlimit": 3,
        "prop": "extracts|info", "exintro": 1, "explaintext": 1, "exsentences": 4,
        "inprop": "url", "format": "json", "formatversion": 2,
    })
    pages = sorted(payload.get("query", {}).get("pages", []), key=lambda page: page.get("index", 99))
    return [
        {"source": "Wikipedia", "title": page.get("title", ""), "url": page.get("fullurl", ""),
         "text": page.get("extract", "").strip()[:1200]}
        for page in pages if page.get("extract", "").strip()
    ]


def _duckduckgo(query: str) -> list[dict]:
    payload = _get(DUCKDUCKGO_API, {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1, "no_redirect": 1})
    found = []
    for key, label in (("Answer", "answer"), ("AbstractText", "summary"), ("Definition", "definition")):
        text = str(payload.get(key) or "").strip()
        if text:
            url = payload.get("AbstractURL") or payload.get("DefinitionURL") or "https://duckduckgo.com/"
            found.append({"source": "DuckDuckGo", "title": f"{label}: {payload.get('Heading') or query}",
                          "url": url, "text": text[:1200]})
    return found


def web_lookup(settings: Settings, arguments: dict) -> ToolResult:
    query = _text(arguments, "query")
    results, failures = [], []
    for name, lookup in (("DuckDuckGo", _duckduckgo), ("Wikipedia", _wikipedia)):
        try:
            results += lookup(query)
        except (httpx.HTTPError, ValueError) as exc:
            failures.append(f"{name}: {type(exc).__name__}")
    if not results:
        if failures and len(failures) == 2:
            raise ToolError("The web lookup sources couldn't be reached. Check the internet connection.")
        return ToolResult(f"No results online for “{query}”.", {"query": query, "results": []})
    first = results[0]
    gist = first["text"][:160] + ("…" if len(first["text"]) > 160 else "")
    return ToolResult(
        f"Looked up “{query}” ({len(results)} result{'s' if len(results) != 1 else ''}). "
        f"{first['source']}, {first['title']}: {gist}",
        {"query": query, "results": results},
    )


def _weekday(day: str) -> str:
    """Named here, so a small model doesn't have to work out which day a date falls on."""
    try:
        return date.fromisoformat(day).strftime("%A")
    except (TypeError, ValueError):
        return ""


def weather(settings: Settings, arguments: dict) -> ToolResult:
    place = _text(arguments, "place")
    try:
        found = _get(GEOCODING_API, {"name": place, "count": 1, "language": "en", "format": "json"}).get("results") or []
        if not found:
            raise ToolError(f"No place called “{place}” was found.")
        spot = found[0]
        forecast = _get(FORECAST_API, {
            "latitude": spot["latitude"], "longitude": spot["longitude"], "timezone": "auto", "forecast_days": 3,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max",
        })
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise ToolError("The weather service couldn't be reached. Check the internet connection.") from exc
    now, daily = forecast.get("current", {}), forecast.get("daily", {})
    name = ", ".join(part for part in (spot.get("name"), spot.get("admin1"), spot.get("country")) if part)
    days = [
        {"date": day, "weekday": _weekday(day), "max_c": high, "min_c": low, "conditions": WEATHER_CODES.get(code, f"code {code}"),
         "rain_chance_percent": rain}
        for day, high, low, code, rain in zip(
            daily.get("time", []), daily.get("temperature_2m_max", []), daily.get("temperature_2m_min", []),
            daily.get("weather_code", []), daily.get("precipitation_probability_max", []), strict=False,
        )
    ]
    current = {
        "time": now.get("time"), "temperature_c": now.get("temperature_2m"),
        "feels_like_c": now.get("apparent_temperature"), "humidity_percent": now.get("relative_humidity_2m"),
        "wind_kmh": now.get("wind_speed_10m"), "conditions": WEATHER_CODES.get(now.get("weather_code"), "unknown"),
    }
    return ToolResult(
        f"Weather in {name}: {current['temperature_c']}°C, {current['conditions']}"
        + (f"; today {days[0]['min_c']}–{days[0]['max_c']}°C" if days else "") + " (Open-Meteo).",
        {"place": name, "current": current, "next_days": days, "source": "https://open-meteo.com/"},
    )
