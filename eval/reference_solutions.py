"""A correct program for every task, written by hand.

tests/test_eval.py runs each one against its task's hidden checks. If a reference solution
fails, the task's expected answer is wrong, not the model: this keeps the benchmark honest.
"""

REFERENCE = {
    "expression": r"""
import re

def tokens(text):
    out = re.findall(r"\d+\.\d+|\d+|[-+*/()]|\S", text)
    if any(t not in "+-*/()" and not re.fullmatch(r"\d+(\.\d+)?", t) for t in out):
        raise ValueError
    return out

def parse(ts):
    pos = 0
    def peek():
        return ts[pos] if pos < len(ts) else None
    def take():
        nonlocal pos
        pos += 1
        return ts[pos - 1]
    def expr():
        value = term()
        while peek() in ("+", "-"):
            value = value + term() if take() == "+" else value - term()
        return value
    def term():
        value = factor()
        while peek() in ("*", "/"):
            value = value * factor() if take() == "*" else value / factor()
        return value
    def factor():
        t = peek()
        if t == "-":
            take()
            return -factor()
        if t == "(":
            take()
            value = expr()
            if take() != ")":
                raise ValueError
            return value
        if t is None or t in "+*/)":
            raise ValueError
        return float(take())
    value = expr()
    if pos != len(ts):
        raise ValueError
    return value

try:
    result = parse(tokens(input()))
    print(int(result) if result == int(result) else result)
except (ValueError, IndexError, ZeroDivisionError):
    print("error")
""",
    "sudoku": r"""
grid = [[int(c) for c in input().strip()] for _ in range(9)]

def ok(r, c, v):
    if any(grid[r][j] == v for j in range(9) if j != c):
        return False
    if any(grid[i][c] == v for i in range(9) if i != r):
        return False
    br, bc = 3 * (r // 3), 3 * (c // 3)
    return not any(grid[i][j] == v for i in range(br, br + 3) for j in range(bc, bc + 3) if (i, j) != (r, c))

def valid_givens():
    return all(ok(r, c, grid[r][c]) for r in range(9) for c in range(9) if grid[r][c])

def solve():
    for r in range(9):
        for c in range(9):
            if grid[r][c] == 0:
                for v in range(1, 10):
                    if ok(r, c, v):
                        grid[r][c] = v
                        if solve():
                            return True
                        grid[r][c] = 0
                return False
    return True

if valid_givens() and solve():
    print("\n".join("".join(map(str, row)) for row in grid))
else:
    print("no solution")
""",
    "roman": r"""
n = int(input())
out = ""
for value, symbol in [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
                      (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]:
    while n >= value:
        out += symbol
        n -= value
print(out)
""",
    "brackets": r"""
pairs = {")": "(", "]": "[", "}": "{"}
stack = []
balanced = True
for ch in input():
    if ch in "([{":
        stack.append(ch)
    elif ch in pairs:
        if not stack or stack.pop() != pairs[ch]:
            balanced = False
            break
print("balanced" if balanced and not stack else "not balanced")
""",
    "word_frequency": r"""
import re
from collections import Counter
words = re.findall(r"[a-z']+", input().lower())
for word, count in sorted(Counter(words).items(), key=lambda item: (-item[1], item[0]))[:3]:
    print(word, count)
""",
    "grid_path": r"""
from collections import deque
rows = int(input())
grid = [input() for _ in range(rows)]
start = next((r, c) for r in range(rows) for c in range(len(grid[r])) if grid[r][c] == "S")
seen = {start}
queue = deque([(start, 0)])
answer = -1
while queue:
    (r, c), steps = queue.popleft()
    if grid[r][c] == "E":
        answer = steps
        break
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < len(grid[nr]) and grid[nr][nc] != "#" and (nr, nc) not in seen:
            seen.add((nr, nc))
            queue.append(((nr, nc), steps + 1))
print(answer)
""",
    "date_difference": r"""
from datetime import date
first, second = (date.fromisoformat(input().strip()) for _ in range(2))
print(abs((second - first).days))
""",
    "prime_factors": r"""
n = int(input())
parts, factor = [], 2
while factor * factor <= n:
    power = 0
    while n % factor == 0:
        n //= factor
        power += 1
    if power:
        parts.append(f"{factor}^{power}" if power > 1 else str(factor))
    factor += 1
if n > 1:
    parts.append(str(n))
print(" * ".join(parts))
""",
    "spiral": r"""
n = int(input())
m = [list(map(int, input().split())) for _ in range(n)]
out = []
while m:
    out += m.pop(0)
    m = [list(row) for row in zip(*m)][::-1]
print(" ".join(map(str, out)))
""",
    "run_length": r"""
from itertools import groupby
print("".join(f"{ch}{len(list(run))}" for ch, run in groupby(input())))
""",
}
