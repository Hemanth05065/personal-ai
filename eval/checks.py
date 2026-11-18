"""Hidden checks: does a program's output contain the right answer?

Programs print their own prompts ("Enter a number: ") and wording ("Result: 7"), so the
checks look for the answer rather than demanding an exact transcript. Each check is
{"type": ..., ...} and judge() returns (passed, why).
"""

import re

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _numbers(text: str) -> list[float]:
    return [float(item) for item in _NUMBER.findall(text)]


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def judge(check: dict, stdout: str) -> tuple[bool, str]:
    kind = check["type"]
    if kind == "number":
        # The last number printed is the answer.
        numbers = _numbers(stdout)
        if not numbers:
            return False, "printed no number"
        ok = abs(numbers[-1] - check["value"]) < 1e-9
        return ok, f"last number {numbers[-1]:g}, wanted {check['value']:g}"
    if kind == "word":
        # The expected token appears on its own (not inside a longer word).
        pattern = rf"(?<![\w]){re.escape(check['value'])}(?![\w])"
        ok = re.search(pattern, stdout) is not None
        return ok, f"{'found' if ok else 'missing'} {check['value']!r}"
    if kind == "contains":
        ok = check["value"].lower() in stdout.lower()
        absent = [bad for bad in check.get("absent", []) if bad.lower() in stdout.lower()]
        return ok and not absent, (
            f"{'found' if ok else 'missing'} {check['value']!r}"
            + (f"; also printed {absent[0]!r}" if absent else "")
        )
    if kind == "squashed":
        # Compare without any whitespace: "2^3 * 3^2" == "2^3*3^2".
        ok = _squash(check["value"]) in _squash(stdout)
        return ok, f"{'found' if ok else 'missing'} {check['value']!r}"
    if kind == "in_order":
        # Each item appears, in this order (lowercased, whitespace squashed).
        text = _squash(stdout.lower())
        position = 0
        for item in check["value"]:
            found = text.find(_squash(item.lower()), position)
            if found < 0:
                return False, f"missing {item!r} (in order)"
            position = found + len(_squash(item))
        return True, "all items in order"
    if kind == "tail_numbers":
        # The program's numbers end with exactly this sequence.
        numbers = _numbers(stdout)
        want = [float(item) for item in check["value"]]
        ok = numbers[-len(want) :] == want
        return ok, f"ended with {[f'{n:g}' for n in numbers[-len(want) :]]}"
    if kind == "digits_end":
        # All digits printed, concatenated, end with this string (for grids).
        digits = re.sub(r"\D", "", stdout)
        ok = digits.endswith(check["value"])
        return ok, "grid matches" if ok else "grid differs"
    raise ValueError(f"unknown check type {kind!r}")
