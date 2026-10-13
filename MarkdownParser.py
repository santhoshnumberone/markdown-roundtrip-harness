from __future__ import annotations
import hashlib
import re
from dataclasses import dataclass, field

from markdown_it import MarkdownIt


def _atx_text(text: str) -> str:
    """Heading text for a one-line ATX heading. A trailing # run is escaped, or the
    heading would read it as a closing sequence."""
    return re.sub(r"(^|\s)(#+)\s*$", r"\1\\\2", text.replace("\n", " "))


@dataclass
class Node:
    id: str
    kind: str                       # heading | paragraph | blockquote | list | list_item
                                     # | code_block | table | thematic_break | html_block
    level: int | None = None
    text: str = ""
    children: list["Node"] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


@dataclass
class Document:
    nodes: list[Node]
    source_hash: str


class MarkdownParser:
    """Walks markdown-it's token stream into our Node tree."""

    def __init__(self):
        # "gfm-like" enables GFM tables, strikethrough, etc. on top of CommonMark.
        # Plain "commonmark" does NOT parse tables — they fall through as raw
        # paragraph text, which is what caused the table to vanish entirely
        # in the api_spec.md test rather than just rendering wrong.
        self.md = MarkdownIt("gfm-like")
        self._counters: dict[str, int] = {}
        self.diagnostics: list[str] = []

    def parse(self, text: str) -> Document:
        self._counters = {}
        self.diagnostics = []
        tokens = self.md.parse(text)
        nodes = self._walk(tokens)
        self._report_uncovered_lines(text, tokens)
        return Document(nodes=nodes, source_hash=hashlib.sha256(text.encode()).hexdigest())

    def _report_uncovered_lines(self, text: str, tokens) -> None:
        """markdown-it consumes link reference definitions without emitting a token.
        A source line that no token covers is reported here instead of vanishing."""
        covered = {n for t in tokens if t.map for n in range(*t.map)}
        for n, line in enumerate(re.split(r"\r\n?|\n", text)):
            if line.strip() and n not in covered:
                self.diagnostics.append(f"line {n + 1} is not part of any block: {line[:60]!r}")

    def _next_id(self, kind: str) -> str:
        prefix = {"heading": "h", "paragraph": "p", "blockquote": "bq",
                  "list": "lst", "list_item": "li", "code_block": "cb",
                  "table": "tbl", "thematic_break": "hr", "html_block": "html"}[kind]
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"{prefix}{self._counters[prefix]}"

    def _walk(self, tokens) -> list[Node]:
        nodes: list[Node] = []
        i = 0
        while i < len(tokens):
            t = tokens[i]

            if t.type == "heading_open":
                level = int(t.tag[1])
                text = tokens[i + 1].content
                if t.markup in ("=", "-"):  # setext: may span lines and end in a literal #
                    text = _atx_text(text)
                nodes.append(Node(id=self._next_id("heading"), kind="heading",
                                   level=level, text=text))
                i += 3  # heading_open, inline, heading_close

            elif t.type == "paragraph_open":
                inline = tokens[i + 1]
                nodes.append(Node(id=self._next_id("paragraph"), kind="paragraph",
                                   text=inline.content))
                i += 3

            elif t.type == "blockquote_open":
                close_idx = self._find_matching_close(tokens, i, "blockquote_open", "blockquote_close")
                inner = tokens[i + 1:close_idx]
                node = Node(id=self._next_id("blockquote"), kind="blockquote")
                # A quote wrapping exactly one paragraph is kept as plain text, anything
                # richer keeps its children. Decided from the tokens, before any child is
                # numbered, so ids follow document order and none are spent on nodes we drop.
                if len(inner) == 3 and inner[0].type == "paragraph_open":
                    node.text = inner[1].content
                else:
                    node.children = self._walk(inner)
                nodes.append(node)
                i = close_idx + 1

            elif t.type in ("fence", "code_block"):
                nodes.append(Node(id=self._next_id("code_block"), kind="code_block",
                                   text=t.content, meta={"language": t.info.strip() if t.info else ""}))
                i += 1

            elif t.type in ("bullet_list_open", "ordered_list_open"):
                close_type = t.type.replace("_open", "_close")
                close_idx = self._find_matching_close(tokens, i, t.type, close_type)
                inner = tokens[i + 1:close_idx]
                ordered = t.type == "ordered_list_open"
                # markdown-it hides the paragraphs of a tight list. One visible paragraph
                # directly under an item makes the whole list loose.
                tight = all(x.hidden for x in inner
                            if x.type == "paragraph_open" and x.level == t.level + 2)
                meta = {"ordered": ordered, "tight": tight}
                if ordered:
                    start = t.attrGet("start")
                    meta["start"] = 1 if start is None else int(start)
                list_node = Node(id=self._next_id("list"), kind="list", meta=meta)
                list_node.children = self._walk_list_items(inner)
                nodes.append(list_node)
                i = close_idx + 1

            elif t.type == "table_open":
                close_idx = self._find_matching_close(tokens, i, "table_open", "table_close")
                rows, align = self._walk_table(tokens[i + 1:close_idx])
                nodes.append(Node(id=self._next_id("table"), kind="table",
                                   meta={"rows": rows, "align": align}))
                i = close_idx + 1

            elif t.type == "hr":
                # markdown-it-py's hr markup is not reliable beyond its first character
                nodes.append(Node(id=self._next_id("thematic_break"), kind="thematic_break",
                                   meta={"marker": (t.markup or "-")[0]}))
                i += 1

            elif t.type == "html_block":
                nodes.append(Node(id=self._next_id("html_block"), kind="html_block", text=t.content))
                i += 1

            else:
                # anything else is skipped, but recorded
                line_no = t.map[0] + 1 if t.map else None
                self.diagnostics.append(f"skipped {t.type} at line {line_no}")
                i += 1

        return nodes

    def _find_matching_close(self, tokens, open_idx, open_type, close_type) -> int:
        """Returns the index of the close token matching tokens[open_idx], handling nesting."""
        depth = 1
        j = open_idx + 1
        while depth > 0:
            if tokens[j].type == open_type:
                depth += 1
            elif tokens[j].type == close_type:
                depth -= 1
            j += 1
        return j - 1

    def _walk_list_items(self, tokens) -> list[Node]:
        """Walks the tokens *inside* a list_open/list_close pair into list_item Nodes.

        An item's first paragraph is its text. Every block after it (sub-lists, more
        paragraphs, code blocks, quotes, tables) becomes a child, so nothing is dropped.
        The item is numbered before its children, which keeps ids in document order.
        """
        items = []
        i = 0
        while i < len(tokens):
            if tokens[i].type == "list_item_open":
                close_idx = self._find_matching_close(tokens, i, "list_item_open", "list_item_close")
                inner = tokens[i + 1:close_idx]
                item = Node(id=self._next_id("list_item"), kind="list_item")
                if inner and inner[0].type == "paragraph_open":
                    item.text = inner[1].content
                    inner = inner[3:]
                item.children = self._walk(inner)
                items.append(item)
                i = close_idx + 1
            else:
                i += 1
        return items

    def _walk_table(self, tokens) -> tuple[list[list[str]], list[str]]:
        """Returns (rows, align). rows[0] is the header. align holds 'left', 'center',
        'right' or '' for each column."""
        rows: list[list[str]] = []
        align: list[str] = []
        current_row: list[str] = []
        i = 0
        while i < len(tokens):
            t = tokens[i]
            if t.type == "tr_open":
                current_row = []
            elif t.type in ("th_open", "td_open"):
                if t.type == "th_open":
                    align.append((t.attrGet("style") or "").removeprefix("text-align:"))
                # next token is inline content for this cell
                current_row.append(tokens[i + 1].content)
            elif t.type == "tr_close":
                rows.append(current_row)
            i += 1
        return rows, align


