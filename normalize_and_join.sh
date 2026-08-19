#!/usr/bin/env bash
#
# Normalize 37 mixed VFR / mixed-orientation phone clips and join them
# into one master video, with cumulative chapter boundaries.
#
# Built for an unattended overnight run:
#   - Resumable. Kill it and re-run; finished clips are skipped.
#   - Survives a bad clip. Failures are logged, the run continues.
#   - Preflight mode shows you what it will do before committing hours.
#
# USAGE
#   chmod +x normalize_and_join.sh
#   ./normalize_and_join.sh --check         # preflight, no encoding
#   ./normalize_and_join.sh                 # full run
#   caffeinate -i ./normalize_and_join.sh   # full run, Mac stays awake
#
# Requires ffmpeg + ffprobe (brew install ffmpeg).

set -uo pipefail

# ======================================================================
# SETTINGS
# ======================================================================

W=1920
H=1080
FPS=30
CRF=18
PRESET=slow

# Portrait clips are PILLARBOXED by default (black bars, nothing lost).
# To CROP a portrait clip to 16:9 instead, list its exact filename here.
# Optionally append :OFFSET to set the crop window's distance from the
# top of the frame in pixels. Omit the offset to crop from the center.
#
#   CROP_LIST=(
#     "14 - vesting.mp4"
#     "22 - great entrance.mp4:300"
#   )
CROP_LIST=(
)

WORK="_normalized"
OUT="master.mp4"
LOG="encode.log"

# ======================================================================

CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

command -v ffmpeg  >/dev/null || { echo "ffmpeg not found. brew install ffmpeg" >&2; exit 1; }
command -v ffprobe >/dev/null || { echo "ffprobe not found. brew install ffmpeg" >&2; exit 1; }

mkdir -p "$WORK"

# ----------------------------------------------------------------------
# Collect clips in order
# ----------------------------------------------------------------------

CLIPS=()
while IFS= read -r line; do CLIPS+=("$line"); done < <(
  find . -maxdepth 1 -type f \( -iname '*.mp4' -o -iname '*.mov' \) \
    ! -name '._*' -print | sed 's|^\./||' | sort
)

[ ${#CLIPS[@]} -eq 0 ] && { echo "No clips found." >&2; exit 1; }

# Warn about unpadded leading numbers, which sort wrongly (1, 10, 11, 2...)
if printf '%s\n' "${CLIPS[@]}" | grep -qE '^[0-9][^0-9]'; then
  echo "!! WARNING: some filenames start with an unpadded single digit."
  echo "!! Sort order will be wrong (1, 10, 11, 2...). Rename to 01, 02, ..."
  echo
fi

# ----------------------------------------------------------------------
# Is this clip in CROP_LIST? Sets CROP_HIT / CROP_OFFSET.
# ----------------------------------------------------------------------
crop_lookup() {
  local name="$1" entry
  CROP_HIT=0; CROP_OFFSET=""
  for entry in "${CROP_LIST[@]:-}"; do
    [ -z "$entry" ] && continue
    if [ "$entry" = "$name" ]; then
      CROP_HIT=1; return
    elif [ "${entry%:*}" = "$name" ] && [ "$entry" != "${entry%:*}" ]; then
      CROP_HIT=1; CROP_OFFSET="${entry##*:}"; return
    fi
  done
}

# ----------------------------------------------------------------------
# PREFLIGHT
# ----------------------------------------------------------------------

echo "======================================================================"
echo " PREFLIGHT — ${#CLIPS[@]} clips"
echo "======================================================================"
printf '%-3s %-40s %-11s %-5s %-6s %s\n' "#" "FILE" "SOURCE" "ROT" "AUDIO" "PLAN"

i=0; total=0; n_portrait=0; n_noaudio=0
for f in "${CLIPS[@]}"; do
  i=$((i+1))
  sw=$(ffprobe -v error -select_streams v:0 -show_entries stream=width  -of csv=p=0 "$f" 2>/dev/null)
  sh=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$f" 2>/dev/null)
  rot=$(ffprobe -v error -select_streams v:0 \
          -show_entries stream_side_data=rotation \
          -of default=nw=1:nk=1 "$f" 2>/dev/null | head -1)
  rot="${rot:-0}"
  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f" 2>/dev/null)
  dur="${dur:-0}"
  has_a=$(ffprobe -v error -select_streams a -show_entries stream=index \
          -of csv=p=0 "$f" 2>/dev/null | head -1)

  # Effective orientation AFTER ffmpeg applies the rotation flag
  case "$rot" in
    90|-90|270|-270) ew="$sh"; eh="$sw" ;;
    *)               ew="$sw"; eh="$sh" ;;
  esac

  crop_lookup "$f"
  if [ "${eh:-0}" -gt "${ew:-0}" ] 2>/dev/null; then
    n_portrait=$((n_portrait+1))
    if [ "$CROP_HIT" = "1" ]; then
      plan="portrait -> CROP${CROP_OFFSET:+ @${CROP_OFFSET}px}"
    else
      plan="portrait -> pillarbox"
    fi
  else
    plan="landscape -> scale"
  fi

  if [ -z "$has_a" ]; then
    plan="$plan +silent-audio"; n_noaudio=$((n_noaudio+1)); astr="NO"
  else
    astr="yes"
  fi

  printf '%-3s %-40.40s %-11s %-5s %-6s %s\n' \
    "$i" "$f" "${sw}x${sh}" "$rot" "$astr" "$plan"

  total=$(awk -v a="$total" -v b="$dur" 'BEGIN{print a+b}')
