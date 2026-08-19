#!/bin/bash
# Restore the 37 raw source clips into raw/, then verify every byte against
# raw_clips.tsv. Safe to re-run: files already present and valid are skipped.
#
#   ./restore_raw_clips.sh            # download what's missing, verify all
#   ./restore_raw_clips.sh --verify   # verify what's on disk, download nothing
#
# Requires: gh (authenticated), shasum. Run from the repo root.
set -uo pipefail

TAG="raw-footage-v1"
MANIFEST="raw_clips.tsv"
RAW="raw"

verify_only=false
[[ "${1:-}" == "--verify" ]] && verify_only=true

[[ -f "$MANIFEST" ]] || { echo "error: $MANIFEST not found — run from the repo root." >&2; exit 1; }
mkdir -p "$RAW"

ok=0; fetched=0; bad=0; missing=0

# Skip the header row; fields are: filename, bytes, sha256, then technical data.
while IFS=$'\t' read -r name bytes sha _rest; do
  [[ "$name" == "filename" || -z "$name" ]] && continue

  path="$RAW/$name"
  # GitHub replaces spaces with dots in release asset filenames.
  asset="${name// /.}"

  if [[ ! -f "$path" ]]; then
    if $verify_only; then
      echo "MISSING  $name"; ((missing++)); continue
    fi
    echo "fetching $name"
    if ! gh release download "$TAG" --pattern "$asset" --output "$path" --clobber 2>/dev/null; then
      echo "FAILED   $name (no asset '$asset' in release $TAG)" >&2
      ((missing++)); continue
    fi
    ((fetched++))
  fi

  actual_bytes=$(stat -f%z "$path")
  if [[ "$actual_bytes" != "$bytes" ]]; then
    echo "BAD SIZE $name (expected $bytes, got $actual_bytes)" >&2; ((bad++)); continue
  fi

  if [[ "$(shasum -a 256 "$path" | awk '{print $1}')" != "$sha" ]]; then
    echo "BAD HASH $name" >&2; ((bad++)); continue
  fi

  ((ok++))
done < "$MANIFEST"

echo
echo "verified $ok   fetched $fetched   corrupt $bad   missing $missing"
if [[ $bad -eq 0 && $missing -eq 0 ]]; then
  echo "All 37 raw clips present in $RAW/ and byte-identical to the manifest."
else
  exit 1
fi
