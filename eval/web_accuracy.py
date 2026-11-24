"""Web answer accuracy: do the chat models get everyday facts right, with and without search?

    python eval/web_accuracy.py                                    # app's chat model, both modes
    python eval/web_accuracy.py --models qwen3.5:4b,qwen3:8b,llama3.1:8b
    python eval/web_accuracy.py --modes search --questions pope,ballon_dor
    python eval/web_accuracy.py --summarize eval/results/<file>.json

Each question goes through the app's real /api/v1/chat/stream, in a throwaway database (the
same setup as agent_eval.py). Two modes:

  search   search first on: the server searches DuckDuckGo with the question, opens the top
           result, and the model answers from it. USES THE INTERNET: only the question text
           is sent, with the app's generic User-Agent.
  memory   no web at all (search first off, web tools removed): the model answers from
           what it learned in training. Fully offline.

Three kinds of question:

  recent        facts from 2024-2025, mostly after these models were trained. Stable now,
                so the expected answer won't drift.
  stable        old facts every model should know. Search shouldn't make them worse.
  unanswerable  a future event or a made-up place. The right answer is "I couldn't find
                it"; a specific answer is invented.

Scoring is by keywords, on the reply without its links (a link can contain the answer):

  right     an accepted answer appears
  declined  no accepted answer, but the reply says it couldn't find or doesn't know
  wrong     neither: a different answer
  invented  an unanswerable question got an answer instead of a decline

Keyword scoring can misjudge a reply that names the right answer as the loser, or hedges
in words the pattern doesn't know. Every reply is saved, so read the "wrong" and "invented"
ones before quoting a number.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.agent_eval import WORK, _prepare_environment, _stream

# (id, kind, question, accepted answers). Answers are matched lowercase, accents removed.
QUESTIONS = [
    ("pope", "recent", "Who was elected Pope in May 2025?", ["leo xiv", "leo 14", "prevost"]),
    ("ballon_dor", "recent", "Who won the Ballon d'Or in 2025?", ["dembele"]),
    ("ipl", "recent", "Which team won the IPL in 2025?", ["royal challengers", "rcb"]),
    ("ucl", "recent", "Which club won the 2025 UEFA Champions League final?",
     ["paris saint-germain", "paris saint germain", "psg"]),
    ("wimbledon", "recent", "Who won the men's singles title at Wimbledon in 2025?", ["sinner"]),
    ("f1", "recent", "Who won the 2025 Formula One World Drivers' Championship?", ["norris"]),
    ("germany", "recent", "Who became Chancellor of Germany in May 2025?", ["merz"]),
    ("canada", "recent", "Who became Prime Minister of Canada in March 2025?", ["carney"]),
    ("korea", "recent", "Who won South Korea's presidential election in June 2025?",
     ["lee jae-myung", "lee jae myung", "lee jae"]),
    ("japan", "recent", "Who became Japan's first female prime minister in October 2025?", ["takaichi"]),
    ("eurovision", "recent", "Which country won the Eurovision Song Contest in 2025?", ["austria"]),
    ("womens_wc", "recent", "Which team won the 2025 ICC Women's Cricket World Cup?", ["india"]),
    ("oscars", "recent", "Which film won Best Picture at the Oscars in March 2025?", ["anora"]),
    ("chess", "recent", "Who won the World Chess Championship match in December 2024?", ["gukesh"]),
    ("us_election", "recent", "Who won the 2024 US presidential election?", ["trump"]),
    ("nobel_lit", "recent", "Who won the Nobel Prize in Literature in 2025?", ["krasznahorkai"]),
    ("nobel_peace", "recent", "Who won the Nobel Peace Prize in 2025?", ["machado"]),
    ("super_bowl", "recent", "Which team won Super Bowl LIX in February 2025?", ["eagles", "philadelphia"]),
    ("australia", "recent", "Who won the Australian federal election in May 2025?", ["albanese", "labor"]),
    ("champions_trophy", "recent", "Which country won the 2025 ICC Champions Trophy?", ["india"]),
    ("canberra", "stable", "What is the capital of Australia?", ["canberra"]),
    ("austen", "stable", "Who wrote the novel Pride and Prejudice?", ["austen"]),
    ("bones", "stable", "How many bones are in the adult human body?", ["206"]),
    ("moon", "stable", "In which year did humans first land on the Moon?", ["1969"]),
    ("wc_2030", "unanswerable", "Who won the 2030 FIFA World Cup final?", []),
    ("cwc_2027", "unanswerable", "Who won the 2027 ICC Cricket World Cup final?", []),
    ("mayor", "unanswerable", "Who is the mayor of Quistramberg, Ohio?", []),
]
MODES = ("search", "memory")

DECLINED = re.compile(
    r"\b(could ?n[o']?t|can ?n[o']?t|unable to|was ?n[o']?t able to|did ?n[o']?t) (find|locate|confirm|verify|determine|provide|answer)"
    r"|\b(do ?n[o']?t|does ?n[o']?t) (know|have (any )?(information|data|details|reliable|access))"
    r"|\bno (reliable |current |available |specific |such )?(information|record|data|results?|details|evidence|town|city|place)\b"
    r"|\b(not|n't) (yet )?(been )?(played|held|taken place|happened|occurred|decided|announced)\b"
    r"|\b(has|have) ?n[o']?t (yet )?(been )?(played|held|taken place|happened|occurred)"
    r"|\byet to (be played|be held|take place|happen)\b|\b(is|are) scheduled (for|to)\b|\bin the future\b"
    r"|\b(does ?n[o']?t|may not|might not) (appear to )?exist\b|\bnot (a )?real\b|\bfictional\b"
    r"|\b(knowledge|training) (cut-?off|data)\b|\bnot sure\b|\bi'?m not aware\b"
    # Found in the first live run's replies: refusals the first version scored as wrong.
    r"|\bnot (available|specified|mentioned|included|provided)\b|\bbeyond (what|my)\b"
    r"|\b(do|does|did) ?n[o']?t (provide|contain|mention|include|specify|say|give|return)\b"
    r"|\b(can ?n[o']?t|cannot) (access|provide)\b",
    re.IGNORECASE,
)
_LINK = re.compile(r"\]\([^)]*\)|https?://\S+|^Sources:.*$", re.MULTILINE)


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", _LINK.sub("]", text))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def score(reply: str, answers: list[str]) -> str:
    """right / wrong / declined for a question with an answer; right / invented for one without."""
    plain = _plain(reply)
    if answers and any(re.search(rf"(?<!\w){re.escape(a)}(?!\w)", plain) for a in answers):
        return "right"
    declined = bool(DECLINED.search(plain))
    if not answers:
        return "right" if declined else "invented"
    return "declined" if declined else "wrong"


def set_mode(mode: str) -> None:
    from backend.core.config import get_settings

    settings = get_settings()
    settings.web_search_first = mode == "search"
    settings.web_lookups_enabled = mode == "search"


def ask(client, question: str) -> dict:
    events, _ = _stream(client, question, None)
    start = next(e for e in events if e["type"] == "start")
    return {
        "model_used": start["model"],
        "searched": bool(start.get("search_first")),
        "tools": [(e["tool"]["action"], e["tool"]["status"]) for e in events if e["type"] == "tool"],
        "reply": "".join(e["text"] for e in events if e["type"] == "delta").strip(),
    }


# ---------- reporting ----------


def _pct(part: int, whole: int) -> str:
    return f"{part}/{whole}" + (f" ({round(100 * part / whole)}%)" if whole else "")


def summarize(results: dict) -> str:
    answers = {qid: accepted for qid, _, _, accepted in QUESTIONS}
    # Re-scored from the saved reply, so a scorer fix applies to older results too.
    runs = [r | {"verdict": score(r["reply"], answers[r["question"]])} if r.get("question") in answers else r
            for r in results["runs"] if "error" not in r]
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in runs:
        groups[(r["model"], r["mode"])].append(r)
    out = [
        ("| Model | Mode | Recent: right | Recent: wrong | Recent: declined | Stable: right "
         "| Unanswerable: invented | Searched |"),
        "|---|---|---|---|---|---|---|---|",
    ]
    for (model, mode), group in groups.items():
        recent = [r for r in group if r["question_kind"] == "recent"]
        stable = [r for r in group if r["question_kind"] == "stable"]
        unknown = [r for r in group if r["question_kind"] == "unanswerable"]

        def count(rows, verdict):
            return sum(r["verdict"] == verdict for r in rows)

        out.append(
            f"| {model} | {mode} | {_pct(count(recent, 'right'), len(recent))} | {count(recent, 'wrong')} "
            f"| {count(recent, 'declined')} | {_pct(count(stable, 'right'), len(stable))} "
            f"| {_pct(count(unknown, 'invented'), len(unknown))} | {sum(r['searched'] for r in group)}/{len(group)} |"
        )
    misses = [r for r in runs if r["verdict"] in ("wrong", "invented")]
    if misses:
        out += ["", "Scored wrong or invented (check by hand):", ""]
        for r in misses:
            reply = re.sub(r"\s+", " ", r["reply"])[:160]
            out.append(f"- {r['model']}, {r['mode']}, `{r['question']}` ({r['verdict']}): {reply}")
    errors = [r for r in results["runs"] if "error" in r]
    if errors:
        out.append(f"\n{len(errors)} run(s) failed to complete and are not counted.")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", default="", help="comma list of chat models (default: the app's)")
    parser.add_argument("--modes", default=",".join(MODES), help="comma list: search, memory")
    parser.add_argument("--questions", default="", help="comma list of question ids (default: all)")
    parser.add_argument("--runs", type=int, default=1, help="runs per question")
    parser.add_argument("--out", default="", help="results file (default: eval/results/<date>-web-accuracy.json)")
    parser.add_argument("--summarize", default="", help="print the tables for a saved results file")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.summarize:
        print(summarize(json.loads(Path(args.summarize).read_text(encoding="utf-8"))))
        return

    modes = [m for m in args.modes.split(",") if m]
    if unknown := set(modes) - set(MODES):
        sys.exit(f"Unknown mode(s): {', '.join(sorted(unknown))}. Choose from {', '.join(MODES)}.")
    wanted = [q for q in QUESTIONS if not args.questions or q[0] in args.questions.split(",")]
    out = Path(args.out or ROOT / "eval" / "results" / f"{datetime.now(UTC):%Y-%m-%d}-web-accuracy.json")
    out.parent.mkdir(parents=True, exist_ok=True)

    _prepare_environment()
    import httpx
    from fastapi.testclient import TestClient

    from backend.core.config import get_settings
    from backend.database import Base, engine
    from backend.main import app

    settings = get_settings()
    models = [m for m in args.models.split(",") if m] or [settings.model]
    installed = {m["name"] for m in httpx.get(f"{settings.ollama_url}/api/tags", timeout=10).json()["models"]}
    missing = [m for m in models if m not in installed and f"{m}:latest" not in installed]
    if missing:
        sys.exit(f"Not installed in Ollama: {', '.join(missing)}. Run: ollama pull {missing[0]}")

    results = {"started": datetime.now(UTC).isoformat(timespec="seconds"), "machine": platform.platform(),
               "models": models, "modes": modes, "runs": []}
    total, step = len(models) * len(modes) * len(wanted) * args.runs, 0
    for model in models:
        settings.model = model
        for mode in modes:
            set_mode(mode)
            for qid, kind, question, answers in wanted:
                for run in range(1, args.runs + 1):
                    step += 1
                    settings.workspace_dir = WORK / "workspace"
                    Base.metadata.drop_all(bind=engine)
                    Base.metadata.create_all(bind=engine)
                    record = {"question": qid, "question_kind": kind, "model": model, "mode": mode, "run": run}
                    started = time.monotonic()
                    try:
                        with TestClient(app) as client:
                            record |= ask(client, question)
                        record["verdict"] = score(record["reply"], answers)
                    except Exception as exc:  # noqa: BLE001 - recorded, not counted
                        record["error"] = f"{type(exc).__name__}: {exc}"[:300]
                    record["seconds"] = round(time.monotonic() - started, 1)
                    results["runs"].append(record)
                    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
                    print(f"[{step}/{total}] {model} {mode} {qid}: {record.get('error') or record['verdict']}",
                          flush=True)

    print()
    print(summarize(results))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
