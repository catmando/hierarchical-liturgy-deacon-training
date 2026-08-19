#!/usr/bin/env bash
#
# Generate a title card that matches the normalized clips exactly, so it
# can be concatenated losslessly with them.
#
# USAGE
#   ./make_card.sh OUTPUT.mp4 SECONDS "Line one" ["Line two" ...]
#
# EXAMPLES
#   ./make_card.sh _normalized/019a.mp4 6 "Homily" "not shown"
#   ./make_card.sh _normalized/033a.mp4 8 \
#       "Communion of the Clergy" "" "not filmed — see the printed notes"
#
# Naming tip: name cards so they sort into position — a card between clips
# 019 and 020 should be 019a.mp4. Then the rebuild script picks up the
# order automatically.

set -euo pipefail

# ---- must match normalize_and_join.sh -------------------------------
W=1920; H=1080; FPS=30; CRF=18; PRESET=slow
# ---------------------------------------------------------------------

BG="black"          # background colour
FG="white"          # text colour
SIZE=64             # main text size, pixels
SPACING=28          # extra space between lines

[ $# -lt 3 ] && { echo "Usage: $0 OUTPUT.mp4 SECONDS \"Line one\" [\"Line two\" ...]" >&2; exit 1; }

OUTPUT="$1"; shift
SECONDS_DUR="$1"; shift

# Find a usable font
FONT=""
for c in \
  "/System/Library/Fonts/Supplemental/Georgia.ttf" \
  "/System/Library/Fonts/Supplemental/Times New Roman.ttf" \
  "/System/Library/Fonts/Supplemental/Arial.ttf" \
  "/Library/Fonts/Arial.ttf" \
  "/System/Library/Fonts/Helvetica.ttc" ; do
  [ -f "$c" ] && { FONT="$c"; break; }
done
[ -z "$FONT" ] && { echo "No font found. Set FONT= manually near the top." >&2; exit 1; }

TXT=$(mktemp /tmp/card.XXXXXX)
trap 'rm -f "$TXT"' EXIT
printf '%s\n' "$@" > "$TXT"

echo "Card: $OUTPUT  (${SECONDS_DUR}s)"
printf '  %s\n' "$@"

ffmpeg -hide_banner -loglevel error -y -nostdin \
  -f lavfi -i "color=c=${BG}:s=${W}x${H}:r=${FPS}:d=${SECONDS_DUR}" \
  -f lavfi -i "anullsrc=channel_layout=stereo:sample_rate=48000" \
  -vf "drawtext=fontfile='${FONT}':textfile='${TXT}':fontcolor=${FG}:fontsize=${SIZE}:line_spacing=${SPACING}:x=(w-text_w)/2:y=(h-text_h)/2,fade=t=in:st=0:d=0.4,fade=t=out:st=$(awk -v d="$SECONDS_DUR" 'BEGIN{print d-0.4}'):d=0.4,setsar=1" \
  -t "$SECONDS_DUR" \
  -r "$FPS" -fps_mode cfr \
  -c:v libx264 -preset "$PRESET" -crf "$CRF" -pix_fmt yuv420p \
  -c:a aac -b:a 192k -ar 48000 -ac 2 \
  -shortest \
  "$OUTPUT"

echo "  done"
