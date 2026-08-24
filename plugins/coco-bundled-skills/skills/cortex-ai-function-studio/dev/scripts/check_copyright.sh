#!/usr/bin/env bash
# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

# check_copyright.sh — Verify that all shipped skill files contain the required
# 3-line copyright header in the correct comment style for their file type.
#
# Usage:
#   ./check_copyright.sh [SKILL_ROOT]
#
# SKILL_ROOT defaults to the directory containing this script's parent (../),
# i.e., cortex-ai-function-studio/.
#
# Exit codes:
#   0 — All files pass
#   1 — One or more files are missing or have an incorrect copyright header

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="${1:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

# --- Expected copyright text (content only, no comment delimiters) ----------
COPYRIGHT_LINE1="Copyright (c) 2026 Snowflake Inc. All rights reserved."
COPYRIGHT_LINE2="Licensed under the Snowflake Skills License."
COPYRIGHT_LINE3="Refer to the LICENSE file in the root of this repository for full terms."

# --- File types to always skip (no comment syntax or generated) --------------
SKIP_EXTENSIONS="json lock zip gz tar png jpg jpeg gif svg ico woff woff2 ttf eot pdf"

# --- Files and directories to always skip (generated, non-source) ------------
ALWAYS_SKIP_DIRS=".pytest_cache .ruff_cache __pycache__ .mypy_cache node_modules .git"
ALWAYS_SKIP_FILES="LICENSE .gitignore .gitattributes"
ALWAYS_SKIP_EXT_PATTERNS="log"

