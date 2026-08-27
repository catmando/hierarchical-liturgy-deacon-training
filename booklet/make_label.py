#!/usr/bin/env python3
"""
make_label.py — a sheet of glue-on labels from labels/*.txt

    python3 make_label.py is_polla          # -> label_is_polla.pdf

A label is a small piece to paste into the service book: a greeting, a
pronunciation, anything that is easier kept in the book than in the head. One
to a sheet, centred, with the dashed cut line used everywhere else here.

The markup is the pages' markup — see make_insert.py — plus a `size:` header
giving the finished label in inches:

    size: 1.625 x 1.25

Paragraph kinds used here: none (the words themselves), `label:` for the red
italic cue, and `lines:` where the line breaks matter.
"""
import html
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from make_insert import inline, KINDS               # one markup, not two

SHEET_W, SHEET_H = 8.5, 11.0
MARGIN = 0.5          # the least paper a printer will leave alone


def read_label(path):
    """-> (w, h, [(kind, html)])"""
    size, blocks, para = (1.625, 1.25), [], []

    def flush():
        if not para:
            return
        first = para[0]
        m = re.match(r"^(\w+):\s*(.*)$", first)
        kind = "say"
        if m and m.group(1).lower() in KINDS:
            kind = KINDS[m.group(1).lower()]
            para[0] = m.group(2)
        body = ("<br>".join(inline(l) for l in para if l.strip())
                if kind == "lines" else inline(" ".join(para)))
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
        m = re.match(r"^size:\s*([\d.]+)\s*x\s*([\d.]+)\s*$", line.strip(), re.I)
        if m and not para:
            size = (float(m.group(1)), float(m.group(2)))
            continue
        para.append(line.strip())
    flush()
    return size[0], size[1], blocks


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "is_polla"
    path = os.path.join(HERE, "labels", f"{name}.txt")
    if not os.path.exists(path):
        sys.exit(f"ERROR: {path} not found")
    w, h, blocks = read_label(path)
    body = "\n".join(f'    <p class="{k}">{b}</p>' for k, b in blocks)

    doc = f"""<!-- built by make_label.py from labels/{name}.txt -->
<meta charset="utf-8"><html lang="en">
<link rel="stylesheet" href="label.css">
<style>.tag{{ width:{w}in; height:{h}in }}</style>
<div class="sheet">
  <div class="tag">
{body}
  </div>
  <div class="caption">Cut on the dashed line &mdash; {frac(w)} &times;
    {frac(h)} in &middot; print at 100%</div>
</div>
"""
    out_html = os.path.join(HERE, f"label_{name}.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(doc)
    pdf = os.path.join(HERE, f"label_{name}.pdf")
    r = subprocess.run(["weasyprint", "--encoding", "utf-8", out_html, pdf],
                       capture_output=True, text=True, cwd=HERE)
    if r.returncode != 0:
        sys.exit("  weasyprint failed: " + (r.stderr or "").strip()[:300])
    print(f"  label_{name}.pdf   {frac(w)} x {frac(h)} in   "
          f"({os.path.getsize(pdf)/1024:.0f} KB)")
    check_fit(pdf, w, h)


def frac(x):
    whole = int(x); rest = round((x - whole) * 8)
    if not rest:
        return str(whole)
    from math import gcd
    g = gcd(rest, 8)
    return f"{whole} {rest//g}/{8//g}" if whole else f"{rest//g}/{8//g}"


def check_fit(pdf, w, h):
    """The label is a fixed box with overflow hidden, so too much text is
    silently cropped — the one failure here that would not announce itself.
    Measure the ink against the room it has."""
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return
    import glob
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        subprocess.run(["pdftoppm", "-png", "-r", "400", pdf,
                        os.path.join(t, "s")], check=True)
        im = Image.open(sorted(glob.glob(os.path.join(t, "s*.png")))[0]).convert("L")
    W, H = im.size
    ppi = W / SHEET_W
    ink = ImageChops.invert(im).point(lambda v: 255 if v > 40 else 0)
    px = ink.load()
    # Look INSIDE the dashed border. A 3px inset does not clear a 0.6pt rule at
    # 400dpi, so the check was measuring its own cut line and reporting 99% of
    # the height used no matter how small the type got.
    inset = 0.02 * ppi                      # 0.02in, comfortably past the rule
    x0 = (SHEET_W - w) / 2 * ppi + inset
    y0 = (SHEET_H - h) / 2 * ppi + inset
    cell = ink.crop((int(x0), int(y0), int(x0 + w * ppi - 2 * inset),
                     int(y0 + h * ppi - 2 * inset)))
    b = cell.getbbox()
    if not b:
        print("  ⚠ the label came out empty")
        return
    uw, uh = (b[2] - b[0]) / ppi, (b[3] - b[1]) / ppi
    print(f"  text occupies {uw:.2f} x {uh:.2f} in of {w} x {h} "
          f"({uh/h*100:.0f}% of the height)")
    if uh > h - 0.08 or uw > w - 0.08:
        print("  ⚠ it is close to the cut line — shrink the type or the text")


if __name__ == "__main__":
    main()
