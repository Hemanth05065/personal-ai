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
sandbox with Python 3.14, without numpy, pandas or internet), read any input with input(),
and print the results. Use current Python only: removed APIs such as ast.Num, ast.Str,
imp, distutils and asyncio.get_event_loop() outside a loop fail on 3.14. Don't hide bugs
behind a broad try/except that prints the exception; only catch errors you expect, such as
bad user input. If a Python program reads input, put one realistic example input right after
the code in a ```text block (exactly the lines the program reads); the app uses it to test
the program. Briefly say how to run it after the code."""


# Small models skim long system prompts; the benchmark showed both coders using ast.Num
# (gone in Python 3.14) despite the guidance above. The same rules right after the request
# are followed far more often. Added for the model only, never saved in the chat.
CODER_REMINDER = (
    "\n\n[Checklist before you answer: complete runnable code, no placeholders. "
    "Python runs on 3.14 with the standard library only: never use ast.Num or ast.Str "
    "(use ast.Constant). If the program reads input, end your reply with one example "
    "input in a ```text block.]"
)


def with_reminder(messages: list[dict]) -> list[dict]:
    """Copy of the conversation with CODER_REMINDER after the latest user message."""
    if not messages or messages[-1].get("role") != "user":
        return messages
    last = {**messages[-1], "content": messages[-1]["content"] + CODER_REMINDER}
    return [*messages[:-1], last]


# Neither coder reliably writes an example input, and without one the self-test can't
# exercise a program that reads input. This short follow-up asks for one.
EXAMPLE_INPUT_PROMPT = (
    "Here is a Python program. Write ONE realistic example of the input it expects: exactly "
    "the lines it reads with input(), in order, valid for the program, nothing else. Reply "
    "with only a ```text block.\n\n```python\n{code}\n```"
)
_TEXT_BLOCK = re.compile(r"```[ \t]*(?:text|txt|input|stdin|plaintext)?[ \t]*\n(.*?)```", re.DOTALL)


def extract_example_input(reply: str) -> str:
    """The lines inside the reply's first code block (or the bare reply), trimmed and capped."""
    match = _TEXT_BLOCK.search(reply)
    text = match.group(1) if match else reply
    lines = [line.rstrip() for line in text.strip("\n").splitlines()]
    return "\n".join(lines[:200])[:4000]


@dataclass(frozen=True)
class ModelChoice:
    model: str
    context_tokens: int
    coding: bool
    guidance: str = ""
    # The big coder: slower, so the UI says so and the stream waits longer between pieces.
    big: bool = False


# The app's own fix requests (apps/web/src/preview.js fixRequest) start like this.
_AUTO_FIX = re.compile(r"^\s*Auto-fix \(attempt \d+ of \d+\)")


def is_coding_request(text: str) -> bool:
    return bool(
        _CODE_PATTERN.search(text) or _BUILD_PATTERN.search(text) or _CODE_SHAPES.search(text)
    )


def is_big_job(text: str) -> bool:
    """Whole programs (a game, an app) and fixing code that failed its test."""
    return bool(_BUILD_PATTERN.search(text) or _AUTO_FIX.search(text))


def choose_model(settings: Settings, latest_user_text: str) -> ModelChoice:
    if settings.big_coder_model and is_big_job(latest_user_text):
        return ModelChoice(
            settings.big_coder_model,
            settings.big_coder_context_tokens,
            True,
            CODER_GUIDANCE,
            big=True,
        )
    if settings.coder_model and is_coding_request(latest_user_text):
        return ModelChoice(
            settings.coder_model, settings.coder_context_tokens, True, CODER_GUIDANCE
        )
    return ModelChoice(settings.model, settings.context_tokens, False)


def without_big(settings: Settings, choice: ModelChoice) -> ModelChoice:
    """The same request on the regular coder, for when the big one isn't installed."""
    model = settings.coder_model or settings.model
    return ModelChoice(model, settings.coder_context_tokens, True, choice.guidance)
