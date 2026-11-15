import asyncio
import json

import httpx
import pytest

from backend.core.config import get_settings
from backend.services.ollama import OllamaClient
from backend.services.routing import choose_model, is_coding_request


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
    coding = choose_model(settings, "make pacman in html")
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


def test_stream_start_event_reports_coding(client, monkeypatch):
    async def stream_chat(self, messages, memories, tools=None, system_extra=""):
        assert "ONE .html file" in system_extra
        yield f"model={self.model}"

    monkeypatch.setattr(OllamaClient, "stream_chat", stream_chat)
    response = client.post("/api/v1/chat/stream", json={"message": "make a pacman game in html"})
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert events[0]["coding"] is True
    assert events[0]["model"] == get_settings().coder_model
    assert events[1]["text"] == f"model={get_settings().coder_model}"
