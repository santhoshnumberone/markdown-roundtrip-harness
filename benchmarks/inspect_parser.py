"""Inspect how MarkdownParser handles one Markdown file.

Run from the repo root:
    python benchmarks/inspect_parser.py examples/api_spec.md
    python benchmarks/inspect_parser.py examples/api_spec.md --view
"""
import difflib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from MarkdownParser import MarkdownParser, MarkdownRenderer  # noqa: E402
from benchmarks.checks import structure  # noqa: E402  (the L1 definition lives in one place)


def dump(nodes, depth=0):
    for n in nodes:
        preview = n.text[:40].replace("\n", " ")
        print(f"{'  ' * depth}{n.id:<9}{n.kind:<12}{preview!r}")
        dump(n.children, depth + 1)


def view(nodes, depth=0, lines=None):  # readable lines, used for L2 via diff
    lines = [] if lines is None else lines
    for n in nodes:
        if n.kind == "heading":
            label = f"h{n.level} {n.text}"
        elif n.kind == "table":
            rows = n.meta["rows"]
            header = " | ".join(rows[0]) if rows else ""
            label = f"{max(len(rows) - 1, 0)} rows | header: {header}"
        elif n.kind == "code_block":
            first = n.text.splitlines()[0] if n.text.strip() else ""
            label = f"[{n.meta.get('language', '')}] {first}"
        elif n.kind == "list":
            label = "ordered" if n.meta.get("ordered") else "bullet"
        else:  # paragraph, blockquote, list_item: soft line breaks become spaces
            label = n.text.replace("\n", " ")
        lines.append(f"{'  ' * depth}{n.kind} | {label}".rstrip())
        view(n.children, depth + 1, lines)
    return lines


def uncovered_lines(source, tokens):  # non-blank lines that no token's map covers
    covered = set()
    for t in tokens:
        if t.map:
            covered.update(range(t.map[0], t.map[1]))
    return [(i + 1, line) for i, line in enumerate(re.split(r"\r\n?|\n", source))
            if line.strip() and i not in covered]


if __name__ == "__main__":
    source = open(sys.argv[1], encoding="utf-8").read()
    parser = MarkdownParser()
    doc = parser.parse(source)

    if "--view" in sys.argv:
        print("\n".join(view(doc.nodes)))
        sys.exit(0)

    rendered = MarkdownRenderer().render(doc)
    print("== NODES ==")
    dump(doc.nodes)
    print("\n== L0 exact text round trip:", rendered == source)
    print("== L1 same structure after one more pass:",
          structure(MarkdownParser().parse(rendered).nodes) == structure(doc.nodes))
    if rendered != source:
        diff = difflib.unified_diff(source.splitlines(), rendered.splitlines(),
                                    "source", "rendered", lineterm="", n=0)
        print("\n== first differences ==")
        print("\n".join(list(diff)[:20]))
    print("\n== diagnostics (reported by the parser) ==")
    for d in getattr(parser, "diagnostics", []):
        print(" ", d)
    print("\n== source lines no token covers ==")
    for lineno, line in uncovered_lines(source, parser.md.parse(source)):
        print(f"  line {lineno}: {line!r}")
