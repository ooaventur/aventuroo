#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Perdorimi: cleanup.sh [opsione] [allowlist]
  --dry-run            Tregon cfare do te fshihet pa fshire (default)
  --apply              Kryen fshirjen dhe logon ne out/cleanup.log
  --min-age-days N     Fshin vetem path-et qe jane te vjetra te pakten N dite
  allowlist            Rruga drejt cleanup-allowlist.txt (default: ne rrënjën e projektit)
USAGE
}

MODE="dry-run"
MIN_AGE_DAYS=0
ALLOWLIST_ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      MODE="dry-run"
      shift
      ;;
    --apply)
      MODE="apply"
      shift
      ;;
    --min-age-days)
      if [[ $# -lt 2 ]]; then
        echo "Mungon vlere per --min-age-days" >&2
        usage
        exit 1
      fi
      MIN_AGE_DAYS="$2"
      shift 2
      ;;
    --min-age-days=*)
      MIN_AGE_DAYS="${1#*=}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    *)
      ALLOWLIST_ARG="$1"
      shift
      break
      ;;
  esac
done

if [[ -n "$ALLOWLIST_ARG" && $# -gt 0 ]]; then
  echo "Argumente te tepërta: $*" >&2
  usage
  exit 1
fi

if ! [[ "$MIN_AGE_DAYS" =~ ^[0-9]+$ ]]; then
  echo "--min-age-days duhet te jete numer i plote >= 0" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ALLOWLIST_FILE="${ALLOWLIST_ARG:-$REPO_ROOT/cleanup-allowlist.txt}"

if [[ ! -f "$ALLOWLIST_FILE" ]]; then
  echo "Allowlist nuk u gjet: $ALLOWLIST_FILE" >&2
  exit 1
fi

check_min_age() {
  local target="$1"
  local min_age="$2"
  python3 - "$target" "$min_age" <<'PY'
import os
import sys
import time
from pathlib import Path


def newest_mtime(path: Path) -> float:
    try:
        stat_result = path.lstat()
    except FileNotFoundError:
        return float("nan")

    newest = stat_result.st_mtime
    if path.is_dir() and not path.is_symlink():
        for root, dirs, files in os.walk(path, followlinks=False):
            for name in files:
                candidate = Path(root, name)
                try:
                    mtime = candidate.lstat().st_mtime
                except FileNotFoundError:
                    continue
                if mtime > newest:
                    newest = mtime
            for name in dirs:
                candidate = Path(root, name)
                try:
                    mtime = candidate.lstat().st_mtime
                except FileNotFoundError:
                    continue
                if mtime > newest:
                    newest = mtime
    return newest


def main() -> int:
    path = Path(sys.argv[1])
    min_age = float(sys.argv[2])
    newest = newest_mtime(path)
    if newest != newest:  # NaN kontroll
        print("MISSING")
        return 2

    now = time.time()
    age_days = max(0.0, (now - newest) / 86400.0)
    threshold = now - min_age * 86400.0

    if newest <= threshold:
        print(f"ALLOW {age_days:.2f}")
        return 0

    print(f"SKIP {age_days:.2f}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
PY
}

# Lista e path-eve te mbrojtura (relative ndaj rrënjës se projektit)
PROTECTED_PATHS=(
  "/data"
  "/out/raw"
  "/scripts"
  "/.github"
  "/assets"
  "/netlify.toml"
  "/_headers"
  "/autopost"
  "/.eleventy.js"  # Konfigurim kryesor i ndërtimit
  "/README.md"      # Dokumentim rrënjësor
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

  nullglob_was_set=0
  if shopt -q nullglob; then
    nullglob_was_set=1
  fi
  dotglob_was_set=0
  if shopt -q dotglob; then
    dotglob_was_set=1
  fi

  shopt -s nullglob dotglob
  old_ifs=$IFS
  IFS=$'\n'
  candidates=( $target )
  IFS=$old_ifs
  if (( ${#candidates[@]} == 0 )); then
    candidates=( "$target" )
  fi
  if (( nullglob_was_set == 0 )); then
    shopt -u nullglob
  fi
  if (( dotglob_was_set == 0 )); then
    shopt -u dotglob
  fi

  for candidate in "${candidates[@]}"; do
    candidate_real="$(realpath -m "$candidate")"

    if [[ "$candidate_real" == "$REPO_ROOT" ]]; then
      echo "Duke kapërcyer rrënjën e projektit: $candidate_real" >&2
      continue
    fi

    if [[ "$candidate_real" != "$REPO_ROOT" && "${candidate_real#$REPO_ROOT/}" == "$candidate_real" ]]; then
      echo "Duke kapërcyer path jashtë projektit: $candidate_real" >&2
      continue
    fi

    skip=false
    for protected in "${PROTECTED_ABS[@]}"; do
      if [[ "$candidate_real" == "$protected" || "$candidate_real" == "$protected"/* ]]; then
        display_protected="${candidate_real#$REPO_ROOT/}"
        if [[ "$display_protected" == "$candidate_real" ]]; then
          display_protected="$candidate_real"
        fi
        echo "Duke kapërcyer path te mbrojtur: $display_protected"
        skip=true
        break
      fi
    done
    if [[ "$skip" == true ]]; then
      continue
    fi

    display_path="${candidate_real#$REPO_ROOT/}"
    if [[ "$display_path" == "$candidate_real" ]]; then
      display_path="$candidate_real"
    fi

    target_exists=false
    AGE_OUTPUT=""
    if [[ -e "$candidate_real" || -L "$candidate_real" ]]; then
      target_exists=true
      if (( MIN_AGE_DAYS > 0 )); then
        if AGE_OUTPUT="$(check_min_age "$candidate_real" "$MIN_AGE_DAYS")"; then
          AGE_STATUS=0
        else
          AGE_STATUS=$?
        fi
        if (( AGE_STATUS == 2 )); then
          echo "Duke kapërcyer (mungon gjate llogaritjes se moshes): $display_path"
          continue
        fi
        if (( AGE_STATUS != 0 )); then
          age_info="${AGE_OUTPUT#SKIP }"
          if [[ "$age_info" != "$AGE_OUTPUT" ]]; then
            echo "Duke kapërcyer (më i ri se $MIN_AGE_DAYS ditë, ≈${age_info} ditë): $display_path"
          else
            echo "Duke kapërcyer (më i ri se $MIN_AGE_DAYS ditë): $display_path"
          fi
          continue
        fi
      fi
    fi

    if [[ "$MODE" == "dry-run" ]]; then
      if [[ "$target_exists" == true ]]; then
        if (( MIN_AGE_DAYS > 0 )) && [[ -n "$AGE_OUTPUT" ]]; then
          age_info="${AGE_OUTPUT#ALLOW }"
          echo "[DRY-RUN] Do fshihej (mosha ≈${age_info} ditë): $display_path"
        else
          echo "[DRY-RUN] Do fshihej: $display_path"
        fi
      else
        echo "[DRY-RUN] Do fshihej (mungon): $display_path"
      fi
    else
      if [[ "$target_exists" == true ]]; then
        rm -rf -- "$candidate_real"
        timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
        if (( MIN_AGE_DAYS > 0 )) && [[ -n "$AGE_OUTPUT" ]]; then
          age_info="${AGE_OUTPUT#ALLOW }"
          echo "[$timestamp] U fshi (mosha ≈${age_info} ditë): $display_path" >> "$LOG_FILE"
          echo "U fshi (mosha ≈${age_info} ditë): $display_path"
        else
          echo "[$timestamp] U fshi: $display_path" >> "$LOG_FILE"
          echo "U fshi: $display_path"
        fi
      else
        echo "U kapërcye (mungon): $display_path"
      fi
    fi
  done

done < "$ALLOWLIST_FILE"

if [[ "$MODE" == "apply" ]]; then
  echo "Logu: $LOG_FILE"
fi
