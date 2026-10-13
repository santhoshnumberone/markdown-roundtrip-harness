"""Round-trip checks for the document model. Shared by roundtrip_harness.py and the tests.

  L0  byte-identical   render(parse(x)) == x                      formatting survived
  L1  structural       parse(render(parse(x))) == parse(x)        the tree is stable
  O   oracle           html(x) == html(render(parse(x)))          it still means the same
  T   typed            the model holds a node for every table, quote, list, list item,
                       code block, heading and rule that the independent HTML shows

L1 compares the model with itself, so it cannot see what the parser dropped on the first
pass. O and T compare against markdown-it's own HTML: same tokenizer, different path. They
test our model and renderer, not markdown-it.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from markdown_it import MarkdownIt

if sys.version_info < (3, 10):  # the evidence is claimed for 3.10+, so refuse to produce it elsewhere
    raise SystemExit(f"Python 3.10+ required, this is {platform.python_version()}. "
                     "Run python -m pytest and python benchmarks/... from the project venv.")

ROOT = Path(__file__).resolve().parents[1]
ORACLE = MarkdownIt("gfm-like")


class Engine:
    """The parser and renderer under test: the repo's MarkdownParser.py, or any file with the same API."""

    def __init__(self, path=None):
        self.path = Path(path or ROOT / "MarkdownParser.py").resolve()
        name = "engine_" + hashlib.sha1(str(self.path).encode()).hexdigest()[:8]
        spec = importlib.util.spec_from_file_location(name, self.path)
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[name] = self.module
        spec.loader.exec_module(self.module)
        self.Parser = self.module.MarkdownParser
        self.Renderer = self.module.MarkdownRenderer

    def fingerprint(self) -> dict:
        data = self.path.read_bytes()
        try:
            shown = str(self.path.relative_to(ROOT))
        except ValueError:
            shown = self.path.name
        return {"file": shown, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()[:12]}


# ------------------------------------------------------------------ tree helpers
def flatten(nodes, out=None):
    out = [] if out is None else out
    for n in nodes:
        out.append(n)
        flatten(n.children, out)
    return out


def structure(nodes):
    """The tree without ids, compared for L1. Every meta key counts."""
    return [(n.kind, n.level, n.text, json.dumps(n.meta, sort_keys=True), structure(n.children))
            for n in nodes]


# ------------------------------------------------------------------ O and T
TAGS = {  # what the HTML shows -> the node kinds that must account for it
    "heading": (re.compile(r"<h[1-6][ >]"), {"heading"}),
    "list": (re.compile(r"<(?:ul|ol)[ >]"), {"list"}),
    "list_item": (re.compile(r"<li[ >]"), {"list_item"}),
    "code_block": (re.compile(r"<pre[ >]"), {"code_block"}),
    "table": (re.compile(r"<table[ >]"), {"table"}),
    "blockquote": (re.compile(r"<blockquote[ >]"), {"blockquote"}),
    "rule": (re.compile(r"<hr[ />]"), {"thematic_break"}),
}


def html_counts(html: str) -> dict:
    return {k: len(rx.findall(html)) for k, (rx, _) in TAGS.items()}


def model_counts(nodes) -> dict:
    flat = flatten(nodes)
    return {k: sum(n.kind in kinds for n in flat) for k, (_, kinds) in TAGS.items()}


def _tag_hist(html: str) -> dict:
    hist: dict = {}
    for m in re.finditer(r"<([a-z0-9]+)((?:\s[^>]*)?)>", html):
        tag, attrs = m.group(1), m.group(2)
        hist[tag] = hist.get(tag, 0) + 1
        for a in re.findall(r"\s(start|style)=", attrs):
            hist[f"{tag}[{a}]"] = hist.get(f"{tag}[{a}]", 0) + 1
    return hist


