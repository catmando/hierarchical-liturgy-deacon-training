#!/bin/bash
# Restore the 37 raw source clips from the GitHub release, then verify every
# byte against raw_clips.tsv. Safe to re-run: existing, valid files are skipped.
#
#   ./restore_raw_clips.sh            # download missing clips + verify all
#   ./restore_raw_clips.sh --verify   # verify what's on disk, download nothing
#
# Requires: gh (authenticated), shasum. Run from the repo root.
set -uo pipefail

TAG="raw-footage-v1"
MANIFEST="raw_clips.tsv"
verify_only=false
[[ "${1:-}" == "--verify" ]] && verify_only=true

[[ -f "$MANIFEST" ]] || { echo "error: $MANIFEST not found — run from the repo root." >&2; exit 1; }

ok=0; fixed=0; bad=0; missing=0

# Skip the header row; fields: filename, bytes, sha256, ...
while IFS=$'\t' read -r name bytes sha rest; do
  [[ "$name" == "filename" || -z "$name" ]] && continue

  # GitHub replaces spaces with dots in release asset names.
  asset="${name// /.}"

  if [[ ! -f "$name" ]]; then
    if $verify_only; then
      echo "MISSING  $name"; ((missing++)); continue
    fi
    echo "download $name"
    if ! gh release download "$TAG" --pattern "$asset" --output "$name" --clobber 2>/dev/null; then
      echo "FAILED   $name (asset '$asset' not found in release $TAG)" >&2
      ((missing++)); continue
    fi
    ((fixed++))
  fi

  actual_bytes=$(stat -f%z "$name")
  if [[ "$actual_bytes" != "$bytes" ]]; then
    echo "BAD SIZE $name (expected $bytes, got $actual_bytes)" >&2; ((bad++)); continue
  fi

  actual_sha=$(shasum -a 256 "$name" | awk '{print $1}')
  if [[ "$actual_sha" != "$sha" ]]; then
    echo "BAD HASH $name" >&2; ((bad++)); continue
  fi

  ((ok++))
done < "$MANIFEST"

echo
echo "verified $ok   downloaded $fixed   corrupt $bad   missing $missing"
[[ $bad -eq 0 && $missing -eq 0 ]] || exit 1
echo "All raw clips present and byte-identical to the manifest."