done

echo "----------------------------------------------------------------------"
awk -v t="$total" 'BEGIN{
  printf " Total runtime: %d:%02d:%05.2f\n", int(t/3600), int((t%3600)/60), t%60 }'
echo " Portrait clips: $n_portrait    Clips without audio: $n_noaudio"
echo " Output: ${W}x${H} @ ${FPS}fps CFR, x264 crf ${CRF} preset ${PRESET}"
echo "======================================================================"
echo

if [ "$CHECK_ONLY" = "1" ]; then
  echo "Preflight only. Review the PLAN column, set CROP_LIST if needed,"
  echo "then re-run without --check."
  exit 0
fi

# ----------------------------------------------------------------------
# PASS 1 — normalize
# ----------------------------------------------------------------------

echo "Starting encode at $(date). Logging to $LOG"
echo "=== run started $(date) ===" >> "$LOG"
echo

: > "$WORK/manifest.tsv"
FAILED=()
i=0

for f in "${CLIPS[@]}"; do
  i=$((i+1))
  n=$(printf '%03d' "$i")
  target="$WORK/${n}.mp4"

  # Resume: skip if already encoded and readable
  if [ -f "$target" ] && ffprobe -v error -show_entries format=duration \
       -of csv=p=0 "$target" >/dev/null 2>&1; then
    echo "[$n/${#CLIPS[@]}] skip (done)  $f"
  else
    echo "[$n/${#CLIPS[@]}] $(date '+%H:%M:%S')  $f"

    crop_lookup "$f"
    if [ "$CROP_HIT" = "1" ]; then
      CH='trunc(iw*9/16/2)*2'
      YOFF="${CROP_OFFSET:-(ih-$CH)/2}"
      VF="crop=iw:${CH}:0:${YOFF},scale=${W}:${H},setsar=1"
    else
      VF="scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    fi

    has_a=$(ffprobe -v error -select_streams a -show_entries stream=index \
            -of csv=p=0 "$f" 2>/dev/null | head -1)

    if [ -n "$has_a" ]; then
      ffmpeg -hide_banner -loglevel error -y -nostdin -i "$f" \
        -vf "$VF" -r "$FPS" -fps_mode cfr \
        -c:v libx264 -preset "$PRESET" -crf "$CRF" -pix_fmt yuv420p \
        -c:a aac -b:a 192k -ar 48000 -ac 2 \
        "$target" >>"$LOG" 2>&1
      rc=$?
    else
      # Silent track, so every clip has the same stream layout for concat
      ffmpeg -hide_banner -loglevel error -y -nostdin -i "$f" \
        -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=48000 \
        -vf "$VF" -r "$FPS" -fps_mode cfr -shortest \
        -c:v libx264 -preset "$PRESET" -crf "$CRF" -pix_fmt yuv420p \
        -c:a aac -b:a 192k \
        "$target" >>"$LOG" 2>&1
      rc=$?
    fi

    if [ $rc -ne 0 ] || [ ! -s "$target" ]; then
      echo "    !! FAILED — see $LOG"
      echo "!! FAILED: $f" >> "$LOG"
      FAILED+=("$f"); rm -f "$target"; continue
    fi
  fi

  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$target")
  printf '%s\t%s\t%s\n' "$n" "$dur" "$f" >> "$WORK/manifest.tsv"
done

echo

if [ ${#FAILED[@]} -gt 0 ]; then
  echo "!! ${#FAILED[@]} clip(s) failed and were left out:"
  printf '   %s\n' "${FAILED[@]}"
  echo "!! Fix or remove them and re-run; finished clips will be skipped."
  echo
fi

# ----------------------------------------------------------------------
# PASS 2 — join (lossless; every clip now matches)
# ----------------------------------------------------------------------

awk -F'\t' '{ printf "file '\''%s.mp4'\''\n", $1 }' \
  "$WORK/manifest.tsv" > "$WORK/concat.txt"

echo "Joining -> $OUT"
ffmpeg -hide_banner -loglevel error -y -nostdin \
  -f concat -safe 0 -i "$WORK/concat.txt" \
  -c copy -movflags +faststart "$OUT" >>"$LOG" 2>&1 \
  || { echo "Concat failed — see $LOG" >&2; exit 1; }

# ----------------------------------------------------------------------
# Chapter boundaries
# ----------------------------------------------------------------------

awk -F'\t' 'BEGIN{t=0}
{
  h=int(t/3600); m=int((t%3600)/60); s=t-h*3600-m*60
  printf "%02d:%02d:%06.3f\t%s\n", h, m, s, $3
  t+=$2
}
END{
  h=int(t/3600); m=int((t%3600)/60); s=t-h*3600-m*60
  printf "%02d:%02d:%06.3f\t[END]\n", h, m, s
}' "$WORK/manifest.tsv" > boundaries.tsv

echo
echo "======================================================================"
echo " Finished $(date)"
echo "   Master video:        $OUT"
echo "   Chapter boundaries:  boundaries.tsv   <-- send me this file"
echo "   Encoder log:         $LOG"
echo "   Normalized clips:    $WORK/  (delete once happy with $OUT)"
echo "======================================================================"
echo
cat boundaries.tsv
