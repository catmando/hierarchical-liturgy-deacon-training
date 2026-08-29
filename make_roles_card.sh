#!/usr/bin/env bash
# Lay the diocesan roles chart out as a card to cut from a Letter sheet.
#
#   in :  Roles for Concelebrating Deacons.pdf   (Letter, one page)
#   out:  art/roles_card.pdf                     (Letter, one card, cut marks)
#
# The card is 3.375 x 5.25 in, which fits a standard liturgy book.
#
# Two passes, and the reason matters. The source page begins by painting an
# opaque white rectangle over the whole sheet:
#
#     q 0 0 612 792 re W n /Cs1 cs 1 1 1 sc 0 792 m ... h f
#
# so anything drawn under the page content is painted over and never seen.
#
# Two pdfwrite quirks bear on this, both established by testing rather than
# assumed. A /Install procedure can set the CTM — that survives into the page —
# but its PAINTING operators are silently discarded, while still counting
# towards the file's bounding box, which makes the marks look present in
# `gs -sDEVICE=bbox` while rendering nothing at all. /BeginPage and /EndPage
# both paint properly. The cut marks therefore go in /EndPage, which runs
# AFTER the page content and so cannot be painted over.
#
# The content transform goes in /BeginPage rather than /Install for the same
# reason of coordinate spaces: /Install sets the device's DEFAULT matrix, so
# an initgraphics inside /EndPage returns to it and the marks come out
# carrying the content's scale. With the transform in /BeginPage, /EndPage
# draws in true page points.
#
# Pass 1 shrinks the media box to the table alone; pass 2 imposes that on
# Letter and adds the marks.
#
# Pass 1 also drops the source's page number, which sits by itself near the
# foot of the sheet. Including it forced the table down to 53% to fit the card;
# without it the table sits at 70%, a third larger and much easier to read.
set -euo pipefail

SRC="${1:-Roles for Concelebrating Deacons.pdf}"
OUT="${2:-art/roles_card.pdf}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# The table's ink box in the source, in points, origin bottom-left. MEASURED,
# not hardcoded: the chart gets revised, and stale geometry would crop or
# shrink it silently. A 200 dpi render is scanned for rows carrying ink and
# those are grouped into bands; the table is the tall one, and the page number
# a small band by itself near the foot, which is excluded by the gap test.
read -r TX0 TY0 TW TH <<< "$(python3 - "$SRC" "$TMP" <<'PY'
import subprocess, sys, glob
from PIL import Image, ImageChops
src, tmp = sys.argv[1], sys.argv[2]
DPI, PH = 200, 792.0
subprocess.run(["pdftoppm", "-png", "-r", str(DPI), src, tmp + "/m"], check=True)
im = Image.open(sorted(glob.glob(tmp + "/m*.png"))[0]).convert("L")
W, H = im.size
ink = ImageChops.invert(im).point(lambda v: 255 if v > 40 else 0)
cols = ink.load()
rows = [any(cols[x, y] for x in range(0, W, 2)) for y in range(H)]
bands, start = [], None
for y, on in enumerate(rows + [False]):
    if on and start is None:
        start = y
    elif not on and start is not None:
        if y - start > 2:
            bands.append((start, y))
        start = None
if not bands:
    sys.exit("no ink found in " + src)
# start from the tallest band and absorb neighbours that are close to it, so a
# table broken by a blank row stays whole while a lone page number does not
# drag the box down the sheet
GAP = 40 * DPI / 72
a, b = max(bands, key=lambda p: p[1] - p[0])
grew = True
while grew:
    grew = False
    for c, d in bands:
        if c >= a and d <= b:
            continue
        if c - b < GAP and d > b:
            b, grew = d, True
        elif a - d < GAP and c < a:
            a, grew = c, True
bb = ink.crop((0, a, W, b)).getbbox()
k = 72.0 / DPI
x0, x1 = bb[0] * k, bb[2] * k
top, bot = (a + bb[1]) * k, (a + bb[3]) * k
print(f"{x0:.1f} {PH-bot:.1f} {x1-x0:.1f} {bot-top:.1f}")
PY
)"
echo "  table measured at ${TW} x ${TH} pt, origin ${TX0},${TY0}"