class MarkdownRenderer:
    """Renders a Document back to Markdown text."""

    def render(self, doc: "Document") -> str:
        return "\n\n".join(self._render_node(n) for n in doc.nodes) + "\n"

    def _render_node(self, n: "Node") -> str:
        if n.kind == "heading":
            return f"{'#' * n.level} {_atx_text(n.text)}"

        elif n.kind == "paragraph":
            return n.text

        elif n.kind == "blockquote":
            inner = "\n\n".join(self._render_node(c) for c in n.children) if n.children else n.text
            return "\n".join(f"> {line}" if line else ">" for line in inner.split("\n"))

        elif n.kind == "code_block":
            lang = n.meta.get("language", "")
            text = n.text if not n.text or n.text.endswith("\n") else n.text + "\n"
            # the fence has to be longer than any backtick run inside the code
            fence = "`" * max(3, 1 + max((len(m) for m in re.findall(r"`+", text)), default=0))
            return f"{fence}{lang}\n{text}{fence}"

        elif n.kind == "list":
            ordered = n.meta.get("ordered", False)
            start = n.meta.get("start", 1)
            gap = "\n" if n.meta.get("tight", True) else "\n\n"
            items = []
            for k, item in enumerate(n.children):
                marker = f"{start + k}. " if ordered else "- "
                blocks = ([item.text] if item.text else []) + [self._render_node(c) for c in item.children]
                first, *rest = gap.join(blocks).split("\n")
                # continuation lines are indented to the item's content column
                head = marker + first if first else marker.rstrip()
                items.append("\n".join([head] + [" " * len(marker) + ln if ln else ln for ln in rest]))
            return gap.join(items)

        elif n.kind == "table":
            rows = n.meta.get("rows", [])
            if not rows:
                return ""
            header, *body = rows
            align = n.meta.get("align", [])
            rule = {"left": ":---", "right": "---:", "center": ":---:"}
            sep = [rule.get(align[c] if c < len(align) else "", "---") for c in range(len(header))]
            lines = [self._table_row(header), self._table_row(sep)]
            lines += [self._table_row(r) for r in body]
            return "\n".join(lines)

        elif n.kind == "thematic_break":
            return n.meta.get("marker", "-") * 3

        elif n.kind == "html_block":
            return n.text.rstrip("\n")

        else:
            return n.text

    @staticmethod
    def _table_row(cells: list[str]) -> str:
        # cell text is stored unescaped: markdown-it removes the backslash from \|
        return "| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |"
