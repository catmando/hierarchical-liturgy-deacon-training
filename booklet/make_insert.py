#!/usr/bin/env python3
"""
make_insert.py — build the replacement spread from pages/*.txt

    python3 make_insert.py               # pages/136.txt
    python3 make_insert.py 140           # a different spread

Writes insert.html and, if weasyprint is about, insert.pdf: a US Letter sheet
carrying the two pages side by side at the book's own size. ONE file holds the
whole spread; the text flows across both leaves and is balanced between them,
so the break falls where it falls and an edit redistributes itself. Print it at 100%,
cut the dashed border, fold the centre line, glue the blank back over the
existing pages.

THE MARKUP, in full. A line starting with # is a comment; blank lines separate
paragraphs; a paragraph may be wrapped over as many lines as you like.

    head:    the running head          folio:  the page number
    rubric:  whole paragraph in red    label:  centred red italic
    small:   the choir's smaller type  note:   a footnote
    normal:  body size, when the spread's default is small
    size: small  in the header, to set the whole spread in the smaller type
    flush:   body paragraph, no indent
    lines:   keeps the line breaks — for a list of petitions
    blank:   one empty line;  `blank: 2`  for two
    break:   force what follows onto the second page
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
         "note": "note", "flush": "flush", "lines": "lines",
         "normal": "normal", "blank": "blank"}
# `lines:` keeps the line breaks as written — a list of petitions is a list,
# and joining it into a paragraph runs two of them together. Everywhere else a
# newline is only where the line was wrapped in the editor.


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
    head, folio, size, blocks = "", "", "", []
    para = []
    brk = [False]          # a `break:` seen, waiting for the next block
    warn = []              # markers that look mistyped

    def flush():
        if not para:
            return
        first = para[0]
        m = re.match(r"^(\w+):\s*(.*)$", first)
        kind = "body"
        if m and m.group(1).lower() in KINDS:
            kind = KINDS[m.group(1).lower()]
            para[0] = m.group(2)
        nonlocal_break = brk[0]
        brk[0] = False
        if kind == "blank":
            # `blank:` on its own is one empty line; `blank: 2` is two. A
            # non-breaking space gives the line its height, so it takes the
            # leading of whatever size is in force around it.
            try:
                n = max(1, int((para[0] or "1").strip() or 1))
            except ValueError:
                n = 1
            para.clear()
            for i in range(n):
                blocks.append(("blank" + (" brk" if nonlocal_break and not i
                                          else ""), "&nbsp;"))
            return
        if kind == "lines":
            body = "<br>".join(inline(l) for l in para if l.strip())
        else:
            body = inline(" ".join(para))
        para.clear()
        if body:
            cls = "" if kind == "body" else kind
            if nonlocal_break:
                cls = (cls + " brk").strip()
            blocks.append((cls, body))

    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if line.lstrip().startswith("#"):
            continue
        if not line.strip():
            flush()
            continue
        # `blank:` is a break wherever it appears, not only at the head of a
        # paragraph. Requiring an empty line before it made it print as
        # literal text in the middle of a sentence, which is not a mistake
        # anyone would expect to make.
        # `break:` forces what follows onto the second page
        if re.match(r"^break:\s*$", line.strip(), re.I):
            flush()
            brk[0] = True
            continue
        # A marker with the colon on the wrong side, or misspelled, would
        # otherwise print as literal text in the middle of the page — which is
        # exactly what `:blank` did. Say so instead.
        mw = re.match(r"^:?(\w+):?\s*\d*\s*$", line.strip())
        if mw and mw.group(1).lower() in set(KINDS) | {"head", "folio",
                                                       "size", "break"}:
            if not re.match(r"^(\w+):", line.strip()):
                warn.append(line.strip())
        mb = re.match(r"^blank:\s*(\d*)\s*$", line.strip(), re.I)
        if mb:
            flush()
            n = int(mb.group(1)) if mb.group(1) else 1
            for _ in range(max(1, n)):
                blocks.append(("blank", "&nbsp;"))
            continue
        m = re.match(r"^(head|folio|size):\s*(.*)$", line.strip(), re.I)
        if m and not para:
            k = m.group(1).lower()
            if k == "head":
                head = m.group(2).strip()
            elif k == "folio":
                folio = m.group(2).strip()
            else:
                size = m.group(2).strip().lower()
            continue
        para.append(line.strip())
    flush()
    for w in warn:
        print(f"  ⚠ {w!r} looks like a mistyped marker — the colon goes "
              f"after the word, as in `blank:`. It will print as text.")
    return head, folio, size, blocks


def furniture(head, folio, side):
    """One leaf's running head, rule and folio. It sits over the half rather
    than in the flow, so the text can run across both."""
    return (f'    <div class="leaf {side}">\n'
            f'      <div class="head">{html.escape(head)}</div>\n'
            f'      <div class="folio">{html.escape(folio)}</div>\n'
            f'    </div>')


def flow_html(blocks, size=""):
    cls = "flow small-body" if size == "small" else "flow"
    out = [f'  <div class="{cls}">']
    for kind, body in blocks:
        cls = f' class="{kind}"' if kind else ""
        out.append(f'    <p{cls}>{body}</p>')
    out.append("  </div>")
    return "\n".join(out)


def main():
    first = sys.argv[1] if len(sys.argv) > 1 else "136"
    path = os.path.join(HERE, "pages", f"{first}.txt")
    if not os.path.exists(path):
        sys.exit(f"ERROR: {path} not found")
    head, folio, size, blocks = read_page(path)
    folio = folio or first
    try:
        second = str(int(folio) + 1)
    except ValueError:
        second = ""

    doc = f"""<!-- built by make_insert.py from pages/{first}.txt -->
