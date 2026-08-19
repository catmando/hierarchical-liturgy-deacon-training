#!/bin/bash
# Regenerate raw_clips.tsv from whatever is in raw/. Records the size, SHA-256,
# duration, and codec of every source clip so a restore can be proven
# byte-identical. Only needed if the source clips themselves change.
#
#   ./make_manifest.sh
#
# Run from the repo root. Overwrites raw_clips.tsv; commit the result.
set -uo pipefail

RAW="raw"
OUT="raw_clips.tsv"

[ -d "$RAW" ] || { echo "error: $RAW/ not found — run from the repo root." >&2; exit 1; }

printf 'filename\tbytes\tsha256\tduration_s\tvcodec\twidth\theight\tfps\tacodec\n' > "$OUT"

n=0
for path in "$RAW"/*.mp4; do
  [ -e "$path" ] || { echo "error: no clips in $RAW/" >&2; exit 1; }
  name=$(basename "$path")
  n=$((n+1))
  printf '[%2d] %s\n' "$n" "$name" >&2

  bytes=$(stat -f%z "$path")
  sha=$(shasum -a 256 "$path" | awk '{print $1}')
  probe=$(ffprobe -v error -select_streams v:0 \
      -show_entries format=duration:stream=codec_name,width,height,r_frame_rate \
      -of default=nw=1:nk=1 "$path" | tr '\n' '|')
  acodec=$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name \
      -of default=nw=1:nk=1 "$path")

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$name" "$bytes" "$sha" \
    "$(echo "$probe" | cut -d'|' -f5)" \
    "$(echo "$probe" | cut -d'|' -f1)" \
    "$(echo "$probe" | cut -d'|' -f2)" \
    "$(echo "$probe" | cut -d'|' -f3)" \
    "$(echo "$probe" | cut -d'|' -f4)" \
    "${acodec:-none}" >> "$OUT"
done

echo >&2
echo "$OUT written: $n clips" >&2
