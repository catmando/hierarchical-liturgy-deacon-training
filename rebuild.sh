#!/usr/bin/env bash
#
# Rebuild master.mp4 from whatever is currently in _normalized/, and
# regenerate boundaries.tsv. Lossless and fast — run it as often as you
# like while you iterate on the edit.
#
# USAGE
#   ./rebuild.sh                    # use every .mp4 in _normalized/, sorted
#   ./rebuild.sh edit.txt           # use an explicit ordered list
#
#   ./rebuild.sh --trim 019 12 88   # re-encode clip 019 keeping 12s..88s
#                                   # (originals are kept as 019.orig.mp4)
#   ./rebuild.sh --restore 019      # undo a trim
#
# The EDL file for the second form is one filename per line, relative to
# _normalized/, in order. Blank lines and lines starting with # are ignored:
#
#   001.mp4
#   002.mp4
#   # homily not filmed
#   019a.mp4
#   020.mp4

set -euo pipefail

WORK="_normalized"
OUT="master.mp4"
CRF=18; PRESET=slow; FPS=30

[ -d "$WORK" ] || { echo "$WORK/ not found. Run normalize_and_join.sh first." >&2; exit 1; }

# ----------------------------------------------------------------------
# --trim / --restore
# ----------------------------------------------------------------------

if [ "${1:-}" = "--trim" ]; then
  n="$2"; start="$3"; end="$4"
  f="$WORK/${n}.mp4"; orig="$WORK/${n}.orig.mp4"
  [ -f "$f" ] || { echo "No such clip: $f" >&2; exit 1; }
  [ -f "$orig" ] || cp "$f" "$orig"
  dur=$(awk -v a="$end" -v b="$start" 'BEGIN{print a-b}')
  echo "Trimming $n: keeping ${start}s to ${end}s (${dur}s)"
  ffmpeg -hide_banner -loglevel error -y -nostdin \
    -ss "$start" -i "$orig" -t "$dur" \
    -r "$FPS" -fps_mode cfr \
    -c:v libx264 -preset "$PRESET" -crf "$CRF" -pix_fmt yuv420p \
    -c:a aac -b:a 192k -ar 48000 -ac 2 \
    "$f"
  echo "Done. Original kept at $orig"
  echo "NOTE: annotation offsets for clip $n now start from the new head."
  exit 0
fi

if [ "${1:-}" = "--restore" ]; then
  n="$2"
  [ -f "$WORK/${n}.orig.mp4" ] || { echo "No saved original for $n" >&2; exit 1; }
  mv "$WORK/${n}.orig.mp4" "$WORK/${n}.mp4"
  echo "Restored $n"
  exit 0
fi

# ----------------------------------------------------------------------
# Build the file list
# ----------------------------------------------------------------------

LIST=()
if [ -n "${1:-}" ]; then
  [ -f "$1" ] || { echo "EDL not found: $1" >&2; exit 1; }
  while IFS= read -r line; do
    line="${line%%#*}"; line="$(echo "$line" | xargs || true)"
    [ -z "$line" ] && continue
    [ -f "$WORK/$line" ] || { echo "Missing: $WORK/$line" >&2; exit 1; }
    LIST+=("$line")
  done < "$1"
  echo "Using EDL: $1  (${#LIST[@]} entries)"
else
  while IFS= read -r line; do LIST+=("$line"); done < <(
    find "$WORK" -maxdepth 1 -name '*.mp4' ! -name '*.orig.mp4' \
      -exec basename {} \; | sort
  )
  echo "Using every clip in $WORK/  (${#LIST[@]} entries)"
fi

[ ${#LIST[@]} -eq 0 ] && { echo "Nothing to join." >&2; exit 1; }

# ----------------------------------------------------------------------
# Concat + boundaries
# ----------------------------------------------------------------------

: > "$WORK/concat.txt"
: > "$WORK/manifest.tsv"
for f in "${LIST[@]}"; do
  printf "file '%s'\n" "$f" >> "$WORK/concat.txt"
  d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$WORK/$f")
  printf '%s\t%s\n' "$f" "$d" >> "$WORK/manifest.tsv"
done

echo "Joining -> $OUT"
ffmpeg -hide_banner -loglevel error -y -nostdin \
  -f concat -safe 0 -i "$WORK/concat.txt" \
  -c copy -movflags +faststart "$OUT"

awk -F'\t' 'BEGIN{t=0}
{
  h=int(t/3600); m=int((t%3600)/60); s=t-h*3600-m*60
  printf "%02d:%02d:%06.3f\t%s\t%s\n", h, m, s, $1, $2
  t+=$2
}
END{
  h=int(t/3600); m=int((t%3600)/60); s=t-h*3600-m*60
  printf "%02d:%02d:%06.3f\t[END]\t\n", h, m, s
}' "$WORK/manifest.tsv" > boundaries.tsv

echo
echo "Rebuilt $OUT"
echo "boundaries.tsv:"
cat boundaries.tsv
