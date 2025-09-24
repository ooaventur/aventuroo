#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Perdorimi: cleanup.sh [--dry-run|--apply] [allowlist]
  --dry-run   Tregon cfare do te fshihet pa fshire (default)
  --apply     Kryen fshirjen dhe logon ne out/cleanup.log
  allowlist   Rruga drejt cleanup-allowlist.txt (default: ne rrënjën e projektit)
USAGE
}

MODE="dry-run"
if [[ $# -gt 0 ]]; then
  case "$1" in
    --dry-run)
      MODE="dry-run"
      shift
      ;;
    --apply)
      MODE="apply"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Argument i panjohur: $1" >&2
      usage
      exit 1
      ;;
  esac
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ALLOWLIST_FILE="${1:-$REPO_ROOT/cleanup-allowlist.txt}"

if [[ ! -f "$ALLOWLIST_FILE" ]]; then
  echo "Allowlist nuk u gjet: $ALLOWLIST_FILE" >&2
  exit 1
fi

# Lista e path-eve te mbrojtura (relative ndaj rrënjës se projektit)
PROTECTED_PATHS=(
  "/data"
  "/out/raw"
  "/scripts"
  "/.github"
  "/assets"
  "/netlify.toml"
  "/_headers"
)

PROTECTED_ABS=()
for path in "${PROTECTED_PATHS[@]}"; do
  if [[ "$path" == /* ]]; then
    PROTECTED_ABS+=("$(realpath -m "$REPO_ROOT$path")")
  else
    PROTECTED_ABS+=("$(realpath -m "$REPO_ROOT/$path")")
  fi
done

LOG_FILE="$REPO_ROOT/out/cleanup.log"
if [[ "$MODE" == "apply" ]]; then
  mkdir -p "$REPO_ROOT/out"
  touch "$LOG_FILE"
fi

while IFS= read -r line || [[ -n "$line" ]]; do
  trimmed="${line#"${line%%[![:space:]]*}"}"
  trimmed="${trimmed%"${trimmed##*[![:space:]]}"}"

  if [[ -z "$trimmed" ]]; then
    continue
  fi
  if [[ ${trimmed:0:1} == "#" ]]; then
    continue
  fi

  if [[ "$trimmed" == /* ]]; then
    target="$REPO_ROOT$trimmed"
  else
    target="$REPO_ROOT/$trimmed"
  fi
  target="$(realpath -m "$target")"

  if [[ "$target" == "$REPO_ROOT" ]]; then
    echo "Duke kapërcyer rrënjën e projektit: $trimmed" >&2
    continue
  fi

  if [[ "$target" != "$REPO_ROOT" && "${target#$REPO_ROOT/}" == "$target" ]]; then
    echo "Duke kapërcyer path jashtë projektit: $trimmed" >&2
    continue
  fi

  skip=false
  for protected in "${PROTECTED_ABS[@]}"; do
    if [[ "$target" == "$protected" || "$target" == "$protected"/* ]]; then
      echo "Duke kapërcyer path te mbrojtur: $trimmed"
      skip=true
      break
    fi
  done
  if [[ "$skip" == true ]]; then
    continue
  fi

  display_path="${target#$REPO_ROOT/}"
  if [[ "$display_path" == "$target" ]]; then
    display_path="$trimmed"
  fi

  if [[ "$MODE" == "dry-run" ]]; then
    if [[ -e "$target" || -L "$target" ]]; then
      echo "[DRY-RUN] Do fshihej: $display_path"
    else
      echo "[DRY-RUN] Do fshihej (mungon): $display_path"
    fi
  else
    if [[ -e "$target" || -L "$target" ]]; then
      rm -rf -- "$target"
      timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
      echo "[$timestamp] U fshi: $display_path" >> "$LOG_FILE"
      echo "U fshi: $display_path"
    else
      echo "U kapërcye (mungon): $display_path"
    fi
  fi

done < "$ALLOWLIST_FILE"

if [[ "$MODE" == "apply" ]]; then
  echo "Logu: $LOG_FILE"
fi
