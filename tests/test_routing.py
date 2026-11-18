import asyncio
import json
import time

import httpx
import pytest

import backend.api.chat as chat_api
from backend.core.config import get_settings
from backend.services.ollama import OllamaClient, model_installed
from backend.services.routing import choose_model, extract_example_input, is_coding_request


@pytest.mark.parametrize(
    "text",
    [
        "make pacman in html",
        "Build me a snake game",
        "write a python script that renames my photos",
        "why does this throw an exception?",
        "fix this:\n```js\nconst a = 1\n```",
        "create a calculator app",
        "def add(a, b): return a + b  -- what's wrong?",
    ],
)
def test_coding_requests_are_detected(text):
    assert is_coding_request(text)


@pytest.mark.parametrize(
    "text",
    [
        "hi, how are you?",
        "let's go for a walk later",
        "what game should I play this weekend?",
        "remind me about my class tomorrow",
        "I made an error in my essay, any tips?",
        "summarise my notes about the trip",
    ],
)
def test_normal_chat_stays_on_the_chat_model(text):
    assert not is_coding_request(text)


def test_choice_uses_coder_model_and_bigger_window():
    settings = get_settings().model_copy(update={"coder_model": "coder", "model": "chat"})
    coding = choose_model(settings, "fix the css in this html page layout")
    assert (coding.model, coding.coding) == ("coder", True)
    assert coding.context_tokens == settings.coder_context_tokens
    assert "ONE .html file" in coding.guidance
    chat = choose_model(settings, "hello")
    assert (chat.model, chat.coding, chat.guidance) == ("chat", False, "")


def test_empty_coder_model_turns_coding_mode_off():
    settings = get_settings().model_copy(update={"coder_model": "", "model": "chat"})
    assert choose_model(settings, "write a python script").model == "chat"


def test_payload_sends_chosen_model_and_context_size():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200, text=json.dumps({"message": {"content": "ok"}, "done": True}) + "\n"
        )

    client = OllamaClient(
        get_settings(), transport=httpx.MockTransport(handler), model="coder", context_tokens=16384
    )

    async def collect():
        return [piece async for piece in client.stream_chat([{"role": "user", "content": "x"}], [])]

    assert asyncio.run(collect()) == ["ok"]
    assert seen["model"] == "coder"
    assert seen["options"]["num_ctx"] == 16384


def _stream(captured):
    async def stream_chat(self, messages, memories, tools=None, system_extra=""):
        captured["timeout"] = self.read_timeout
        assert "ONE .html file" in system_extra
        yield f"model={self.model}"

    return stream_chat


