#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: check-single-line-commit.sh <commit_msg_file>"
  exit 1
fi

msg_file="$1"

if [ ! -f "$msg_file" ]; then
  echo "Commit message file not found: $msg_file"
  exit 1
fi

# Keep non-empty, non-comment lines.
content_lines="$(grep -Ev '^[[:space:]]*($|#)' "$msg_file" || true)"

if [ -z "$content_lines" ]; then
  echo "Commit message must not be empty."
  exit 1
fi

line_count="$(printf "%s\n" "$content_lines" | wc -l | tr -d '[:space:]')"

if [ "$line_count" -gt 1 ]; then
  echo "Commit message must be single-line (no multiline body)."
  exit 1
fi
