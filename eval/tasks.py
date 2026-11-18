"""The coding tasks and their hidden checks.

Each prompt is what a user would type into the chat. The checks are never shown to the
model: each one runs the final program with `stdin` and judges its output (eval/checks.py).
Prompts state the output format, because a format mismatch isn't the skill being measured.
"""

SUDOKU = "530070000\n600195000\n098000060\n800060003\n400803001\n700020006\n060000280\n000419005\n000080079"
SUDOKU_SOLVED = "534678912672195348198342567859761423426853791713924856961537284287419635345286179"

TASKS = [
    {
        "id": "expression",
        "prompt": (
            "Write a Python program that reads one line containing an arithmetic expression "
            "and prints its value. Support + - * /, parentheses, unary minus and decimal "
            "numbers, with normal operator precedence. Do NOT use eval or exec. If the "
            "expression is invalid, print error."
        ),
        "checks": [
            {"stdin": "3 + 4 * (2 - 1)", "type": "number", "value": 7},
            {"stdin": "-(2+3)*2", "type": "number", "value": -10},
            {"stdin": "10/4", "type": "number", "value": 2.5},
            {"stdin": "1 - -1", "type": "number", "value": 2},
            {"stdin": "2 + 3 * 4 - 6 / 2", "type": "number", "value": 11},
            {"stdin": "2*(3+", "type": "contains", "value": "error"},
        ],
    },
    {
        "id": "sudoku",
        "prompt": (
            "Write a Python program that solves a sudoku. It reads 9 lines of 9 digits each, "
            "where 0 means an empty cell, and prints the solved grid as 9 lines of 9 digits. "
            "If the puzzle has no solution (including when the given digits already break "
            "the rules), print no solution."
        ),
        "checks": [
            {"stdin": SUDOKU, "type": "digits_end", "value": SUDOKU_SOLVED},
            {"stdin": "553070000" + SUDOKU[9:], "type": "contains", "value": "no solution"},
        ],
    },
    {
        "id": "roman",
        "prompt": (
            "Write a Python program that reads a whole number from 1 to 3999 and prints it "
            "as a Roman numeral in uppercase."
        ),
        "checks": [
            {"stdin": "1994", "type": "word", "value": "MCMXCIV"},
            {"stdin": "4", "type": "word", "value": "IV"},
            {"stdin": "3999", "type": "word", "value": "MMMCMXCIX"},
            {"stdin": "58", "type": "word", "value": "LVIII"},
            {"stdin": "9", "type": "word", "value": "IX"},
        ],
    },
    {
        "id": "brackets",
        "prompt": (
            "Write a Python program that reads one line and prints balanced if every (, [ "
            "and { in it is closed in the right order, otherwise prints not balanced. Other "
            "characters are ignored."
        ),
        "checks": [
            {
                "stdin": "([]{})",
                "type": "contains",
                "value": "balanced",
                "absent": ["not balanced"],
            },
            {"stdin": "([)]", "type": "contains", "value": "not balanced"},
            {"stdin": "((", "type": "contains", "value": "not balanced"},
            {"stdin": "a(b)c", "type": "contains", "value": "balanced", "absent": ["not balanced"]},
        ],
    },
    {
        "id": "word_frequency",
        "prompt": (
            "Write a Python program that reads one line of text and prints its 3 most common "
            "words, one per line as `word count`, most common first. Treat words "
            "case-insensitively (print them in lowercase) and ignore punctuation. Break ties "
            "alphabetically."
        ),
        "checks": [
            {
                "stdin": "The cat and the dog. The cat ran!",
                "type": "in_order",
                "value": ["the 3", "cat 2", "and 1"],
            },
            {
                "stdin": "Hello, hello WORLD! world? Zebra",
                "type": "in_order",
                "value": ["hello 2", "world 2", "zebra 1"],
            },
        ],
    },
    {
        "id": "grid_path",
        "prompt": (
            "Write a Python program that reads the number of rows, then that many lines of a "
            "grid made of S (start), E (end), # (wall) and . (open). Moving up, down, left or "
            "right, print the number of steps on the shortest path from S to E, or -1 if "
            "there is no path."
        ),
        "checks": [
            {"stdin": "3\nS.#\n.##\n..E", "type": "number", "value": 4},
            {"stdin": "2\nS#\n#E", "type": "number", "value": -1},
            {"stdin": "1\nS..E", "type": "number", "value": 3},
        ],
    },
    {
        "id": "date_difference",
        "prompt": (
            "Write a Python program that reads two dates in YYYY-MM-DD format, one per line, "
            "and prints how many days apart they are, as a positive number."
        ),
        "checks": [
            {"stdin": "2024-01-01\n2024-03-01", "type": "number", "value": 60},
            {"stdin": "2023-12-25\n2023-12-24", "type": "number", "value": 1},
            {"stdin": "2000-02-28\n2000-03-01", "type": "number", "value": 2},
        ],
    },
    {
        "id": "prime_factors",
        "prompt": (
            "Write a Python program that reads a whole number greater than 1 and prints its "
            "prime factorization like 2^3 * 3^2 * 5: factors in increasing order, joined by "
            "' * ', with an exponent only when it is above 1."
        ),
        "checks": [
            {"stdin": "360", "type": "squashed", "value": "2^3 * 3^2 * 5"},
            {"stdin": "97", "type": "contains", "value": "97", "absent": ["*", "^"]},
            {"stdin": "1024", "type": "squashed", "value": "2^10"},
        ],
    },
    {
        "id": "spiral",
        "prompt": (
            "Write a Python program that reads n, then n lines of n whole numbers separated by "
            "spaces, and prints the numbers in clockwise spiral order starting at the top-left, "
            "on one line separated by spaces."
        ),
        "checks": [
            {
                "stdin": "3\n1 2 3\n4 5 6\n7 8 9",
                "type": "tail_numbers",
                "value": [1, 2, 3, 6, 9, 8, 7, 4, 5],
            },
            {"stdin": "2\n1 2\n3 4", "type": "tail_numbers", "value": [1, 2, 4, 3]},
            {"stdin": "1\n5", "type": "tail_numbers", "value": [5]},
        ],
    },
    {
        "id": "run_length",
        "prompt": (
            "Write a Python program that reads one line and prints its run-length encoding: "
            "each run of the same character as the character followed by its count, so "
            "aaabcc becomes a3b1c2."
        ),
        "checks": [
            {"stdin": "aaabccdddd", "type": "word", "value": "a3b1c2d4"},
            {"stdin": "x", "type": "word", "value": "x1"},
            {"stdin": "zzzzzzzzzzzz", "type": "word", "value": "z12"},
        ],
    },
]
