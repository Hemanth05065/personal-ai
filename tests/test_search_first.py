"""Search first: everyday questions are answered from the web, not the model's memory."""

import pytest

from backend.core.config import get_settings
from backend.services import browse
from backend.services.agent import NETWORK_REASON, SEARCHED_GUIDANCE, _pages_worth_opening
from backend.services.ollama import ToolRequest
from backend.services.routing import wants_web_search
from tests.test_agent import ScriptedModel, _stream, _text, _tools, _workspace
from tests.test_browse import PAGE_HTML, SEARCH_HTML, resolves_to

GOLD = "https://www.goodreturns.in/gold-rates/"


@pytest.mark.parametrize("question", [
    "how is gta 6", "where is voyager 1", "gold rate in chennai today", "who won the ipl 2026",
    "what is the capital of france", "Thirukkural author", "latest news about isro",
    "Open https://www.python.org and tell me the latest release",
])
def test_everyday_questions_search_first(question):
    assert wants_web_search(question)


@pytest.mark.parametrize("message", [
    "hi", "thanks!", "what is todays date", "date and time", "whats the time", "17*23",
    "summarize notes.txt", "list my files", "remind me at 5pm to call mom",
    "translate this to tamil: good morning", "why?", "tell me more",
    "make a pacman game", "write a python function to sort a list", "fix this code",
])
def test_small_talk_code_and_own_files_do_not(message):
    assert not wants_web_search(message)


def test_unreadable_sites_are_not_opened():
    results = {"results": [{"url": "https://www.youtube.com/watch?v=1"}, {"url": "https://m.facebook.com/x"},
                           {"url": "https://a.example/"}, {"url": "https://b.example/"}, {"url": "https://c.example/"}]}
    assert _pages_worth_opening(results) == ["https://a.example/", "https://b.example/"]


@pytest.fixture
def search_first(monkeypatch):
    monkeypatch.setattr(get_settings(), "web_search_first", True)
    pages = {browse.SEARCH_URL: SEARCH_HTML, GOLD: PAGE_HTML}
    opened = []

    def fetch(url, data=None):
        opened.append(url)
        if url not in pages:
            raise browse.ToolError("The page couldn't be loaded.")
        return url, "text/html", pages[url]

    resolves_to(monkeypatch, "93.184.215.14")
    monkeypatch.setattr(browse, "_fetch", fetch)
    return opened


def test_the_server_searches_and_opens_the_top_result_before_the_model_answers(client, monkeypatch, search_first):
    model = ScriptedModel(["22K gold is 7,050 per gram (goodreturns.in)."]).install(monkeypatch)
    events = _stream(client, "gold rate in chennai today")
    assert [(c["action"], c["status"]) for c in _tools(events)] == [("web_search", "completed"), ("open_page", "completed")]
    assert search_first == [browse.SEARCH_URL, GOLD]
    call = model.calls[0]
    assert "<UNTRUSTED_DATA" in call["messages"][-1]["content"] and "7,050" in call["messages"][-1]["content"]
    assert SEARCHED_GUIDANCE in call["system_extra"]
    # The "only these facts" note and today's date sit right after the results.
    assert "using ONLY facts" in call["messages"][-1]["content"]
    assert "Current date and time" in call["messages"][-1]["content"]
    # The server adds the source link; the model didn't give one.
    assert _text(events).endswith(f"Sources: [Gold Rate Today]({GOLD})")


def test_no_second_source_line_when_the_model_linked_it(client, monkeypatch, search_first):
    ScriptedModel([f"7,050 per gram ({GOLD})."]).install(monkeypatch)
    assert "Sources:" not in _text(_stream(client, "gold rate in chennai today"))


def test_a_page_that_fails_falls_back_to_the_next_result(client, monkeypatch, search_first):
    monkeypatch.setattr(browse, "_fetch", _failing_first(browse._fetch))
    ScriptedModel(["Answer."]).install(monkeypatch)
    cards = _tools(_stream(client, "gold rate in chennai today"))
    assert [(c["action"], c["status"]) for c in cards] == [
        ("web_search", "completed"), ("open_page", "failed"), ("open_page", "failed")]


def _failing_first(fetch):
    def wrapped(url, data=None):
        if url == GOLD:
            raise browse.ToolError("The page couldn't be loaded.")
        return fetch(url, data)
    return wrapped


def test_coding_and_small_talk_go_straight_to_the_model(client, monkeypatch, search_first):
    ScriptedModel(["Hello!"]).install(monkeypatch)
    assert _tools(_stream(client, "hi")) == []
    assert search_first == []


def test_once_files_are_in_the_chat_the_search_asks_first(client, monkeypatch, search_first):
    """Search first sends the user's own words, but the exfiltration guard still applies."""
    (_workspace() / "notes.txt").write_text("private")
    ScriptedModel([ToolRequest("read_file", {"path": "notes.txt"})], ["Summary."]).install(monkeypatch)
    first = _stream(client, "Summarize notes.txt")
    conversation = next(e for e in first if e["type"] == "start")["conversation_id"]
    card = _tools(_stream(client, "gold rate in chennai today", conversation))[-1]
    assert card["action"] == "web_search" and card["status"] == "awaiting_approval"
    assert card["reason"] == NETWORK_REASON
    assert search_first == []


def test_turned_off_it_leaves_the_choice_to_the_model(client, monkeypatch, search_first):
    monkeypatch.setattr(get_settings(), "web_search_first", False)
    ScriptedModel(["From memory."]).install(monkeypatch)
    assert _tools(_stream(client, "gold rate in chennai today")) == []


def test_a_searched_answer_is_labelled(client, monkeypatch, search_first):
    ScriptedModel(["Answer."], ["Hello!"]).install(monkeypatch)
    start = next(e for e in _stream(client, "gold rate in chennai today") if e["type"] == "start")
    assert start["search_first"] is True
    start = next(e for e in _stream(client, "hi") if e["type"] == "start")
    assert start["search_first"] is False


def test_the_web_search_button_turns_it_off_for_this_user(client, monkeypatch, search_first):
    assert client.get("/api/v1/settings/me").json()["web_search"] is True  # the server default
    saved = client.put("/api/v1/settings/me", json={"web_search": False}).json()
    assert saved == {"autopilot": False, "web_search": False, "web_available": True}
    ScriptedModel(["From memory."]).install(monkeypatch)
    assert _tools(_stream(client, "gold rate in chennai today")) == []
    assert search_first == []


def test_switching_web_search_is_recorded_in_the_audit_log(client, search_first):
    from backend.database import SessionLocal
    from backend.models.entities import SecureAuditRecord
    client.put("/api/v1/settings/me", json={"web_search": False})
    with SessionLocal() as db:
        actions = [record.event_type for record in db.query(SecureAuditRecord).all()]
    assert "settings.web_search" in actions


def test_with_web_access_off_the_button_is_hidden_and_nothing_is_searched(client, monkeypatch, search_first):
    monkeypatch.setattr(get_settings(), "web_lookups_enabled", False)
    assert client.get("/api/v1/settings/me").json() == {"autopilot": False, "web_search": False, "web_available": False}
