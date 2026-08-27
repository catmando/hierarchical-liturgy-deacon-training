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
    flush:   body paragraph, no indent
    lines:   keeps the line breaks — for a list of petitions
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
         "note": "note", "flush": "flush", "lines": "lines"}
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
    head, folio, blocks = "", "", []
    para = []

    def flush():
        if not para:
            return
        first = para[0]
        m = re.match(r"^(\w+):\s*(.*)$", first)
        kind = "body"
        if m and m.group(1).lower() in KINDS:
            kind = KINDS[m.group(1).lower()]
            para[0] = m.group(2)
        if kind == "lines":
            body = "<br>".join(inline(l) for l in para if l.strip())
        else:
            body = inline(" ".join(para))
        para.clear()
        if body:
            blocks.append((kind, body))

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


def furniture(head, folio, side):
    """One leaf's running head, rule and folio. It sits over the half rather
    than in the flow, so the text can run across both."""
    return (f'    <div class="leaf {side}">\n'
            f'      <div class="head">{html.escape(head)}</div>\n'
            f'      <div class="folio">{html.escape(folio)}</div>\n'
            f'    </div>')


def flow_html(blocks):
    out = ['  <div class="flow">']
    for kind, body in blocks:
        cls = "" if kind == "body" else f' class="{kind}"'
        out.append(f'    <p{cls}>{body}</p>')
    out.append("  </div>")
    return "\n".join(out)


def main():
    first = sys.argv[1] if len(sys.argv) > 1 else "136"
    path = os.path.join(HERE, "pages", f"{first}.txt")
    if not os.path.exists(path):
        sys.exit(f"ERROR: {path} not found")
    head, folio, blocks = read_page(path)
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
{flow_html(blocks)}
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


def check_fit(pdf):
    """Does it fit? Two columns of fixed height silently spill into a third
    when the text is too long, and a third column lands outside the spread —
    so measure the ink rather than trust the render."""
    try:
        from PIL import Image, ImageChops
    except ImportError:
        print("  (install Pillow to have the fit checked)")
        return
    import glob
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-png", "-r", "150", pdf,
                        os.path.join(tmp, "p")], check=True)
        im = Image.open(sorted(glob.glob(os.path.join(tmp, "p*.png")))[0])
    W, H = im.size
    ppi = W / 8.5
    ink = ImageChops.invert(im.convert("L")).point(lambda v: 255 if v > 25 else 0)
    b = ink.getbbox()
    # the spread, centred on the sheet
    sw, sh = 7.25 * ppi, 5.875 * ppi
    x0, y0 = (W - sw) / 2, (H - sh) / 2
    over_r = (b[2] - (x0 + sw)) / ppi
    over_b = (b[3] - (y0 + sh)) / ppi
    if over_r > 0.02 or over_b > 0.02:
        print(f"  ⚠ TOO LONG — the text spills past the spread by "
              f"{max(over_r,0):.2f}in to the right, {max(over_b,0):.2f}in below."
              f"\n    Cut some text, or it will not be on the sheet at all.")
    else:
        # how full are the columns?
        col = ink.crop((int(x0), int(y0), int(x0 + sw), int(y0 + sh)))
        cb = col.getbbox()
        used = (cb[3] - cb[1]) / ppi if cb else 0
        avail = 5.875 - 0.386 - 0.36
        print(f"  fits — the columns run {used:.2f}in of the {avail:.2f}in "
              f"available ({used/avail*100:.0f}% full)")


if __name__ == "__main__":
    main()
