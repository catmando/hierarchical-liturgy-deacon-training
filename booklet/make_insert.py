#!/usr/bin/env python3
"""
make_insert.py — build the replacement spread from pages/*.txt

    python3 make_insert.py               # pages/136.txt + pages/137.txt
    python3 make_insert.py 140 141       # a different pair

Writes insert.html and, if weasyprint is about, insert.pdf: a US Letter sheet
carrying the two pages side by side at the book's own size. Print it at 100%,
cut the dashed border, fold the centre line, glue the blank back over the
existing pages.

THE MARKUP, in full. A line starting with # is a comment; blank lines separate
paragraphs; a paragraph may be wrapped over as many lines as you like.

    head:    the running head          folio:  the page number
    rubric:  whole paragraph in red    label:  centred red italic
    small:   the choir's smaller type  note:   a footnote
    flush:   body paragraph, no indent
    (no prefix)  an ordinary body paragraph, first line indented

    {red}   *italic*   **bold**   {*red italic*}   [1] superior figure

Everything about the size, spacing and colour lives in insert.css, and every
number in it was measured off a scan of the real page — see SPEC.md.
"""
import html
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KINDS = {"rubric": "rubric", "label": "label", "small": "small",
         "note": "note", "flush": "flush"}


def inline(t):
    """{red}, *italic*, **bold**, [1] — in that order, so a {*red italic*}
    comes out as one red span with an italic inside it."""
    t = html.escape(t)
    t = re.sub(r"\{(.+?)\}", r'<span class="red">\1</span>', t, flags=re.S)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t, flags=re.S)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>",
               t, flags=re.S)
    t = re.sub(r"\[(\d+)\]", r"<sup>\1</sup>", t)
    return " ".join(t.split())


def read_page(path):
    """-> (head, folio, [(kind, html)])  from one page file."""
    head, folio, blocks = "", "", []
    para = []

    def flush():
        if not para:
            return
        text = " ".join(para).strip()
        para.clear()
        if not text:
            return
        m = re.match(r"^(\w+):\s*(.*)$", text, flags=re.S)
        kind = "body"
        if m and m.group(1).lower() in KINDS:
            kind = KINDS[m.group(1).lower()]
            text = m.group(2)
        blocks.append((kind, inline(text)))

    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if line.lstrip().startswith("#"):
            continue
        if not line.strip():
            flush()
            continue
        m = re.match(r"^(head|folio):\s*(.*)$", line.strip(), re.I)
        if m and not para:
            if m.group(1).lower() == "head":
                head = m.group(2).strip()
            else:
                folio = m.group(2).strip()
            continue
        para.append(line.strip())
    flush()
    return head, folio, blocks


def leaf_html(path):
    head, folio, blocks = read_page(path)
    out = ['    <div class="leaf">',
           f'      <div class="head">{html.escape(head)}</div>',
           '      <div class="body">']
    for kind, body in blocks:
        cls = "" if kind == "body" else f' class="{kind}"'
        out.append(f"        <p{cls}>{body}</p>")
    out += ['      </div>',
            f'      <div class="folio">{html.escape(folio)}</div>',
            '    </div>']
    return "\n".join(out)


def main():
    a, b = (sys.argv[1:3] + ["136", "137"])[:2] if len(sys.argv) > 2 \
        else ("136", "137")
    paths = [os.path.join(HERE, "pages", f"{n}.txt") for n in (a, b)]
    for p in paths:
        if not os.path.exists(p):
            sys.exit(f"ERROR: {p} not found")

    doc = f"""<!-- built by make_insert.py from pages/{a}.txt and {b}.txt -->
<meta charset="utf-8"><html lang="en">
<link rel="stylesheet" href="insert.css">
<div class="sheet">
  <div class="spread">
{leaf_html(paths[0])}
{leaf_html(paths[1])}
  </div>
  <div class="cut"></div>
  <div class="caption">Cut on the dashed border &middot; fold on the centre
    line &middot; glue the blank side over pages {a}&ndash;{b}</div>
</div>
"""
    out_html = os.path.join(HERE, "insert.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"  insert.html   pages {a} and {b}")

    pdf = os.path.join(HERE, "insert.pdf")
    r = subprocess.run(["weasyprint", "--encoding", "utf-8", out_html, pdf],
                       capture_output=True, text=True, cwd=HERE)
    if r.returncode == 0:
        print(f"  insert.pdf    {os.path.getsize(pdf)/1024:.0f} KB   "
              f"— print at 100%, do not fit to page")
    else:
        print("  weasyprint failed:", (r.stderr or "").strip()[:200])


if __name__ == "__main__":
    main()
