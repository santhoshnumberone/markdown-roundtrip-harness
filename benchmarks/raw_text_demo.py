"""One of Article 2's test edits, done two ways.

    python benchmarks/raw_text_demo.py [--json PATH]

Case update_01: "Change the Pro tier's rate limit to 2000 requests per minute."
A plain text replace of the old value changes more than the Pro row. Setting the
table cell through the model changes one cell. This is a naive replace, not an LLM
rewrite: the smallest version of the problem that text has no addresses.
"""
import argparse
import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks import checks  # noqa: E402


def diff(before: str, after: str) -> list:
    """The changed lines of a zero-context unified diff: '-old' lines, then '+new' lines."""
    lines = list(difflib.unified_diff(before.splitlines(), after.splitlines(), "", "", lineterm="", n=0))[2:]
    return [ln for ln in lines if not ln.startswith("@@")]


def removed(lines: list) -> int:
    return sum(ln.startswith("-") for ln in lines)


def run(engine) -> dict:
    gold = json.loads((checks.ROOT / "fixtures" / "article2" / "gold_set.json").read_text(encoding="utf-8"))
    case = next(c for c in gold["cases"] if c["case_id"] == "update_01")
    op = case["expected_operations"][0]  # Update tbl1, field "Pro.Requests/min", value "2000"
    source = (checks.ROOT / "examples" / "api_spec.md").read_bytes().decode("utf-8")

    doc = engine.Parser().parse(source)
    table = next(n for n in checks.flatten(doc.nodes) if n.id == op["target"])
    row_name, column = op["field"].split(".", 1)
    header, *body = table.meta["rows"]
    col = header.index(column)
    row = next(i for i, cells in enumerate(body, 1) if cells[0] == row_name)
    old, new = table.meta["rows"][row][col], op["value"]

    raw = diff(source, source.replace(old, new))
    unedited = engine.Renderer().render(engine.Parser().parse(source))
    table.meta["rows"][row][col] = new  # by hand, until Article 4's applier exists
    edited = engine.Renderer().render(doc)
    typed = diff(unedited, edited)
    gone = [ln[1:] for ln in raw if ln.startswith("-")]
    came = [ln[1:] for ln in raw if ln.startswith("+")]
    unasked = [(b, a) for b, a in zip(gone, came) if row_name not in b]
    return {
        "case": case["case_id"], "instruction": case["instruction"], "target": op["target"], "field": op["field"],
        "old": old, "new": new,
        "raw": {"lines_changed": removed(raw), "diff": raw, "unasked": unasked},
        "typed": {"cells_changed": 1, "lines_vs_unedited_render": removed(typed),
                  "lines_vs_source": removed(diff(source, edited)), "diff": typed},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="also write the result here")
    args = ap.parse_args()
    r = run(checks.Engine())
    print(f"{r['instruction']}   ({r['case']} from Article 2's gold set)\n")
    print(f"plain text replace of {r['old']} with {r['new']}: {r['raw']['lines_changed']} lines change")
    for ln in r["raw"]["diff"]:
        print("   " + ln)
    for before, after in r["raw"]["unasked"]:
        print(f"\n   not asked for: {before.strip()}  ->  {after.strip()}")
    print(f"\nset {r['target']} cell [{r['field']}] through the model: {r['typed']['cells_changed']} cell changes")
    for ln in r["typed"]["diff"]:
        print("   " + ln)
    print(f"   lines that differ from rendering the unedited model: {r['typed']['lines_vs_unedited_render']}")
    print(f"   lines that differ from the original file: {r['typed']['lines_vs_source']} "
          "(the extra one is the table separator row being rewritten)")
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(r, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
