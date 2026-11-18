"""The evaluation harness's own correctness: its checks, and its tasks' expected answers."""

import subprocess
import sys

import pytest

from eval.checks import judge
from eval.reference_solutions import REFERENCE
from eval.tasks import TASKS

KNOWN_TYPES = {"number", "word", "contains", "squashed", "in_order", "tail_numbers", "digits_end"}


def test_tasks_are_well_formed():
    ids = [task["id"] for task in TASKS]
    assert len(ids) == len(set(ids)) >= 10
    for task in TASKS:
        assert task["prompt"].startswith("Write a Python program")
        assert task["checks"], task["id"]
        for check in task["checks"]:
            assert check["type"] in KNOWN_TYPES and "stdin" in check and "value" in check


def test_every_task_has_a_reference_solution():
    assert set(REFERENCE) == {task["id"] for task in TASKS}


@pytest.mark.parametrize(
    ("task", "check"),
    [(task, check) for task in TASKS for check in task["checks"]],
    ids=lambda item: item["id"] if "id" in item else item["stdin"][:12],
)
def test_reference_solution_passes_every_hidden_check(task, check):
    """If this fails, the expected answer in eval/tasks.py is wrong, not the model."""
    done = subprocess.run(
        [sys.executable, "-I", "-c", REFERENCE[task["id"]]],
        input=check["stdin"] + "\n",
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    passed, why = judge(check, done.stdout)
    assert passed, f"{task['id']} {check['stdin']!r}: {why}; printed {done.stdout!r}"


# ---------- the checks themselves ----------


@pytest.mark.parametrize(
    ("check", "stdout", "expected"),
    [
        ({"type": "number", "value": 7}, "Enter an expression: Result: 7.0\n", True),
        ({"type": "number", "value": -1}, "No path. -1\n", True),
        ({"type": "number", "value": 4}, "4 steps... actually 5\n", False),
        ({"type": "number", "value": 4}, "no number here", False),
        ({"type": "word", "value": "IV"}, "Roman: IV\n", True),
        ({"type": "word", "value": "IV"}, "Roman: XIV\n", False),
        ({"type": "contains", "value": "balanced", "absent": ["not balanced"]}, "balanced", True),
        (
            {"type": "contains", "value": "balanced", "absent": ["not balanced"]},
            "Not balanced",
            False,
        ),
        ({"type": "squashed", "value": "2^3 * 3^2 * 5"}, "360 = 2^3*3^2*5\n", True),
        ({"type": "in_order", "value": ["the 3", "cat 2"]}, "the 3\ncat 2\nand 1\n", True),
        ({"type": "in_order", "value": ["the 3", "cat 2"]}, "cat 2\nthe 3\n", False),
        ({"type": "tail_numbers", "value": [1, 2, 4, 3]}, "Enter n: 1 2 4 3\n", True),
        ({"type": "tail_numbers", "value": [1, 2, 4, 3]}, "1 2 3 4\n", False),
        ({"type": "digits_end", "value": "123"}, "Solved:\n1 2 3\n", True),
    ],
)
def test_judge(check, stdout, expected):
    assert judge(check, stdout)[0] is expected


def test_unknown_check_type_is_an_error():
    with pytest.raises(ValueError):
        judge({"type": "vibes", "value": 1}, "")