def _tag_changes(h_src: str, h_out: str) -> list:
    a, b = _tag_hist(h_src), _tag_hist(h_out)
    changes = [f"{k} {b.get(k, 0) - a.get(k, 0):+d}" for k in sorted(set(a) | set(b))
               if a.get(k, 0) != b.get(k, 0)]
    if not changes:  # same tags, different text
        for x, y in zip(h_src.splitlines() + [""], h_out.splitlines() + [""]):
            if x != y:
                return [f"text: {x[:40]!r} -> {y[:40]!r}"]
    return changes


# ------------------------------------------------------------------ one case
@dataclass
class Result:
    l0: bool
    l1: bool
    o: bool
    t: bool
    diagnostics: list = field(default_factory=list)  # what the parser reported
    changes: list = field(default_factory=list)      # tag-level differences between the two HTMLs
    lacks: dict = field(default_factory=dict)        # kinds the HTML shows that the model lacks
    error: str = ""                                  # set when the case crashed

    @property
    def ok(self) -> bool:
        return not self.error and self.l1 and self.o and self.t


def run_case(engine: Engine, source: str, parser_cls=None) -> Result:
    """A crash is a result, not a reason to stop: it comes back as a failing Result with .error set."""
    try:
        make = parser_cls or engine.Parser
        parser = make()
        doc = parser.parse(source)
        out = engine.Renderer().render(doc)
        h_src, h_out = ORACLE.render(source), ORACLE.render(out)
        have, want = model_counts(doc.nodes), html_counts(h_src)
        return Result(
            l0=out == source,
            l1=structure(make().parse(out).nodes) == structure(doc.nodes),
            o=h_src == h_out,
            t=have == want,
            diagnostics=list(getattr(parser, "diagnostics", [])),
            changes=_tag_changes(h_src, h_out) if h_src != h_out else [],
            lacks={k: want[k] - have[k] for k in want if want[k] != have[k]},
        )
    except Exception as exc:  # noqa: BLE001
        return Result(l0=False, l1=False, o=False, t=False, error=f"{type(exc).__name__}: {exc}")


# ------------------------------------------------------------------ cases and ledger
SPECIAL = {  # byte-level cases: built here because an editor may "fix" them in a saved file
    "crlf_line_endings": "# T\r\n\r\ntext\r\n",
    "no_trailing_newline": "# T\n\ntext",
    "empty_document": "",
}


@dataclass
class Case:
    group: str  # doc | construct
    name: str
    source: str


def load_cases() -> list:
    read = lambda p: p.read_bytes().decode("utf-8")  # noqa: E731  (keeps CRLF intact)
    cases = [Case("doc", p.name, read(p)) for p in sorted((ROOT / "examples").glob("*.md"))
             if p.name.lower() != "readme.md"]
    cases += [Case("construct", p.stem, read(p)) for p in sorted((ROOT / "examples" / "constructs").glob("*.md"))]
    cases += [Case("construct", name, src) for name, src in SPECIAL.items()]
    return cases


