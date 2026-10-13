"""Run every round-trip check over the example documents and constructs.

    python benchmarks/roundtrip_harness.py
    python benchmarks/roundtrip_harness.py --failures
    python benchmarks/roundtrip_harness.py --parser benchmarks/baseline/MarkdownParser_phase1.py
    python benchmarks/roundtrip_harness.py --selftest --json results/after.json | tee results/after.txt

--parser runs the same checks against any file with the MarkdownParser API.
Exit status is 1 when a case fails that benchmarks/ledger.json does not list as a limitation.
"""
import argparse
import importlib.metadata as imd
import json
import platform
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks import checks  # noqa: E402

REFERENCE = checks.ROOT / "fixtures" / "article2" / "ast_reference.json"


def versions() -> dict:
    def get(pkg):
        try:
            return imd.version(pkg)
        except imd.PackageNotFoundError:
            return "not installed"

    return {"python": platform.python_version(), "markdown-it-py": get("markdown-it-py"),
            "linkify-it-py": get("linkify-it-py")}


def flag(ok: bool) -> str:
    return "ok" if ok else "FAIL"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parser", help="run against this MarkdownParser.py instead of the repo's")
    ap.add_argument("--selftest", action="store_true", help="also re-create three old bugs and see which checks fire")
    ap.add_argument("--json", help="also write the full results here")
    ap.add_argument("--failures", action="store_true", help="list only the cases that fail in the case table")
    args = ap.parse_args()

    engine = checks.Engine(args.parser)
    ledger = checks.load_ledger()
    shown = {"limitations": {}, "normalizations": {}} if args.parser else ledger  # the ledger describes the repo's parser
    fp, env = engine.fingerprint(), versions()
    print("== engine ==")
    print(f"{fp['file']}  {fp['bytes']} bytes  sha256 {fp['sha256']}")
    print("  ".join(f"{k} {v}" for k, v in env.items()))

    cases = checks.load_cases()
    results = {c.name: checks.run_case(engine, c.source) for c in cases}

    print("\n== cases ==")
    print(f"{'group':<10}{'case':<36}{'L0':<6}{'L1':<6}{'O':<6}{'T':<6}{'diag':<6}{'ledger':<13}what")
    for c in cases:
        r = results[c.name]
        if args.failures and r.ok:
            continue
        status = ("limitation" if c.name in shown["limitations"]
                  else "normalized" if c.name in shown["normalizations"] else "")
        what = ("CRASH " + r.error) if r.error else ", ".join(r.changes)
        if r.lacks:
            what += (" | " if what else "") + "model lacks " + ", ".join(f"{k} {v:+d}" for k, v in r.lacks.items())
        if not what:
            what = shown["normalizations"].get(c.name, "")
        print(f"{c.group:<10}{c.name[:35]:<36}{'same' if r.l0 else 'diff':<6}{flag(r.l1):<6}{flag(r.o):<6}"
              f"{flag(r.t):<6}{len(r.diagnostics):<6}{status:<13}{what[:70]}")

    n = len(cases)
    count = lambda pred: sum(1 for r in results.values() if pred(r))  # noqa: E731
    blind = [c.name for c in cases if results[c.name].l1 and not (results[c.name].o and results[c.name].t)]
    mute = [name for name in blind if not results[name].diagnostics]
    unexpected = [c.name for c in cases if not results[c.name].ok and c.name not in ledger["limitations"]]
    print("\n== summary ==")
    print(f"cases {n} (documents {sum(c.group == 'doc' for c in cases)}, "
          f"constructs {sum(c.group == 'construct' for c in cases)})")
    print(f"L0 byte-identical {count(lambda r: r.l0)}/{n} | L1 ok {count(lambda r: r.l1)}/{n} | "
          f"O ok {count(lambda r: r.o)}/{n} | T ok {count(lambda r: r.t)}/{n}")
    print(f"L1 alone calls {count(lambda r: r.l1)}/{n} healthy. L1, O and T all agree on {count(lambda r: r.ok)}/{n}.")
    print("L1 fails            :", ", ".join(c.name for c in cases if not results[c.name].l1) or "none")
    print("L1 ok, O or T fails :", ", ".join(blind) or "none")
    print("  of those the parser reported nothing for:", ", ".join(mute) or "none")
    print("crashed             :", ", ".join(c.name for c in cases if results[c.name].error) or "none")
    print("failing, not in ledger.json:", ", ".join(unexpected) or "none")

    print("\n== ids (documents) ==")
    ids = {}
    for c in cases:
        if c.group != "doc":
            continue
        rep = ids[c.name] = checks.id_report(engine, c.source)
        problems = []
        if not rep["unique"]:
            problems.append("duplicate ids")
        if rep["gaps"]:
            problems.append("gaps " + "; ".join(checks.runs(g, p) for p, g in rep["gaps"].items()))
        if rep["out_of_order"]:
            problems.append("not in document order " + "; ".join(
                f"{p}: {x[0][0]} before {x[0][1]}" for p, x in rep["out_of_order"].items()))
        sp, sh = rep["shift"]["paragraph"], rep["shift"]["heading"]
        print(f"{c.name:<20}{rep['nodes']:>3} nodes  {'; '.join(problems) or 'unique, gap-free, document order'}")
        print(f"{'':<20}insert a paragraph at the top: {sp['moved']}/{sp['of']} existing ids change; "
              f"insert a heading: {sh['moved']}/{sh['of']}")

    par = None
    if REFERENCE.exists():
        api = next(c.source for c in cases if c.name == "api_spec.md")
        par = checks.parity(engine, api, REFERENCE)
        print("\n== parity with Article 2's ast_reference.json (api_spec.md) ==")
        print(f"nodes engine {par['nodes'][0]} / reference {par['nodes'][1]}; "
              f"same id at the same position {par['same_id_same_position']}/{par['nodes'][1]}")
        print("same id, different node:", ", ".join(par["same_id_other_node"]) or "none")
        print("only in engine   :", ", ".join(par["only_engine"]) or "none")
        print("only in reference:", ", ".join(par["only_reference"]) or "none")

    sim = None
    if args.selftest:
        api = next(c.source for c in cases if c.name == "api_spec.md")
        print("\n== simulated regressions on api_spec.md (variants written from ARCHITECTURE.md, not the original code) ==")
        print(f"{'variant':<40}{'L0':<6}{'L1':<6}{'O':<6}{'T':<6}caught by")
        sim = []
        for label, cls in checks.simulated_regressions(engine):
            r = checks.run_case(engine, api, cls)
            caught = [k for k, ok in (("L1", r.l1), ("O", r.o), ("T", r.t)) if not ok]
            sim.append({"variant": label, "l0": r.l0, "l1": r.l1, "o": r.o, "t": r.t, "caught_by": caught})
            print(f"{label:<40}{'same' if r.l0 else 'diff':<6}{flag(r.l1):<6}{flag(r.o):<6}{flag(r.t):<6}"
                  f"{', '.join(caught) or 'nothing'}")
        print(f"caught by O or T: {sum(any(k in s['caught_by'] for k in ('O', 'T')) for s in sim)}/{len(sim)}; "
              f"caught by L1: {sum('L1' in s['caught_by'] for s in sim)}/{len(sim)}")

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "engine": fp, "environment": env,
            "cases": [{"group": c.group, "name": c.name, **asdict(results[c.name])} for c in cases],
            "ids": ids, "parity": par, "simulated_regressions": sim,
        }, indent=2), encoding="utf-8")
        print(f"\nwrote {out}")

    return 1 if unexpected else 0


if __name__ == "__main__":
    sys.exit(main())
