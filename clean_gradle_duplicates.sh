#!/usr/bin/env bash
# clean_gradle_duplicates.sh
# Remove Groovy Gradle files when a .kts counterpart exists.

set -euo pipefail

ROOT_DIR="."
APPLY=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      ROOT_DIR="$2"
      shift 2
      ;;
    --apply)
      APPLY=true
      shift
      ;;
    *)
      echo "Usage: $0 [--root <dir>] [--apply]"
      exit 1
      ;;
  esac
done

echo "Scanning $ROOT_DIR for duplicate Gradle files..."
echo

# File patterns to check
for f in $(find "$ROOT_DIR" -type f -name "*.gradle"); do
  # skip already .kts
  if [[ "$f" == *.kts ]]; then
    continue
  fi

  # candidate .kts
  kts="${f}.kts"

  if [[ -f "$kts" ]]; then
    if $APPLY; then
      echo "Deleting: $f (KTS counterpart exists: $kts)"
      rm -f "$f"
    else
      echo "[DRY RUN] Would delete: $f (KTS counterpart exists: $kts)"
    fi
  fi
done

echo
if $APPLY; then
  echo "Cleanup complete. Groovy Gradle files with .kts twins have been removed."
else
  echo "Dry run complete. Re-run with --apply to actually delete the files."
fi