def load_ledger() -> dict:
    """limitations: cases that fail by design. normalizations: why a passing case is not byte-identical."""
    return json.loads((ROOT / "benchmarks" / "ledger.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ ids
def runs(numbers: list, prefix: str) -> str:
    """[4, 5, 6, 7, 9] -> 'p4-p7, p9'"""
    out, start, prev = [], None, None
    for n in numbers + [None]:
        if start is not None and (n is None or n != prev + 1):
            out.append(f"{prefix}{start}" if start == prev else f"{prefix}{start}-{prefix}{prev}")
            start = None
        if n is not None:
            start = n if start is None else start
            prev = n
    return ", ".join(out)


def id_report(engine: Engine, source: str) -> dict:
    flat = flatten(engine.Parser().parse(source).nodes)
    nums: dict = {}
    for n in flat:
        prefix, num = re.fullmatch(r"([a-z]+)(\d+)", n.id).groups()
        nums.setdefault(prefix, []).append(int(num))
    gaps = {p: sorted(set(range(1, max(v) + 1)) - set(v)) for p, v in nums.items()}
    out_of_order = {p: [(a, b) for a, b in zip(v, v[1:]) if b < a] for p, v in nums.items()}

    def keyed(nodes):  # (kind, text, n-th duplicate) -> id
        seen, out = {}, {}
        for n in flatten(nodes):
            k = seen.get((n.kind, n.text), 0)
            seen[(n.kind, n.text)] = k + 1
            out[(n.kind, n.text, k)] = n.id
        return out

    before = keyed(engine.Parser().parse(source).nodes)
    shift = {}
    for label, prefix in (("paragraph", "A new paragraph at the top.\n\n"), ("heading", "# A new title at the top\n\n")):
        after = keyed(engine.Parser().parse(prefix + source).nodes)
        shared = [k for k in before if k in after]
        moved = [k for k in shared if before[k] != after[k]]
        shift[label] = {"moved": len(moved), "of": len(shared)}
    return {
        "nodes": len(flat),
        "unique": len({n.id for n in flat}) == len(flat),
        "gaps": {p: g for p, g in gaps.items() if g},
        "out_of_order": {p: x for p, x in out_of_order.items() if x},
        "shift": shift,
    }


def parity(engine: Engine, source: str, reference_path: Path) -> dict:
    """Compare the engine's ids with the node list Article 2's planner was graded against."""
    ref = json.loads(Path(reference_path).read_text(encoding="utf-8"))
    ref_nodes = []

    def walk(nodes):
        for n in nodes:
            ref_nodes.append(n)
            walk(n.get("children", []))

    walk(ref["nodes"])
    eng_nodes = flatten(engine.Parser().parse(source).nodes)
    eng = {n.id: (n.kind, n.text.strip()) for n in eng_nodes}
    ref_by_id = {n["id"]: (n["kind"], (n.get("text") or "").strip()) for n in ref_nodes}
    containers = {"list", "table"}  # compared by kind only
    same_id_other_node = sorted(
        (i for i in set(eng) & set(ref_by_id)
         if eng[i][0] != ref_by_id[i][0] or (eng[i][0] not in containers and eng[i][1] != ref_by_id[i][1])),
        key=lambda s: (re.sub(r"\d", "", s), int(re.sub(r"\D", "", s))))
    return {
        "nodes": [len(eng_nodes), len(ref_nodes)],
        "same_id_same_position": sum(a.id == b["id"] for a, b in zip(eng_nodes, ref_nodes)),
        "same_id_other_node": same_id_other_node,
        "only_engine": sorted(set(eng) - set(ref_by_id)),
        "only_reference": sorted(set(ref_by_id) - set(eng)),
    }


# ------------------------------------------------------------------ does the harness catch real bugs?
def simulated_regressions(engine: Engine) -> list:
    """Three bugs recorded in ARCHITECTURE.md, re-created as parser variants.
    These follow the written descriptions. They are not the original code."""
    Base, mod = engine.Parser, engine.module

    class CommonMarkPreset(Base):  # tables fall through as paragraph text
        def __init__(self):
            super().__init__()
            self.md = MarkdownIt("commonmark")

    class BlockquoteDemoted(Base):  # the quote marker is lost, the paragraph stays
        def parse(self, text):
            self._counters, self.diagnostics = {}, []
            tokens = [t for t in self.md.parse(text) if not t.type.startswith("blockquote_")]
            return mod.Document(nodes=self._walk(tokens), source_hash="")

    class NestedListsDropped(Base):  # a list item keeps only its own line
        def _walk_list_items(self, tokens):
            items = super()._walk_list_items(tokens)
            for item in items:
                item.children = []
            return items

    return [("table not parsed (commonmark preset)", CommonMarkPreset),
            ("blockquote demoted to paragraph", BlockquoteDemoted),
            ("nested lists dropped", NestedListsDropped)]
