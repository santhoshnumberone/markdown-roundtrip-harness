import hashlib
import json
import re

import pytest

from benchmarks import checks, raw_text_demo

ENGINE = checks.Engine()
FIXTURES = checks.ROOT / "fixtures" / "article2"
API_SPEC = (checks.ROOT / "examples" / "api_spec.md").read_bytes().decode("utf-8")
GOLD = json.loads((FIXTURES / "gold_set.json").read_text(encoding="utf-8"))
NODES = {n.id: n for n in checks.flatten(ENGINE.Parser().parse(API_SPEC).nodes)}
KIND = {"tbl": "table", "bq": "blockquote", "lst": "list", "li": "list_item", "h": "heading",
        "p": "paragraph", "cb": "code_block"}
OPERATIONS = [(c["case_id"], op) for c in GOLD["cases"] for op in c["expected_operations"] or []]


def test_the_vendored_files_match_their_recorded_checksums():
    text = (FIXTURES / "PROVENANCE.md").read_text(encoding="utf-8")
    recorded = dict(re.findall(r"\| `([\w.]+)` \|[^|]*\| `([0-9a-f]{64})` \|", text))
    assert set(recorded) == {"ast_reference.json", "gold_set.json"}
    for name, sha in recorded.items():
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == sha


def test_the_input_document_is_the_article_2_document():
    reference = json.loads((FIXTURES / "ast_reference.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(API_SPEC.encode()).hexdigest().startswith(reference["source_hash"])


def test_ids_match_the_article_2_reference():
    p = checks.parity(ENGINE, API_SPEC, FIXTURES / "ast_reference.json")
    assert p["nodes"][0] == p["nodes"][1] == p["same_id_same_position"], p
    assert not (p["same_id_other_node"] or p["only_engine"] or p["only_reference"]), p


@pytest.mark.parametrize("entry", OPERATIONS, ids=[f"{case}:{op['op']}" for case, op in OPERATIONS])
def test_every_node_an_article_2_gold_operation_targets_exists(entry):
    _, op = entry
    for key in ("target", "parent"):
        if key in op:
            node = NODES[op[key]]  # a KeyError here means the id does not exist
            assert node.kind == KIND[op[key].rstrip("0123456789")]
    if op["op"] == "Update" and "field" in op:  # "Pro.Requests/min" names a table cell
        row, column = op["field"].split(".", 1)
        header, *body = NODES[op["target"]].meta["rows"]
        assert column in header and any(cells[0] == row for cells in body)


def test_a_plain_replace_of_the_article_2_edit_also_changes_another_row():
    r = raw_text_demo.run(ENGINE)
    assert r["raw"]["lines_changed"] == 2 and r["typed"]["lines_vs_unedited_render"] == 1
