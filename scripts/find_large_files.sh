#!/usr/bin/env bash
set -euo pipefail

THRESHOLD_MEGABYTES=20
THRESHOLD_HUMAN="${THRESHOLD_MEGABYTES} MB"

show_help() {
  cat <<'USAGE'
Usage: scripts/find_large_files.sh

Scans the repository for files larger than 20MB and prints their sizes and
paths. When large binary assets such as .mp4, .psd, or .zip files are found,
the script suggests tracking them with Git LFS.
USAGE
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  show_help
  exit 0
fi

FOUND=0

while IFS= read -r -d '' file; do
  if [[ $FOUND -eq 0 ]]; then
    echo "Files larger than ${THRESHOLD_HUMAN}:"
    FOUND=1
  fi

  size_bytes=$(stat -c %s "$file")
  size_readable=$(numfmt --to=iec --suffix=B "$size_bytes")
  display_path=${file#./}
  printf ' - %s\t%s\n' "$size_readable" "$display_path"

  case "${display_path,,}" in
    *.mp4|*.psd|*.zip)
      echo "   -> Consider tracking this file with Git LFS."
      ;;
  esac
done < <(
  find . \
    -path './.git' -prune -o \
    -type f -size +"${THRESHOLD_MEGABYTES}"M -print0
)

if [[ $FOUND -eq 0 ]]; then
  echo "No files larger than ${THRESHOLD_HUMAN} were found."
fi
