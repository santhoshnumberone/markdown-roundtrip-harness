import pytest

from benchmarks import checks

ENGINE = checks.Engine()
CASES = checks.load_cases()
DOCS = [c for c in CASES if c.group == "doc"]
LEDGER = checks.load_ledger()
API_SPEC = next(c for c in DOCS if c.name == "api_spec.md")
Node, Document = ENGINE.module.Node, ENGINE.module.Document


def run(case):
    return checks.run_case(ENGINE, case.source)


def render(*nodes):
    return ENGINE.Renderer().render(Document(nodes=list(nodes), source_hash=""))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_round_trip(case):
    r = run(case)
    if case.name in LEDGER["limitations"]:
        assert not r.ok, f"{case.name} passes now: remove it from benchmarks/ledger.json"
    else:
        assert r.ok, f"L1 {r.l1}, O {r.o}, T {r.t}: {r.changes} {r.lacks} {r.error}"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_every_byte_change_is_explained(case):
    r = run(case)
    listed = case.name in LEDGER["normalizations"]
    assert listed == (r.ok and not r.l0), f"benchmarks/ledger.json normalizations are out of date for {case.name}"


@pytest.mark.parametrize("case", DOCS, ids=lambda c: c.name)
def test_ids_are_unique_gap_free_and_in_document_order(case):
    rep = checks.id_report(ENGINE, case.source)
    assert rep["unique"] and not rep["gaps"] and not rep["out_of_order"], rep


@pytest.mark.parametrize("case", DOCS, ids=lambda c: c.name)
def test_documents_parse_without_diagnostics(case):
    assert run(case).diagnostics == []


def test_a_line_no_block_covers_is_reported():
    case = next(c for c in CASES if c.name == "reference_link")
    assert any("not part of any block" in d for d in run(case).diagnostics)


def test_the_ledger_names_only_cases_that_exist():
    names = {c.name for c in CASES}
    assert set(LEDGER["limitations"]) <= names and set(LEDGER["normalizations"]) <= names


def test_the_corpus_is_not_empty():
    assert [c.name for c in DOCS] == ["api_spec.md"]
    assert len(CASES) >= 49


def test_a_crashing_parser_is_reported_not_raised():
    class Boom(ENGINE.Parser):
        def parse(self, text):
            raise ValueError("boom")

    r = checks.run_case(ENGINE, "# x\n", Boom)
    assert not r.ok and r.error == "ValueError: boom"


VARIANTS = checks.simulated_regressions(ENGINE)


@pytest.mark.parametrize("label, parser_cls", VARIANTS, ids=[label for label, _ in VARIANTS])
def test_the_checks_catch_the_old_bugs(label, parser_cls):
    r = checks.run_case(ENGINE, API_SPEC.source, parser_cls)
    assert not (r.o and r.t)


def test_code_block_text_without_a_trailing_newline_still_closes_its_fence():
    assert render(Node("cb1", "code_block", text="x", meta={"language": "py"})) == "```py\nx\n```\n"


def test_heading_text_ending_in_a_hash_is_escaped():
    assert render(Node("h1", "heading", level=2, text="Issue #")) == "## Issue \\#\n"
    assert render(Node("h1", "heading", level=2, text="C#")) == "## C#\n"


def test_table_with_fewer_alignments_than_columns_still_renders():
    table = Node("tbl1", "table", meta={"rows": [["a", "b"], ["1", "2"]], "align": ["left"]})
    assert render(table) == "| a | b |\n| :--- | --- |\n| 1 | 2 |\n"
