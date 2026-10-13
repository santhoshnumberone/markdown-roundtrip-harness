"""Random Markdown documents for round-trip testing.

    python benchmarks/fuzz.py [N] [--parser PATH]

Each document mixes the constructs the model supports. The generator keeps clear of the
shapes listed as limitations in ledger.json (lazy lines that look like a table, a setext
underline glued to item text), so a failure here is a new bug, not a known one.
"""
import argparse
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks import checks  # noqa: E402

PHRASES = ["plain words", "with `code`", "some **bold** text", "an [inline link](http://x.y/z) here",
           "pipes | in | text", "a_b_c and *em*", "ends with hash #", "1986\\. escaped number",
           "<b>tag</b> inline"]


def phrase(r):
    return r.choice(PHRASES)


def paragraph(r, depth):
    lines = [phrase(r) for _ in range(r.choice([1, 1, 2, 3]))]
    if len(lines) > 1 and r.random() < 0.2:
        lines[0] += "  "  # hard break
    return lines


def heading(r, depth):
    return ["#" * r.choice([1, 2, 3]) + " " + phrase(r)]


def rule(r, depth):
    return [r.choice(["---", "***", "___", "-----"])]


def html(r, depth):
    return [r.choice(["<div>x</div>", "<!-- note -->", "<details>\n<summary>s</summary>\n</details>"])]


def fence(r, depth):
    body = [r.choice(["x = 1", "", "    indented", "```", "~~~", "a | b", "``", "#!/bin/sh"])
            for _ in range(r.choice([0, 1, 2, 3]))]
    ch = r.choice(["`", "`", "~"])
    longest = max((len(m) for line in body for m in re.findall(re.escape(ch) + "+", line)), default=0)
    mark = ch * max(3, longest + 1)
    return [mark + r.choice(["", "py", "bash", "md"])] + body + [mark]


def table(r, depth):
    cols = r.choice([1, 2, 3])
    row = lambda cells: "| " + " | ".join(cells) + " |"  # noqa: E731
    cell = lambda: r.choice(["a", "b c", "x \\| y", "`z`", "1", ""])  # noqa: E731
    rules = [r.choice(["---", ":--", "--:", ":-:"]) for _ in range(cols)]
    return ([row([f"h{c}" for c in range(cols)]), "|" + "|".join(rules) + "|"]
            + [row([cell() for _ in range(cols)]) for _ in range(r.choice([1, 2]))])


def quote(r, depth):
    return [("> " + line) if line else ">" for line in blocks(r, depth + 1, r.choice([1, 2]))]


def listing(r, depth):
    ordered = r.random() < 0.5
    start = r.choice([0, 1, 1, 3, 9, 10]) if ordered else 0
    tight = r.random() < 0.6
    count = r.choice([1, 2, 3])
    lines = []
    for k in range(count):
        marker = f"{start + k}. " if ordered else "- "
        body = [phrase(r)]
        if depth < 3:
            for _ in range(r.choice([0, 0, 1, 2])):
                make = r.choice([listing, fence, quote, paragraph, table, rule, html])
                # a tight item may only glue a list or a fence to the line above it: anything
                # else would be absorbed as a lazy continuation or read as a setext underline
                if not tight or make not in (listing, fence):
                    body.append("")
                body += make(r, depth + 1)
        lines += [marker + body[0]] + [" " * len(marker) + ln if ln else ln for ln in body[1:]]
        if not tight and k < count - 1:
            lines.append("")
    return lines


BLOCKS = [heading, paragraph, paragraph, listing, listing, fence, quote, table, rule, html]


def blocks(r, depth, count):
    lines = []
    for _ in range(count):
        if lines:
            lines += [""] * r.choice([1, 1, 2])
        lines += r.choice(BLOCKS)(r, depth)
    return lines


def document(seed: int) -> str:
    r = random.Random(seed)
    return "\n".join(blocks(r, 0, r.choice([1, 2, 3, 4, 5]))) + "\n"


def failures(engine, count=3000) -> list:
    """(seed, Result) for every random document that fails L1, O or T."""
    out = []
    for seed in range(count):
        result = checks.run_case(engine, document(seed))
        if not result.ok:
            out.append((seed, result))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("count", nargs="?", type=int, default=3000)
    ap.add_argument("--parser", help="run against this MarkdownParser.py instead of the repo's")
    args = ap.parse_args()
    engine = checks.Engine(args.parser)
    bad = failures(engine, args.count)
    print(f"{engine.fingerprint()['file']}: {len(bad)}/{args.count} random documents fail L1, O or T")
    for seed, r in bad[:3]:
        print(f"  seed {seed}: L1 {r.l1}  O {r.o}  T {r.t}  {r.changes[:2]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
