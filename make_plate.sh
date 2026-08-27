#!/usr/bin/env bash
# A cut-out piece, as an image, so the printed rubric can carry it at true size
# on a page of its own — the same idea as the roles card.
#
#   ./make_plate.sh booklet/insert.pdf art/insert_136_137.png 7.25 5.875
#   ./make_plate.sh booklet/label_is_polla.pdf art/label_is_polla.png 1.625 1.25
#
# Only the piece is taken, not the whole sheet: the cut line and caption are
# redrawn by the rubric's stylesheet, so they sit where that page needs them.
set -euo pipefail
SRC="${1:-booklet/insert.pdf}"
OUT="${2:-art/insert_136_137.png}"
PW="${3:-7.25}"
PH="${4:-5.875}"
DPI=400
# the piece is centred on a Letter sheet
python3 - "$SRC" "$OUT" "$DPI" "$PW" "$PH" <<'PY'
import subprocess, sys, glob, tempfile, os
src, out, dpi = sys.argv[1], sys.argv[2], int(sys.argv[3])
pw, ph = float(sys.argv[4]), float(sys.argv[5])
x = round((8.5 - pw) / 2 * dpi); y = round((11 - ph) / 2 * dpi)
w = round(pw * dpi);             h = round(ph * dpi)
with tempfile.TemporaryDirectory() as t:
    subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-x", str(x), "-y", str(y),
                    "-W", str(w), "-H", str(h), src, os.path.join(t, "p")], check=True)
    from PIL import Image
    im = Image.open(sorted(glob.glob(os.path.join(t, "p*.png")))[0]).convert("RGB")
# RGB, not greyscale — the rubrics are red, and that is the whole point of them
im.quantize(colors=64, method=Image.Quantize.MEDIANCUT).save(out, optimize=True)
print(f"{out}  {im.size[0]}x{im.size[1]}  ({os.path.getsize(out)/1024:.0f} KB)")
PY
