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
    # Drop a heading such as "# Example input": it would be fed to input() as an answer.
    while lines and (_LABEL.match(lines[0]) or lines[0].lstrip().startswith(("#", "//"))):
        lines.pop(0)
    return "\n".join(lines[:200])[:4000]


_LABEL = re.compile(r"^\s*(#|//|--)?\s*(example|sample)?\s*(input|stdin)\b.*$", re.IGNORECASE)


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


# "Open https://www.python.org and tell me…" names Python but is a browsing task, not code:
# routed to the coder, it wrote a script instead of opening the page. A link or a web phrase,
# with no request to write or fix code, stays with the chat model (which has the web tools).
_BROWSE = re.compile(
    r"https?://|www\.\w|\b(?:search|look\s+up|browse|google)\b[^.?!\n]{0,30}\b(?:web|internet|online)\b"
    r"|\b(?:latest|today'?s?|current)\s+(?:news|price|rate|score)s?\b",
    re.IGNORECASE,
)
_WRITE_CODE = re.compile(
    r"\b(?:write|code|script|program|function|class|debug|fix|refactor|implement|scrape|scraper|regex)\b",
    re.IGNORECASE,
)


def is_browsing_request(text: str) -> bool:
    return bool(_BROWSE.search(text)) and not _WRITE_CODE.search(text) and "```" not in text


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
    if is_browsing_request(latest_user_text):
        return ModelChoice(settings.model, settings.context_tokens, False)
    if settings.coder_model and is_coding_request(latest_user_text):
        return ModelChoice(
            settings.coder_model, settings.coder_context_tokens, True, CODER_GUIDANCE
        )
    return ModelChoice(settings.model, settings.context_tokens, False)


def without_big(settings: Settings, choice: ModelChoice) -> ModelChoice:
    """The same request on the regular coder, for when the big one isn't installed."""
    model = settings.coder_model or settings.model
    return ModelChoice(model, settings.coder_context_tokens, True, choice.guidance)


# Search first: everyday questions are answered from the web, not the chat model's memory,
# which is old and invents details (asked "how is GTA 6", it made up the studio and setting).
# Skipped where a search can't help: small talk, the date and time (the model is given them),
# sums, the user's own files and reminders, rewriting text they gave, and short follow-ups
# that only make sense with the chat above.
_SMALL_TALK = re.compile(
    r"^\s*(?:hi+|hello|hey|yo|hii+|good\s+(?:morning|afternoon|evening|night)|thanks?(?:\s+you)?|thank\s+you|"
    r"ok(?:ay)?|cool|nice|great|yes|no|yeah|nope|bye|goodbye|how\s+are\s+you|who\s+are\s+you|"
    r"what\s+can\s+you\s+do)\b[\s!.?]*$",
    re.IGNORECASE,
)
_CLOCK = re.compile(
    r"^\s*(?:what(?:'?s|\s+is)?\s+)?(?:the\s+)?(?:today'?s?\s+)?(?:current\s+)?(?:date|time|day)"
    r"(?:\s+(?:and|&)\s+(?:date|time|day))?(?:\s+(?:is\s+it\s+)?(?:today|now))?\s*\??\s*$",
    re.IGNORECASE,
)
_SUM = re.compile(r"^[\s\d+\-*/x×÷^().,%=?]*(?:what\s+is\s+)?[\s\d+\-*/x×÷^().,%=?]+$", re.IGNORECASE)
_OWN_STUFF = re.compile(
    r"\b(?:my\s+(?:files?|folder|notes?|documents?|workspace)|workspace|\w+\.(?:txt|md|csv|json|py|pdf)\b|"
    r"remind(?:er)?s?|remember\s+(?:that|this)|forget|memor(?:y|ies))\b",
    re.IGNORECASE,
)
_TEXT_TASK = re.compile(
    r"^\s*(?:please\s+)?(?:summari[sz]e|translate|rewrite|rephrase|paraphrase|proofread|correct|"
    r"shorten|expand|reword|make\s+(?:this|it)\s+(?:shorter|longer|formal|polite))\b",
    re.IGNORECASE,
)
_FOLLOW_UP = re.compile(
    r"^\s*(?:and|so|but|why|how\s+so|really|tell\s+me\s+more|more|explain(?:\s+(?:it|that|this|more))?|"
    r"what\s+about|continue|go\s+on|again|elaborate)\b[^.?!\n]{0,25}[?.!]*\s*$",
    re.IGNORECASE,
)


def wants_web_search(text: str) -> bool:
    """True for an everyday question the chat model should answer from the web."""
    words = re.findall(r"\w+", text)
    if not words or len(text) > 400 or "```" in text:
        return False
    if is_coding_request(text) and not is_browsing_request(text):
        return False
    return not any(
        pattern.search(text) for pattern in (_SMALL_TALK, _CLOCK, _SUM, _OWN_STUFF, _TEXT_TASK, _FOLLOW_UP)
    )