# The measured table, rounded up to whole points. Both passes use it: pass 1
# as its page size, pass 2 to work out the scale. These were hardcoded once,
# and a table that lost a row then printed smaller than it needed to, the
# difference showing as blank inside the cut line.
read -r PGW PGH <<< "$(python3 -c "import math,sys; print(math.ceil(float(sys.argv[1])), math.ceil(float(sys.argv[2])))" "$TW" "$TH")"

# --- pass 1: the table becomes the whole page ------------------------------
gs -q -o "$TMP/table.pdf" -sDEVICE=pdfwrite \
   -dDEVICEWIDTHPOINTS=$PGW -dDEVICEHEIGHTPOINTS=$PGH -dFIXEDMEDIA \
   -dCompatibilityLevel=1.5 \
   -c "<</Install{ -$TX0 -$TY0 translate }>> setpagedevice" \
   -f "$SRC" 2>&1 | grep -v "Annotation destination" || true

# --- pass 2: impose it on Letter, with cut marks ---------------------------
read -r S TXX TYY CX CY CW CH <<< "$(python3 - "$PGW" "$PGH" <<'PY'
import sys
PW, PH = 612.0, 792.0
CW, CH = 3.375 * 72, 5.25 * 72     # 243 x 378
PGW, PGH = float(sys.argv[1]), float(sys.argv[2])   # the page from pass 1
M = 4.0                            # inner margin, so a hand cut has room
s = min((CW - 2*M) / PGW, (CH - 2*M) / PGH)
cx, cy = (PW - CW) / 2, (PH - CH) / 2
print(f"{s:.5f} {cx + (CW - PGW*s)/2:.2f} {cy + (CH - PGH*s)/2:.2f} "
      f"{cx:.1f} {cy:.1f} {CW:.0f} {CH:.0f}")
PY
)"

gs -q -o "$OUT" -sDEVICE=pdfwrite \
   -dDEVICEWIDTHPOINTS=612 -dDEVICEHEIGHTPOINTS=792 -dFIXEDMEDIA \
   -dCompatibilityLevel=1.5 \
   -c "<</BeginPage{ pop $TXX $TYY translate $S $S scale }
        /EndPage{
          exch pop 2 lt {
            gsave initgraphics
              0.45 setgray 0.7 setlinewidth [3 3] 0 setdash
              $CX $CY $CW $CH rectstroke
              [] 0 setdash
              0.4 setgray /Helvetica findfont 7.5 scalefont setfont
              $CX 192 moveto
              (Cut on the dashed line - 3 3/8 x 5 1/4 in, to fit a liturgy book) show
            grestore
            true
          }{ false } ifelse
        }>> setpagedevice" \
   -f "$TMP/table.pdf" 2>&1 | grep -v "Annotation destination" || true

echo "$OUT  ($(wc -c < "$OUT") bytes)  card scaled to ${S}"

# --- a PNG of the chart, for the rubric page and the printed document ------
# Same table box as above, rendered straight from the source at 300 dpi.
pdftoppm -png -r 300 \
  -x $(python3 -c "print(round($TX0*300/72))") \
  -y $(python3 -c "print(round((792-$TY0-$TH)*300/72))") \
  -W $(python3 -c "print(round($TW*300/72))") \
  -H $(python3 -c "print(round($TH*300/72))") \
  "$SRC" "$TMP/chart"
python3 - "$TMP" <<'PY'
import sys, glob
from PIL import Image
src = sorted(glob.glob(sys.argv[1] + "/chart*.png"))[0]
im = Image.open(src).convert("L")
# line art: a small palette keeps it sharp and small, since this rides inside
# the HTML as a data URI
im.quantize(colors=16, method=Image.Quantize.MEDIANCUT).save(
    "art/roles_chart.png", optimize=True)
print(f"art/roles_chart.png  {im.size[0]}x{im.size[1]}")
PY
echo "art/roles_chart.png  ($(wc -c < art/roles_chart.png) bytes)"
