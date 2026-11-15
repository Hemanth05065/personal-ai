"""Pick which local model answers a message.

Small general models write a page layout and leave the logic broken, so requests
that ask for code go to a model trained for code. The check is a plain word match:
predictable, instant, and easy to test. A wrong guess only changes which model
answers; every tool still goes through the same policy and approval rules.
"""

import re
from dataclasses import dataclass

from backend.core.config import Settings

# Words that almost only appear when someone wants code written, fixed or explained.
_CODE_WORDS = (
    r"code|coding|programming|script|function|debug|exception|stack ?trace|compiler?|"
    r"refactor|algorithm|regex|api endpoint|sql|html|css|javascript|typescript|react|vue|"
    r"node\.?js|python|java|c\+\+|c#|rust|golang|php|ruby|kotlin|swift|bash|powershell|"
    r"json|yaml|web ?page|website|web ?app|snippet|unit ?tests?|pytest|syntax"
)
_CODE_PATTERN = re.compile(rf"(?<![\w+#])(?:{_CODE_WORDS})(?![\w+#])", re.IGNORECASE)
# "make a pacman game", "build me a calculator app": a build verb, then something to build.
_BUILD_PATTERN = re.compile(
    r"\b(?:make|build|create|write|develop|code|program)\b[^.?!\n]{0,40}?"
    r"\b(?:game|app|application|program|tool|bot|calculator|site|page|extension|cli)\b",
    re.IGNORECASE,
)
# Code pasted into the message counts too.
_CODE_SHAPES = re.compile(
    r"```|\bdef \w+\(|\bfunction \w*\(|=>|</?[a-z][\w-]*(?:\s[^>]*)?>|;\s*$", re.MULTILINE
)

CODER_GUIDANCE = """You are answering a programming request. Write complete, working code:
no placeholders, no "add your logic here", no omitted parts. For a web page or browser
game, put everything in ONE .html file with the CSS in a <style> tag and the JavaScript in
a <script> tag, so it runs by opening the file. Make the core logic actually work (game
loop, input, collisions, scoring, win/lose) before adding polish. For Python, write one
complete script that runs as-is with only the standard library (the app runs it in a
sandbox without numpy, pandas or internet), read any input with input(), and print the
results. Briefly say how to run it after the code."""


@dataclass(frozen=True)
class ModelChoice:
    model: str
    context_tokens: int
    coding: bool
    guidance: str = ""


def is_coding_request(text: str) -> bool:
    return bool(
        _CODE_PATTERN.search(text) or _BUILD_PATTERN.search(text) or _CODE_SHAPES.search(text)
    )


def choose_model(settings: Settings, latest_user_text: str) -> ModelChoice:
    if settings.coder_model and is_coding_request(latest_user_text):
        return ModelChoice(
            settings.coder_model, settings.coder_context_tokens, True, CODER_GUIDANCE
        )
    return ModelChoice(settings.model, settings.context_tokens, False)
