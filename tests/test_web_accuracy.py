"""The web answer accuracy eval (eval/web_accuracy.py): its scorer and its two modes, offline."""

import pytest

from backend.core.config import get_settings
from backend.services import browse
from backend.services.routing import wants_web_search
from eval.web_accuracy import MODES, QUESTIONS, ask, score, set_mode, summarize
from tests.test_agent import ScriptedModel
from tests.test_browse import resolves_to


@pytest.mark.parametrize("qid, kind, question, answers", QUESTIONS, ids=[q[0] for q in QUESTIONS])
def test_every_question_is_one_search_first_would_search(qid, kind, question, answers):
    """Otherwise the search mode would quietly measure memory."""
    assert wants_web_search(question)
    assert kind in ("recent", "stable", "unanswerable")
    assert bool(answers) == (kind != "unanswerable")
    assert all(a == a.lower() for a in answers)


def test_question_ids_are_unique():
    assert len({q[0] for q in QUESTIONS}) == len(QUESTIONS)


@pytest.mark.parametrize("reply, answers, verdict", [
    ("Pope Leo XIV, born Robert Prevost, was elected on 8 May 2025.", ["leo xiv", "prevost"], "right"),
    ("Ousmane Dembélé won the 2025 Ballon d'Or.", ["dembele"], "right"),  # accents don't matter
    ("Lamine Yamal won it.", ["dembele"], "wrong"),
    ("I couldn't find who won the 2025 Ballon d'Or.", ["dembele"], "declined"),
    ("My training data ends before 2025, so I don't know.", ["dembele"], "declined"),
    # The answer in a link isn't the model saying it.
    ("Lamine Yamal won.\nSources: [Ballon d'Or](https://example.org/dembele-wins)", ["dembele"], "wrong"),
    ("Lamine Yamal won, see https://example.org/dembele.", ["dembele"], "wrong"),
    ("206 bones.", ["206"], "right"),
    ("2060 is not it.", ["206"], "wrong"),  # whole words only
    ("The 2030 World Cup hasn't been played yet; it is scheduled for 2030.", [], "right"),
    ("I couldn't find a town called Quistramberg in Ohio.", [], "right"),
    # Refusals from the first live run, which the first pattern scored as wrong or invented.
    ("The 2024 US presidential election results are not available in my current knowledge base.", ["trump"],
     "declined"),
    ("I can't provide that information, as late 2025 is beyond what I have been trained on.", ["machado"],
     "declined"),
    ("Unfortunately, the search results do not provide the answer to the question.", ["1969"], "declined"),
    ("The results do not provide information about the mayor of Quistramberg, Ohio.", [], "right"),
    ("The winner of the 2027 final is not specified in the provided web search results.", [], "right"),
    ("Brazil won the 2030 World Cup, beating Spain 2-1.", [], "invented"),
    ("The mayor of Quistramberg is John Miller.", [], "invented"),
])
def test_scoring(reply, answers, verdict):
    assert score(reply, answers) == verdict


@pytest.fixture
def modes(monkeypatch):
    """set_mode changes the shared settings: undo it after the test."""
    settings = get_settings()
    monkeypatch.setattr(settings, "web_search_first", settings.web_search_first)
    monkeypatch.setattr(settings, "web_lookups_enabled", settings.web_lookups_enabled)
    return set_mode


SEARCH_HTML = ('<div class="result"><h2><a class="result__a" href="https://news.example/pope">Pope</a></h2>'
               '<a class="result__snippet" href="x">Leo XIV elected.</a></div>')


def test_search_mode_searches_first_and_memory_mode_has_no_web(client, monkeypatch, modes):
    fetched = []

    def fetch(url, data=None):
        fetched.append(url)
        body = SEARCH_HTML if url == browse.SEARCH_URL else "<p>Robert Prevost was elected Pope Leo XIV.</p>"
        return url, "text/html", body

    resolves_to(monkeypatch, "93.184.215.14")
    monkeypatch.setattr(browse, "_fetch", fetch)
    model = ScriptedModel(["Pope Leo XIV."], ["I don't know."]).install(monkeypatch)

    modes("search")
    searched = ask(client, "Who was elected Pope in May 2025?")
    assert searched["searched"] and fetched == [browse.SEARCH_URL, "https://news.example/pope"]
    assert ("open_page", "completed") in searched["tools"]
    assert score(searched["reply"], ["leo xiv"]) == "right"

    modes("memory")
    remembered = ask(client, "Who was elected Pope in May 2025?")
    assert not remembered["searched"] and remembered["tools"] == []
    assert len(fetched) == 2  # nothing more went out
    offered = {t["function"]["name"] for t in model.calls[-1]["tools"] or []}
    assert not offered & {"web_search", "open_page", "web_lookup", "weather"}


def test_summary_counts_each_model_and_mode():
    runs = [
        {"model": "m", "mode": "search", "question": "pope", "question_kind": "recent", "verdict": "right",
         "searched": True, "reply": "Leo XIV"},
        {"model": "m", "mode": "search", "question": "mayor", "question_kind": "unanswerable",
         "verdict": "invented", "searched": True, "reply": "John Miller"},
        {"model": "m", "mode": "memory", "question": "pope", "question_kind": "recent", "verdict": "declined",
         "searched": False, "reply": "I don't know"},
        {"model": "m", "mode": "memory", "question": "pope", "error": "timeout"},
    ]
    table = summarize({"runs": runs})
    assert "| m | search | 1/1 (100%) | 0 | 0 | 0/0 | 1/1 (100%) | 2/2 |" in table
    assert "| m | memory | 0/1 (0%) | 0 | 1 | 0/0 | 0/0 | 0/1 |" in table
    assert "`mayor` (invented): John Miller" in table
    assert "1 run(s) failed" in table
    assert set(MODES) == {"search", "memory"}
