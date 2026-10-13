from dataclasses import dataclass, field
from markdown_it import MarkdownIt


@dataclass
class Node:
    id: str
    kind: str                       # heading | paragraph | blockquote | list | list_item
                                     # | code_block | table
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
        import hashlib
        self._counters = {}
        self.diagnostics = []
        tokens = self.md.parse(text)
        nodes = self._walk(tokens)
        return Document(nodes=nodes, source_hash=hashlib.sha256(text.encode()).hexdigest())

    def _next_id(self, kind: str) -> str:
        prefix = {"heading": "h", "paragraph": "p", "blockquote": "bq",
                  "list": "list", "list_item": "li", "code_block": "cb",
                  "table": "tbl"}[kind]
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"{prefix}{self._counters[prefix]}"

    def _walk(self, tokens) -> list[Node]:
        nodes: list[Node] = []
        i = 0
        while i < len(tokens):
            t = tokens[i]

            if t.type == "heading_open":
                level = int(t.tag[1])
                inline = tokens[i + 1]
                nodes.append(Node(id=self._next_id("heading"), kind="heading",
                                   level=level, text=inline.content))
                i += 3  # heading_open, inline, heading_close

            elif t.type == "paragraph_open":
                inline = tokens[i + 1]
                nodes.append(Node(id=self._next_id("paragraph"), kind="paragraph",
                                   text=inline.content))
                i += 3

            elif t.type == "blockquote_open":
                close_idx = self._find_matching_close(tokens, i, "blockquote_open", "blockquote_close")
                inner = self._walk(tokens[i + 1:close_idx])
                # v1: a blockquote usually wraps a single paragraph; flatten that
                # common case to plain text, but keep full children for the
                # (rarer) multi-block blockquote so nothing is silently dropped.
                if len(inner) == 1 and inner[0].kind == "paragraph":
                    nodes.append(Node(id=self._next_id("blockquote"), kind="blockquote",
                                       text=inner[0].text))
                else:
                    nodes.append(Node(id=self._next_id("blockquote"), kind="blockquote",
                                       children=inner))
                i = close_idx + 1

            elif t.type in ("fence", "code_block"):
                nodes.append(Node(id=self._next_id("code_block"), kind="code_block",
                                   text=t.content, meta={"language": t.info.strip() if t.info else ""}))
                i += 1

            elif t.type in ("bullet_list_open", "ordered_list_open"):
                close_type = t.type.replace("_open", "_close")
                close_idx = self._find_matching_close(tokens, i, t.type, close_type)
                list_node = Node(id=self._next_id("list"), kind="list",
                                  meta={"ordered": t.type == "ordered_list_open"})
                list_node.children = self._walk_list_items(tokens[i + 1:close_idx])
                nodes.append(list_node)
                i = close_idx + 1

            elif t.type == "table_open":
                close_idx = self._find_matching_close(tokens, i, "table_open", "table_close")
                rows = self._walk_table(tokens[i + 1:close_idx])
                nodes.append(Node(id=self._next_id("table"), kind="table", meta={"rows": rows}))
                i = close_idx + 1

            else:
                # not modelled yet (e.g. hr, html_block): skipped, but now recorded
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

        Each list_item can contain a leading paragraph (the item's own text)
        AND a nested sub-list. The previous version only looked at the first
        paragraph and silently dropped everything else in the item -- this is
        the fix for that silent data-loss bug.
        """
        items = []
        i = 0
        while i < len(tokens):
            if tokens[i].type == "list_item_open":
                close_idx = self._find_matching_close(tokens, i, "list_item_open", "list_item_close")
                inner = self._walk(tokens[i + 1:close_idx])

                text = ""
                nested = []
                for n in inner:
                    if n.kind == "paragraph" and not text:
                        text = n.text          # the item's own line
                    elif n.kind == "list":
                        nested.append(n)        # a sub-list nested inside this item
                    # any other kind found here (rare) is intentionally still
                    # discarded in v1 -- only paragraph + nested list are common
                    # enough in real docs to handle now.

                item = Node(id=self._next_id("list_item"), kind="list_item",
                            text=text, children=nested)
                items.append(item)
                i = close_idx + 1
            else:
                i += 1
        return items

    def _walk_table(self, tokens) -> list[list[str]]:
        """Returns rows as list[list[str]], header row included as rows[0]."""
        rows: list[list[str]] = []
        current_row: list[str] = []
        i = 0
        while i < len(tokens):
            t = tokens[i]
            if t.type == "tr_open":
                current_row = []
            elif t.type in ("th_open", "td_open"):
                # next token is inline content for this cell
                current_row.append(tokens[i + 1].content)
            elif t.type == "tr_close":
                rows.append(current_row)
            i += 1
        return rows


class MarkdownRenderer:
    """Renders a Document back to Markdown text."""

    def render(self, doc: "Document") -> str:
        return "\n\n".join(self._render_node(n) for n in doc.nodes) + "\n"

    def _render_node(self, n: "Node") -> str:
        if n.kind == "heading":
            return f"{'#' * n.level} {n.text}"

        elif n.kind == "paragraph":
            return n.text

        elif n.kind == "blockquote":
            if n.children:
                inner = "\n\n".join(self._render_node(c) for c in n.children)
                return "\n".join(f"> {line}" for line in inner.split("\n"))
            return f"> {n.text}"

        elif n.kind == "code_block":
            lang = n.meta.get("language", "")
            return f"```{lang}\n{n.text}```"

        elif n.kind == "list":
            marker = self._list_marker(n.meta.get("ordered", False))
            lines = []
            for i, item in enumerate(n.children, start=1):
                lines.append(f"{marker(i)}{item.text}")
                for sub in item.children:
                    sub_text = self._render_node(sub)
                    lines.append("\n".join(f"   {line}" for line in sub_text.split("\n")))
            return "\n".join(lines)

        elif n.kind == "table":
            rows = n.meta.get("rows", [])
            if not rows:
                return ""
            header, *body = rows
            sep = ["---"] * len(header)
            lines = [self._table_row(header), self._table_row(sep)]
            lines += [self._table_row(r) for r in body]
            return "\n".join(lines)

        else:
            return n.text

    @staticmethod
    def _table_row(cells: list[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    @staticmethod
    def _list_marker(ordered: bool):
        return (lambda i: f"{i}. ") if ordered else (lambda i: "- ")


if __name__ == "__main__":
    with open("examples/api_spec.md") as f:
        sample = f.read()

    doc = MarkdownParser().parse(sample)

    print("=== PARSED NODES ===")
    for n in doc.nodes:
        extra = n.meta if n.meta else ""
        print(n.kind, n.id, repr(n.text[:60]), extra, f"children={len(n.children)}" if n.children else "")

    print("\n=== RENDERED ===")
    rendered = MarkdownRenderer().render(doc)
    print(rendered)

    print("\n=== ROUND-TRIP MATCH ===")
    print(rendered.strip() == sample.strip())