# --- Parse .skillignore to build exclusion list ------------------------------
build_exclusions() {
  local skillignore="$SKILL_ROOT/.skillignore"
  local -a excludes=()

  if [[ -f "$skillignore" ]]; then
    while IFS= read -r line; do
      # Skip comments and blank lines
      [[ "$line" =~ ^[[:space:]]*# ]] && continue
      [[ -z "${line// /}" ]] && continue
      excludes+=("$line")
    done < "$skillignore"
  fi

  # Always exclude .git and the scripts directory itself
  excludes+=(".git/")
  excludes+=("scripts/check_copyright.sh")

  printf '%s\n' "${excludes[@]}"
}

# --- Check if a path matches any exclusion pattern ---------------------------
is_excluded() {
  local relpath="$1"
  shift
  local -a exclusions=("$@")

  for pattern in "${exclusions[@]}"; do
    # Directory exclusion (ends with /)
    if [[ "$pattern" == */ ]]; then
      local dir_pattern="${pattern%/}"
      if [[ "$relpath" == "$dir_pattern"/* || "$relpath" == "$dir_pattern" ]]; then
        return 0
      fi
    # Exact file match
    elif [[ "$relpath" == "$pattern" ]]; then
      return 0
    # Glob pattern with path components
    elif [[ "$relpath" == $pattern ]]; then
      return 0
    fi
  done
  return 1
}

# --- Check if file extension should be skipped --------------------------------
should_skip_extension() {
  local file="$1"
  local ext="${file##*.}"
  local basename
  basename="$(basename "$file")"

  # Skip known non-source extensions
  for skip_ext in $SKIP_EXTENSIONS; do
    if [[ "$ext" == "$skip_ext" ]]; then
      return 0
    fi
  done

  # Skip log-like extensions
  for skip_pat in $ALWAYS_SKIP_EXT_PATTERNS; do
    if [[ "$ext" == "$skip_pat" ]]; then
      return 0
    fi
  done

  # Files with no extension that aren't special (like Makefile)
  if [[ "$ext" == "$basename" ]]; then
    # Allow known no-extension files
    case "$basename" in
      Makefile|Dockerfile) return 1 ;;
      *) return 0 ;;
    esac
  fi

  return 1
}

# --- Check if path is in an always-skipped directory or is an always-skipped file
should_skip_path() {
  local relpath="$1"
  local basename
  basename="$(basename "$relpath")"

  # Check always-skip directories
  for dir in $ALWAYS_SKIP_DIRS; do
    if [[ "$relpath" == "$dir"/* || "$relpath" == "$dir" ]]; then
      return 0
    fi
    # Also check nested occurrences (e.g., src/__pycache__)
    if [[ "$relpath" == *"/$dir"/* || "$relpath" == *"/$dir" ]]; then
      return 0
    fi
  done

  # Check always-skip filenames
  for skipfile in $ALWAYS_SKIP_FILES; do
    if [[ "$basename" == "$skipfile" ]]; then
      return 0
    fi
  done

  return 1
}

# --- Get the expected copyright lines for a given file extension --------------
# Returns the 3-line header with appropriate comment syntax.
get_expected_header() {
  local file="$1"
  local ext="${file##*.}"
  local basename
  basename="$(basename "$file")"

  # Handle no-extension files
  if [[ "$ext" == "$basename" ]]; then
    case "$basename" in
      Makefile|Dockerfile)
        echo "# $COPYRIGHT_LINE1"
        echo "# $COPYRIGHT_LINE2"
        echo "# $COPYRIGHT_LINE3"
        return
        ;;
    esac
  fi

  case "$ext" in
    py|yaml|yml|toml|sh|cfg)
      echo "# $COPYRIGHT_LINE1"
      echo "# $COPYRIGHT_LINE2"
      echo "# $COPYRIGHT_LINE3"
      ;;
    sql)
      echo "-- $COPYRIGHT_LINE1"
      echo "-- $COPYRIGHT_LINE2"
      echo "-- $COPYRIGHT_LINE3"
      ;;
    j2)
      # Jinja2 templates use {# ... #} block comments
      echo "{#${COPYRIGHT_LINE1}#}"
      echo "{#${COPYRIGHT_LINE2}#}"
      echo "{#${COPYRIGHT_LINE3}#}"
      ;;
    md|html)
      # HTML/Markdown use <!-- ... --> (may be multi-line or single per line)
      echo "<!-- $COPYRIGHT_LINE1"
      ;;
    js|ts)
      echo "// $COPYRIGHT_LINE1"
      echo "// $COPYRIGHT_LINE2"
      echo "// $COPYRIGHT_LINE3"
      ;;
    css)
      echo "/* $COPYRIGHT_LINE1"
      ;;
    *)
      # Default to hash-style
      echo "# $COPYRIGHT_LINE1"
      echo "# $COPYRIGHT_LINE2"
      echo "# $COPYRIGHT_LINE3"
      ;;
  esac
}

# --- Check a single file for the copyright header ----------------------------
# Looks within the first 10 lines (to allow for shebangs, frontmatter, etc.)
check_file() {
  local file="$1"
  local ext="${file##*.}"
  local basename
  basename="$(basename "$file")"

  # Skip binary files (contain null bytes)
  if file "$file" 2>/dev/null | grep -q "binary\|image\|executable"; then
    return 0
  fi

  # Read first 15 lines of the file
  local head_content
  head_content="$(head -n 15 "$file" 2>/dev/null)" || true

  if [[ -z "$head_content" ]]; then
    # Empty file — skip
    return 0
  fi

  # Determine what to look for based on file type
  # NOTE: Use "grep -qF -- PATTERN" to avoid patterns starting with "--" being
  # interpreted as grep options.
  case "$ext" in
    py|yaml|yml|toml|sh|cfg)
      if echo "$head_content" | grep -qF -- "# $COPYRIGHT_LINE1" &&
         echo "$head_content" | grep -qF -- "# $COPYRIGHT_LINE2" &&
         echo "$head_content" | grep -qF -- "# $COPYRIGHT_LINE3"; then
        return 0
      fi
      ;;
    sql)
      if echo "$head_content" | grep -qF -- "-- $COPYRIGHT_LINE1" &&
         echo "$head_content" | grep -qF -- "-- $COPYRIGHT_LINE2" &&
         echo "$head_content" | grep -qF -- "-- $COPYRIGHT_LINE3"; then
        return 0
      fi
      ;;
    j2)
      if echo "$head_content" | grep -qF -- "{#${COPYRIGHT_LINE1}#}" &&
         echo "$head_content" | grep -qF -- "{#${COPYRIGHT_LINE2}" &&
         echo "$head_content" | grep -qF -- "{#${COPYRIGHT_LINE3}"; then
        return 0
      fi
      ;;
    md|html)
      # For markdown/HTML, copyright can be in <!-- --> block (possibly multi-line)
      if echo "$head_content" | grep -qF -- "$COPYRIGHT_LINE1"; then
        return 0
      fi
      ;;
    js|ts)
      if echo "$head_content" | grep -qF -- "// $COPYRIGHT_LINE1" &&
         echo "$head_content" | grep -qF -- "// $COPYRIGHT_LINE2" &&
         echo "$head_content" | grep -qF -- "// $COPYRIGHT_LINE3"; then
        return 0
      fi
      ;;
    css)
      # CSS uses /* ... */ — just check the copyright text is present
      if echo "$head_content" | grep -qF -- "$COPYRIGHT_LINE1" &&
         echo "$head_content" | grep -qF -- "$COPYRIGHT_LINE2" &&
         echo "$head_content" | grep -qF -- "$COPYRIGHT_LINE3"; then
        return 0
      fi
      ;;
    *)
      # Default: check for hash-style or raw text
      if echo "$head_content" | grep -qF -- "$COPYRIGHT_LINE1" &&
         echo "$head_content" | grep -qF -- "$COPYRIGHT_LINE2" &&
         echo "$head_content" | grep -qF -- "$COPYRIGHT_LINE3"; then
        return 0
      fi
      ;;
  esac

  # Handle Makefile/Dockerfile (no-extension specials)
  if [[ "$ext" == "$basename" ]]; then
    case "$basename" in
      Makefile|Dockerfile)
        if echo "$head_content" | grep -qF -- "# $COPYRIGHT_LINE1" &&
           echo "$head_content" | grep -qF -- "# $COPYRIGHT_LINE2" &&
           echo "$head_content" | grep -qF -- "# $COPYRIGHT_LINE3"; then
          return 0
        fi
        ;;
    esac
  fi

  return 1
}

# --- Main --------------------------------------------------------------------
main() {
  local -a exclusions
  mapfile -t exclusions < <(build_exclusions)

  local failures=0
  local checked=0

  while IFS= read -r -d '' file; do
    local relpath="${file#"$SKILL_ROOT"/}"

    # Skip excluded paths (from .skillignore)
    if is_excluded "$relpath" "${exclusions[@]}"; then
      continue
    fi

    # Skip always-ignored directories and files
    if should_skip_path "$relpath"; then
      continue
    fi

    # Skip binary/uncommentable extensions
    if should_skip_extension "$file"; then
      continue
    fi

    checked=$((checked + 1))

    if ! check_file "$file"; then
      local ext="${file##*.}"
      echo "FAIL: $relpath"
      echo "      Expected copyright header (${ext} style):"
      while IFS= read -r line; do
        echo "        $line"
      done < <(get_expected_header "$file")
      echo ""
      failures=$((failures + 1))
    fi
  done < <(find "$SKILL_ROOT" -type f -print0 | sort -z)

  echo "---"
  echo "Checked $checked files, $failures failure(s)."

  if [[ $failures -gt 0 ]]; then
    echo ""
    echo "All shipped files must include the copyright header near the top."
    echo "See the expected formats above for each file type."
    exit 1
  fi

  echo "All files have correct copyright headers."
  exit 0
}

main
