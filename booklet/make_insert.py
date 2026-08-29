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
    halfblank:  half a line, where a whole one opens too big a gap
    rule:    a thin divider across the measure
    <<CAPS>> small caps inside a sentence
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
         "normal": "normal", "blank": "blank", "rule": "rule",
         "halfblank": "halfblank",
         # page 56's devices
         "speaker": "speaker",     # NAME: then what is said
         "dialogue": "dialogue",   # several speakers, text aligned
         "title": "title",         # a centred letterspaced heading
         "dropcap": "dropcap"}     # a large red initial
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
    # <<PRIEST>> — small caps inside a sentence, as the book sets a name or
    # office mid-rubric. Explicit rather than inferred from capitals: "O God"
    # and "Ps." are not small caps, and guessing would be wrong silently.
    t = re.sub(r"&lt;&lt;(.+?)&gt;&gt;", r'<span class="sc">\1</span>', t)
    return " ".join(t.split())


def read_page(path):
    """-> (head, folio, [(kind, html)])  from one page file."""
    head, folio, size, blocks = "", "", "", []
    para = []
    brk = [False]          # a `break:` seen, waiting for the next block
    leaves = [2]           # a spread by default; `leaves: 1` for one page
    scale = [1.0]          # 1 matches the book's type size exactly
    side = [0.40]          # the book's own left and right margin, in inches
    track = ["0"]          # letter spacing, for pulling up a widow
    trim = [0.386, 0.36]   # first body line, and the foot — the book's own
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
        if kind == "rule":
            para.clear()
            blocks.append(("rule", "&nbsp;"))
            return
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
        if kind == "speaker":
            # the name runs up to the first colon and is set in red small caps
            whole = inline(" ".join(para))
            nm, _, rest = whole.partition(":")
            body = (f'<span class="who">{nm}</span>' + rest) if rest else whole
        elif kind == "dialogue":
            out = []
            for l in para:
                if not l.strip():
                    continue
                nm, _, rest = inline(l).partition(":")
                out.append(f'<span class="who">{nm}</span>'
                           f'<span class="said">{rest.strip()}</span>'
                           if rest else f"<span>{nm}</span>")
            body = "".join(out)
        elif kind == "dropcap":
            # Split the RAW text, not the marked-up HTML: slicing the HTML cut
            # through a <span> and printed class="sc"> onto the page. The
            # initial, then the rest of that word and the next in small caps —
            # the book sets "IN PEACE" and "O LORD" and no further.
            raw = " ".join(para)
            words = raw.split(" ")
            initial = words[0][:1]
            opening = (words[0][1:] + (" " + words[1] if len(words) > 1 else ""))
            tail = " ".join(words[2:])
            body = (f'<span class="initial">{inline(initial)}</span>'
                    f'<span class="opening">{inline(opening)}</span> '
                    f'{inline(tail)}' if raw else "")
        elif kind == "lines":
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
        if re.match(r"^halfblank:\s*$", line.strip(), re.I):
            flush()
            blocks.append(("halfblank", "&nbsp;"))
            continue
        mb = re.match(r"^blank:\s*(\d*)\s*$", line.strip(), re.I)
        if mb:
            flush()
            n = int(mb.group(1)) if mb.group(1) else 1
            for _ in range(max(1, n)):
                blocks.append(("blank", "&nbsp;"))
            continue
        m = re.match(r"^(head|folio|size|leaves|scale|margins|tracking|trim):\s*(.*)$", line.strip(), re.I)
        if m and not para:
            k = m.group(1).lower()
            if k == "head":
                head = m.group(2).strip()
            elif k == "folio":
                folio = m.group(2).strip()
            elif k == "leaves":
                leaves[0] = int(m.group(2).strip() or 2)
            elif k == "scale":
                scale[0] = float(m.group(2).strip() or 1)
            elif k == "margins":
                side[0] = float(m.group(2).strip() or 0.40)
            elif k == "tracking":
                track[0] = m.group(2).strip() or "0"
            elif k == "trim":
                bits = m.group(2).split()
                if len(bits) == 2:
                    trim[0], trim[1] = float(bits[0]), float(bits[1])
            else:
                size = m.group(2).strip().lower()
            continue
        para.append(line.strip())
    flush()
    globals()['LEAVES'] = leaves[0]
    globals()['SCALE'] = scale[0]
    globals()['SIDE'] = side[0]
    globals()['TRACK'] = track[0]
    globals()['TRIM'] = tuple(trim)
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

    one = globals().get("LEAVES", 2) == 1
    if one:
        doc = f"""<!-- built by make_insert.py from pages/{first}.txt -->
<meta charset="utf-8"><html lang="en">
<link rel="stylesheet" href="insert.css">
<style>:root{{ --scale:{globals().get("SCALE", 1)}; --side:{globals().get("SIDE", 0.40)}in; --track:{globals().get("TRACK", "0")}; --text-top:{globals().get("TRIM",(0.386,0.36))[0]}in; --foot:{globals().get("TRIM",(0.386,0.36))[1]}in; --head-top:{max(0.06, globals().get("TRIM",(0.386,0.36))[0]-0.27):.3f}in; --rule-top:{max(0.10, globals().get("TRIM",(0.386,0.36))[0]-0.21):.3f}in; --folio-up:{max(0.10, globals().get("TRIM",(0.386,0.36))[1]-0.16):.3f}in; }}</style>
<div class="sheet">
  <div class="spread one">
{furniture(head, folio, "left")}
{flow_html(blocks, size)}
  </div>
  <div class="cut one"></div>
  <div class="caption">Cut on the dashed border &middot; glue the blank side
    over page {folio}</div>
</div>
"""
    else:
        doc = f"""<!-- built by make_insert.py from pages/{first}.txt -->
<meta charset="utf-8"><html lang="en">
<link rel="stylesheet" href="insert.css">
<style>:root{{ --scale:{globals().get("SCALE", 1)}; --side:{globals().get("SIDE", 0.40)}in; --track:{globals().get("TRACK", "0")}; --text-top:{globals().get("TRIM",(0.386,0.36))[0]}in; --foot:{globals().get("TRIM",(0.386,0.36))[1]}in; --head-top:{max(0.06, globals().get("TRIM",(0.386,0.36))[0]-0.27):.3f}in; --rule-top:{max(0.10, globals().get("TRIM",(0.386,0.36))[0]-0.21):.3f}in; --folio-up:{max(0.10, globals().get("TRIM",(0.386,0.36))[1]-0.16):.3f}in; }}</style>
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
    out_html = os.path.join(HERE, f"insert_{first}.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(doc)
    globals()["OUT_HTML"] = out_html
    print(f"  insert_{first}.html   "
          f"{'page ' + folio if one else 'pages ' + folio + ' and ' + second}, "
          f"{len(blocks)} paragraphs")

    pdf = os.path.join(HERE, f"insert_{first}.pdf")
    r = subprocess.run(["weasyprint", "--encoding", "utf-8", out_html, pdf],
                       capture_output=True, text=True, cwd=HERE)
    if r.returncode != 0:
        sys.exit("  weasyprint failed: " + (r.stderr or "").strip()[:300])
    print(f"  insert_{first}.pdf    {os.path.getsize(pdf)/1024:.0f} KB   "
          f"— print at 100%, do not fit to page")
    check_fit(pdf)


def ink_outside(pdf, leaves):
    """Anything printed beyond the leaf, described, or None."""
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return None
    import glob
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        subprocess.run(["pdftoppm", "-png", "-r", "150", pdf,
                        os.path.join(t, "o")], check=True)
        im = Image.open(sorted(glob.glob(os.path.join(t, "o*.png")))[0]).convert("L")
    W, H = im.size
    ppi = W / 8.5
    side = globals().get("SIDE", 0.40)
    leaf_w = 3.625 * leaves
    x_right = (8.5 + leaf_w) / 2 * ppi
    ink = ImageChops.invert(im).point(lambda v: 255 if v > 60 else 0)
    px = ink.load()
    n = sum(1 for x in range(int(x_right) + 6, W)
            for y in range(0, H, 2) if px[x, y])
    if n > 40:
        return f"about {n} marks of text"
    return None


def measure_height():
    """The height the text occupies, in inches, set in one tall column of the
    book's measure — which is the only place it can be measured honestly, since
    on the sheet the overflow runs off the edge."""
    import glob
    import tempfile
    css = open(os.path.join(HERE, "insert.css"), encoding="utf-8").read()
    doc = open(globals().get("OUT_HTML",
                                 os.path.join(HERE, "insert.html")),
               encoding="utf-8").read()
    m = re.search(r'<div class="flow[^"]*">(.*?)\n  </div>', doc, re.S)
    if not m:
        return None
    cls = re.search(r'<div class="(flow[^"]*)"', doc).group(1)
    probe = ('<meta charset="utf-8"><html lang="en"><style>' + css +
             f"\n:root{{ --scale:{globals().get('SCALE', 1)};"
             f" --side:{globals().get('SIDE', 0.40)}in;"
             f" --track:{globals().get('TRACK', '0')};"
             f" --text-top:{globals().get('TRIM',(0.386,0.36))[0]}in;"
             f" --foot:{globals().get('TRIM',(0.386,0.36))[1]}in }}"
             "\n@page{ size:3.2in 200in; margin:0 }\n</style>"
             f'<div class="{cls}" style="column-count:1;height:auto;'
             f'padding:0;margin:0;'
             f'width:{(3.625 - 2*globals().get("SIDE", 0.40))*72:.1f}pt">'
             + m.group(1) + "</div>")
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
    t = globals().get('TRIM', (0.386, 0.36))
    col = 5.875 - t[0] - t[1]
    leaves = globals().get("LEAVES", 2)
    # First, the ground truth: is there ink outside the leaf? Text that will
    # not fit spills into a further column beyond the sheet's trim and is
    # simply lost — silently, which is the whole reason for checking. The
    # height sum below can say "fits" while this is happening, because a
    # floated drop cap takes room the sum does not know about.
    spilled = ink_outside(pdf, leaves)
    if spilled:
        print(f"  ⚠ TOO LONG — {spilled} is running off the sheet and will "
              f"not print. Lower `scale:` or cut a line.")
        return
    runs = measure_height()
    if runs is None:
        print("  (could not measure the fit)")
        return
    lines = runs * 72 / 14.2
    per = col * 72 / 14.2
    if runs > col * leaves:
        print(f"  ⚠ TOO LONG — the text runs {runs:.2f}in and "
              f"{'one page holds' if leaves == 1 else 'two pages hold'} "
              f"{col*leaves:.2f}in: about {lines - leaves*per:.0f} lines too "
              f"many.")
    else:
        spare = (col * leaves - runs) * 72 / 14.2
        print(f"  fits — {runs:.2f}in of the {col*leaves:.2f}in available "
              f"({runs/(col*leaves)*100:.0f}% full, about {spare:.0f} lines "
              f"spare).")


if __name__ == "__main__":
    main()
