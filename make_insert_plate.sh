#!/usr/bin/env bash
# The insert spread, as an image, so the printed rubric can carry it at true
# size on a page of its own — the same idea as the roles card.
#
# Only the spread is taken, not the whole sheet: the cut line, fold line and
# caption are redrawn by the rubric's own stylesheet, so they sit where that
# page needs them rather than where insert.pdf put them.
set -euo pipefail
SRC="${1:-booklet/insert.pdf}"
OUT="${2:-art/insert_136_137.png}"
DPI=400
# the spread is centred on a Letter sheet: 7.25 x 5.875 in
python3 - "$SRC" "$OUT" "$DPI" <<'PY'
import subprocess, sys, glob, tempfile, os
src, out, dpi = sys.argv[1], sys.argv[2], int(sys.argv[3])
x = round((8.5 - 7.25) / 2 * dpi); y = round((11 - 5.875) / 2 * dpi)
w = round(7.25 * dpi);             h = round(5.875 * dpi)
with tempfile.TemporaryDirectory() as t:
    subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-x", str(x), "-y", str(y),
                    "-W", str(w), "-H", str(h), src, os.path.join(t, "p")], check=True)
    from PIL import Image
    im = Image.open(sorted(glob.glob(os.path.join(t, "p*.png")))[0]).convert("RGB")
# RGB, not greyscale — the rubrics are red, and that is the whole point of them
im.quantize(colors=64, method=Image.Quantize.MEDIANCUT).save(out, optimize=True)
print(f"{out}  {im.size[0]}x{im.size[1]}  ({os.path.getsize(out)/1024:.0f} KB)")
PY