def _start(client, message):
    response = client.post("/api/v1/chat/stream", json={"message": message})
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_quick_code_question_uses_the_fast_coder(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(OllamaClient, "stream_chat", _stream(captured))
    events = _start(client, "why does this python function throw an exception?")
    assert (events[0]["coding"], events[0]["big"]) == (True, False)
    assert events[0]["model"] == get_settings().coder_model
    assert captured["timeout"] == 120


def test_build_request_uses_the_big_coder_with_a_longer_wait(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(OllamaClient, "stream_chat", _stream(captured))
    monkeypatch.setattr(chat_api, "model_installed", _installed(True))
    events = _start(client, "make a pacman game in html")
    assert (events[0]["coding"], events[0]["big"]) == (True, True)
    assert events[0]["model"] == get_settings().big_coder_model
    assert events[1]["text"] == f"model={get_settings().big_coder_model}"
    assert captured["timeout"] == 600


def test_big_coder_not_installed_falls_back_to_the_fast_coder(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(OllamaClient, "stream_chat", _stream(captured))
    monkeypatch.setattr(chat_api, "model_installed", _installed(False))
    events = _start(client, "make a pacman game in html")
    assert (events[0]["coding"], events[0]["big"]) == (True, False)
    assert events[0]["model"] == get_settings().coder_model


def _installed(answer):
    async def model_installed(settings, name):
        return answer

    return model_installed


@pytest.mark.parametrize(
    "text",
    [
        "build me a snake game",
        "create a calculator app in python",
        "Auto-fix (attempt 1 of 3): I ran your HTML code in the browser and it failed",
    ],
)
def test_whole_programs_and_auto_fixes_are_big_jobs(text):
    settings = get_settings().model_copy(update={"big_coder_model": "big", "coder_model": "coder"})
    choice = choose_model(settings, text)
    assert (choice.model, choice.big, choice.coding) == ("big", True, True)


@pytest.mark.parametrize("text", ["explain this python error", "write a regex for emails", "hello"])
def test_small_requests_are_not_big_jobs(text):
    settings = get_settings().model_copy(update={"big_coder_model": "big", "coder_model": "coder"})
    assert choose_model(settings, text).big is False


def test_empty_big_coder_model_turns_it_off():
    settings = get_settings().model_copy(update={"big_coder_model": "", "coder_model": "coder"})
    assert choose_model(settings, "make a snake game").model == "coder"


def test_model_installed_checks_ollama_and_trusts_it_when_unreachable(monkeypatch):
    import backend.services.ollama as ollama_module

    monkeypatch.setattr(ollama_module, "_installed", (0.0, set()))
    unreachable = get_settings().model_copy(update={"ollama_url": "http://127.0.0.1:9"})
    assert asyncio.run(model_installed(unreachable, "anything")) is True

    monkeypatch.setattr(ollama_module, "_installed", (time.monotonic(), {"qwen2.5-coder:14b"}))
    assert asyncio.run(model_installed(get_settings(), "qwen2.5-coder:14b")) is True
    assert asyncio.run(model_installed(get_settings(), "missing:1b")) is False


def test_coding_requests_get_the_checklist_but_the_chat_does_not_save_it(client, monkeypatch):
    seen = {}

    async def stream_chat(self, messages, memories, tools=None, system_extra=""):
        seen["last"] = messages[-1]["content"]
        yield "ok"

    monkeypatch.setattr(OllamaClient, "stream_chat", stream_chat)
    events = _start(client, "write a python script that adds two numbers")
    assert seen["last"].startswith("write a python script that adds two numbers")
    assert "ast.Constant" in seen["last"] and "```text" in seen["last"]
    detail = client.get(f"/api/v1/chat/conversations/{events[0]['conversation_id']}").json()
    saved = [m["content"] for m in detail["messages"] if m["role"] == "user"]
    assert saved == ["write a python script that adds two numbers"]


def test_normal_chat_gets_no_checklist(client, monkeypatch):
    seen = {}

    async def stream_chat(self, messages, memories, tools=None, system_extra=""):
        seen["last"] = messages[-1]["content"]
        yield "ok"

    monkeypatch.setattr(OllamaClient, "stream_chat", stream_chat)
    _start(client, "how was your day?")
    assert seen["last"] == "how was your day?"


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("```text\n3 + 4\n```", "3 + 4"),
        ("Here you go:\n```\n5\nAlice\n```\nDone.", "5\nAlice"),
        ("```input\n1 2 3  \n4\n```", "1 2 3\n4"),
        ("7", "7"),
        ("```text\n# Example input\n5\n```", "5"),
        ("```\nExample input:\n3 + 4\n```", "3 + 4"),
    ],
)
def test_extract_example_input(reply, expected):
    assert extract_example_input(reply) == expected


def test_example_input_endpoint_uses_the_fast_coder(client, monkeypatch):
    seen = {}

    async def chat(self, messages, memories):
        seen["model"] = self.model
        seen["prompt"] = messages[0]["content"]
        return "```text\n2 + 2\n```"

    monkeypatch.setattr(OllamaClient, "chat", chat)
    response = client.post("/api/v1/chat/example-input", json={"code": "print(input())"})
    assert response.status_code == 200
    assert response.json() == {"input": "2 + 2"}
    assert seen["model"] == get_settings().coder_model
    assert "print(input())" in seen["prompt"]


def test_example_input_endpoint_rejects_empty_code(client):
    assert client.post("/api/v1/chat/example-input", json={"code": ""}).status_code == 422


def test_example_input_uses_the_big_coder_when_it_wrote_the_code(client, monkeypatch):
    seen = {}

    async def chat(self, messages, memories):
        seen["model"] = self.model
        return "```text\n5\n```"

    monkeypatch.setattr(OllamaClient, "chat", chat)
    monkeypatch.setattr(chat_api, "model_installed", _installed(True))
    response = client.post("/api/v1/chat/example-input", json={"code": "input()", "big": True})
    assert response.json() == {"input": "5"}
    assert seen["model"] == get_settings().big_coder_model
