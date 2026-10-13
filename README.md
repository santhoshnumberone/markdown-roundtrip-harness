# markdown-roundtrip-harness

A typed document model for Markdown (`Node` and `Document` over markdown-it-py), a renderer, and a harness that checks whether a document survives parse and render without losing anything. The checks do not trust the model they test. Part 3 of a series on a deterministic document transformation engine. Its inputs come from Part 2: the document, the node ids and the test edits Part 2's planner was graded on.

> Scope note: the checks, cases and fixes here were designed around one document, Part 2's `api_spec.md`, plus 48 small constructs and seeded random documents. They need testing and validation on other kinds of documents before anyone relies on them.

**Medium article — [My Round-Trip Test Passed While My Parser Was Losing Information](https://medium.com/@santhoshnumber1/my-round-trip-test-passed-while-my-parser-was-losing-information-af62650b454c)**

![L1 passes, the oracle and typed checks fail](docs/03-selftest.gif)

## Results

Measured on Python 3.10.20, markdown-it-py 4.2.0.

|  | Phase 1 parser | Fixed parser |
|---|---|---|
| Cases where L1, O and T all pass | 24/49 | 44/49 |
| Cases L1 alone calls healthy | 42/49 | 46/49 |
| Cases byte-identical (L0) | 9/49 | 30/49 |
| Node ids matching Part 2 | 34/46 | 46/46 |
| Random documents failing | 2515/3000 | 0/3000 |

49 cases: Part 2's `api_spec.md` and 48 constructs. A case passes when L1, O and T all hold. L0 (byte-identical) is reported and never required: the renderer normalizes formatting, and `benchmarks/ledger.json` explains every byte that changes.

| Check | Question it answers | How |
|---|---|---|
| L0 | Did the formatting survive? | render(parse(x)) equals x byte for byte |
| L1 | Is the tree stable? | parse(render(parse(x))) equals parse(x) |
| O | Does it still mean the same? | HTML of x equals HTML of render(parse(x)) |
| T | Did the parser keep every construct? | the model has a node for every table, quote, list, item, code block, heading and rule in the HTML |

## What it found

- **L1 alone was not enough.** On the Phase 1 parser L1 called 42 of 49 cases healthy. All three checks agreed on 24.
- **Content was disappearing.** 5 horizontal rules across 3 test cases, plus everything in a list item after its first line. The parser reported nothing for 13 of the 18 cases L1 passed and the other checks failed.
- **Node ids did not match Part 2.** 34/46 before, 46/46 after.
- **Fuzzing.** 2515 of 3000 seeded random documents fail on the Phase 1 parser, 0 on the fixed one. The generator builds from the constructs the model supports, so the first number says nothing about real documents.
- **The harness catches the bugs it should.** Three earlier bugs, re-created as parser variants: L1 catches 0/3, the oracle or typed check catches 3/3.

## Inputs from Part 2

`fixtures/article2/` holds two files copied unchanged from [mutation-planner-harness](https://github.com/santhoshnumberone/mutation-planner-harness). `tests/test_article2_inputs.py` checks three things: `examples/api_spec.md` is the document Part 2's reference was built from, this parser gives it the same node ids, and every node a gold edit targets exists here. Node ids in `api_spec.md`, Phase 1 parser against the fixed one:

| Document | Nodes | Phase 1 parser | Fixed parser |
|---|---|---|---|
| api_spec.md | 46 | gaps p4-p7; li7 before li5 | none |

## Reproduce

```
pip install -r requirements.txt
python -m pytest -q
python benchmarks/roundtrip_harness.py --selftest
python benchmarks/roundtrip_harness.py --parser benchmarks/baseline/MarkdownParser_phase1.py --failures
python benchmarks/fuzz.py
python benchmarks/raw_text_demo.py
```

`results/` holds the runs behind the tables above, from the machine named at the top of this page. `docs/tapes/` has the scripts for the recordings.

## Layout

| Path | What |
|---|---|
| `MarkdownParser.py` | the model, parser and renderer |
| `benchmarks/checks.py` | the four checks, id report, parity with Part 2 |
| `benchmarks/roundtrip_harness.py` | runs them over `examples/` |
| `benchmarks/ledger.json` | limitations, and why each byte changes |
| `benchmarks/fuzz.py` | seeded random documents |
| `benchmarks/raw_text_demo.py` | a plain replace against a model edit, on a Part 2 case |
| `benchmarks/baseline/` | the Phase 1 parser, unchanged, for the before numbers |
| `examples/` | Part 2's `api_spec.md` and the small constructs behind each case |
| `fixtures/article2/` | inputs from Part 2, with checksums |
| `tests/` | `python -m pytest -q` |

## Limitations

| Case | What happens |
|---|---|
| adjacent_lists_markers | Two adjacent lists that differ only in bullet marker are written with the same marker and read back as one list. |
| reference_link | Link reference definitions are not modeled. The parser reports the line, the renderer drops it, and the link stops resolving. |
| setext_heading_two_lines | A setext heading that spans two lines is written as a one-line heading with a space where the line break was. |
| lazy_line_looks_like_table | Lines that continue a quote lazily (no > marker) and look like a table come back as a table. The Phase 1 renderer left continuation lines unmarked and passed this case; marking every line is what lets ordinary two-line quotes round-trip byte for byte. |
| lazy_line_looks_like_table_in_item | The same for a list item: lazy lines that look like a table are indented on the way out and come back as a table. Indenting continuation lines is what lets ordinary two-line items round-trip byte for byte. |

The renderer is a pretty-printer: after an edit it rewrites the formatting of untouched nodes. Ids are stable within one parse, not across edits. Inline Markdown is kept as source text and not parsed. O and T use markdown-it's own HTML, so a bug inside markdown-it is invisible to them.

## License

MIT
