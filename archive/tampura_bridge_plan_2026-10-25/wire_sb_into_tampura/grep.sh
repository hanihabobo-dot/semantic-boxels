#!/bin/bash
# Read-only helper: grep -n with a pattern over files under /root/tampura-work.
# Usage: grep.sh PATTERN FILE [FILE ...]
cd /root/tampura-work || exit 1
pat="$1"; shift
grep -n -E "$pat" "$@"
