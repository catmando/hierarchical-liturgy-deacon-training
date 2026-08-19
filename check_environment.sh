#!/bin/bash
# Verify this machine can build the training video. Checks the tools, the
# ffmpeg features build.py actually uses, a usable font, disk space, and the
# state of the working directories. Run from the repo root.
#
#   ./check_environment.sh
#
# Exits 0 if the machine is ready to build.
set -uo pipefail

fail=0; warn=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }
note() { printf '  \033[33m!\033[0m %s\n' "$1"; warn=$((warn+1)); }

echo
echo "Tools"
for t in git gh python3 ffmpeg ffprobe shasum; do
  if command -v "$t" >/dev/null 2>&1; then
    ok "$t  ($(command -v "$t"))"
  else
    bad "$t is not installed"
  fi
done

echo
echo "ffmpeg features"
if command -v ffmpeg >/dev/null 2>&1; then
  ffver=$(ffmpeg -version 2>/dev/null | head -1 | awk '{print $3}')
  ok "version $ffver"
  # build.py burns card text with drawtext and renders annotations with libass.
  # The stock homebrew/core formula has historically shipped without these,
  # which is why the homebrew-ffmpeg tap is required.
  for filt in drawtext ass subtitles scale pad concat; do
    if ffmpeg -hide_banner -filters 2>/dev/null | awk -v f="$filt" '$2==f{found=1} END{exit !found}'; then
      ok "filter: $filt"
    else
      bad "filter '$filt' missing — install ffmpeg from the homebrew-ffmpeg tap (see README)"
    fi
  done
  if ffmpeg -hide_banner -encoders 2>/dev/null | grep -q ' libx264 '; then
    ok "encoder: libx264"
  else
    bad "encoder libx264 missing"
  fi
else
  bad "cannot check features — ffmpeg missing"
fi

echo
echo "Python packages"
if python3 -c 'import yaml' 2>/dev/null; then
  ok "PyYAML $(python3 -c 'import yaml; print(yaml.__version__)')"
else
  bad "PyYAML missing — run: pip3 install --break-system-packages pyyaml"
fi

echo
echo "Fonts"
# build.py's FONT_CANDIDATES are all macOS system paths; card rendering dies
# without one of them.
font=""
for f in "/System/Library/Fonts/Supplemental/Georgia.ttf" \
         "/System/Library/Fonts/Supplemental/Times New Roman.ttf" \
         "/System/Library/Fonts/Supplemental/Arial.ttf" \
         "/Library/Fonts/Arial.ttf"; do
  [ -f "$f" ] && { font="$f"; break; }
done
[ -n "$font" ] && ok "card font: $font" \
               || bad "none of build.py's FONT_CANDIDATES exist (macOS system fonts)"

echo
echo "GitHub access"
if command -v gh >/dev/null 2>&1; then
  if gh auth status >/dev/null 2>&1; then
    ok "gh authenticated as $(gh api user --jq .login 2>/dev/null)"
  else
    bad "gh is not authenticated — run: gh auth login"
  fi
fi

echo
echo "Project files"
for f in build.py annotations.csv raw_clips.tsv normalize_and_join.sh restore_raw_clips.sh; do
  [ -f "$f" ] && ok "$f" || bad "$f missing — are you in the repo root?"
done
python3 -m py_compile build.py 2>/dev/null && ok "build.py compiles" \
                                           || bad "build.py has a syntax error"

echo
echo "Footage"
nraw=$(ls raw/*.mp4 2>/dev/null | wc -l | tr -d ' ')
if [ "$nraw" = "37" ]; then
  ok "raw/ has all 37 clips  (verify bytes with ./restore_raw_clips.sh --verify)"
elif [ "$nraw" = "0" ]; then
  note "raw/ is empty — run ./restore_raw_clips.sh to download the footage"
else
  note "raw/ has $nraw of 37 clips — run ./restore_raw_clips.sh to fill the gaps"
fi
nnorm=$(ls normalized/[0-9][0-9][0-9].mp4 2>/dev/null | wc -l | tr -d ' ')
if [ "$nnorm" = "37" ]; then
  ok "normalized/ has all 37 clips — build.py can run now"
else
  note "normalized/ has $nnorm of 37 clips — run ./normalize_and_join.sh (takes hours)"
fi

echo
echo "Disk space"
avail_kb=$(df -k . | tail -1 | awk '{print $4}')
avail_gb=$((avail_kb / 1048576))
if [ "$avail_gb" -ge 40 ]; then
  ok "${avail_gb} GB free (a full rebuild needs about 30 GB)"
elif [ "$avail_gb" -ge 30 ]; then
  note "${avail_gb} GB free — enough, but tight; a full rebuild uses about 30 GB"
else
  bad "${avail_gb} GB free — a full rebuild needs about 30 GB"
fi

echo
if [ "$fail" -eq 0 ] && [ "$warn" -eq 0 ]; then
  echo "Ready to build. Try:  python3 build.py --clip 3"
elif [ "$fail" -eq 0 ]; then
  echo "Tooling is fine; $warn item(s) above need footage restored or rebuilt."
else
  echo "$fail problem(s) must be fixed before building."
  exit 1
fi