<meta charset="utf-8"><html lang="en">
<link rel="stylesheet" href="insert.css">
<div class="sheet">
  <div class="spread">
{furniture(head, folio, "left")}
{furniture(head, second, "right")}
{flow_html(blocks, size)}
  </div>
  <div class="cut"></div>
  <div class="caption">Cut on the dashed border &middot; fold on the centre
    line &middot; glue the blank side over pages {folio}&ndash;{second}</div>
</div>
"""
    out_html = os.path.join(HERE, "insert.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"  insert.html   pages {folio} and {second}, "
          f"{len(blocks)} paragraphs")

    pdf = os.path.join(HERE, "insert.pdf")
    r = subprocess.run(["weasyprint", "--encoding", "utf-8", out_html, pdf],
                       capture_output=True, text=True, cwd=HERE)
    if r.returncode != 0:
        sys.exit("  weasyprint failed: " + (r.stderr or "").strip()[:300])
    print(f"  insert.pdf    {os.path.getsize(pdf)/1024:.0f} KB   "
          f"— print at 100%, do not fit to page")
    check_fit(pdf)


def measure_height():
    """The height the text occupies, in inches, set in one tall column of the
    book's measure — which is the only place it can be measured honestly, since
    on the sheet the overflow runs off the edge."""
    import glob
    import tempfile
    css = open(os.path.join(HERE, "insert.css"), encoding="utf-8").read()
    doc = open(os.path.join(HERE, "insert.html"), encoding="utf-8").read()
    m = re.search(r'<div class="flow[^"]*">(.*?)\n  </div>', doc, re.S)
    if not m:
        return None
    cls = re.search(r'<div class="(flow[^"]*)"', doc).group(1)
    probe = ('<meta charset="utf-8"><html lang="en"><style>' + css +
             "\n@page{ size:3.2in 200in; margin:0 }\n</style>"
             f'<div class="{cls}" style="column-count:1;height:auto;'
             'padding:0;margin:0;width:203.5pt">' + m.group(1) + "</div>")
    with tempfile.TemporaryDirectory() as tmp:
        ph = os.path.join(tmp, "probe.html")
        pp = os.path.join(tmp, "probe.pdf")
        with open(ph, "w", encoding="utf-8") as f:
            f.write(probe)
        # the fonts are referenced relatively, so render from here
        open(os.path.join(HERE, "_probe.html"), "w", encoding="utf-8").write(probe)
        subprocess.run(["weasyprint", "--encoding", "utf-8",
                        os.path.join(HERE, "_probe.html"), pp],
                       capture_output=True, cwd=HERE)
        os.remove(os.path.join(HERE, "_probe.html"))
        subprocess.run(["pdftoppm", "-png", "-r", "100", pp,
                        os.path.join(tmp, "q")], check=True)
        from PIL import Image, ImageChops
        total = 0
        for f in sorted(glob.glob(os.path.join(tmp, "q-*.png"))):
            im = Image.open(f).convert("L")
            b = ImageChops.invert(im).point(lambda v: 255 if v > 25 else 0).getbbox()
            if b:
                total += b[3] - b[1]
    return total / 100.0


def check_fit(pdf):
    """Does it fit?

    Not by measuring ink on the sheet: the cut border, the fold ticks and the
    caption all sit outside the spread by design, so that reads as overflow
    every time — it did, and reported 1.80in of spill when the text fitted
    with room over. The honest test is to set the same text in one tall column
    of the book's measure and compare its height with what two columns hold.
    """
    col = 5.875 - 0.386 - 0.36
    runs = measure_height()
    if runs is None:
        print("  (could not measure the fit)")
        return
    lines = runs * 72 / 14.2
    per = col * 72 / 14.2
    if runs > col * 2:
        print(f"  ⚠ TOO LONG — the text runs {runs:.2f}in and two pages hold "
              f"{col*2:.2f}in: about {lines - 2*per:.0f} lines too many.")
    else:
        spare = (col * 2 - runs) * 72 / 14.2
        print(f"  fits — {runs:.2f}in of the {col*2:.2f}in available "
              f"({runs/(col*2)*100:.0f}% full, about {spare:.0f} lines spare).")


if __name__ == "__main__":
    main()
