#!/bin/bash
# Review check: common shell variants of "sha256 over git ls-files", to see
# which one gives the prefixes ARGUMENT.md 4.5 quotes. Read only.
for r in tampura tampura_environments; do
  cd /root/tampura-work/$r || exit 1
  a=$(git ls-files -z | xargs -0 sha256sum | sha256sum | cut -c1-16)
  b=$(git ls-files | sort | xargs sha256sum 2>/dev/null | sha256sum | cut -c1-16)
  c=$(git ls-files -z | xargs -0 cat | sha256sum | cut -c1-16)
  echo "$r: ls-files|xargs sha256sum|sha256sum=$a  sorted=$b  cat=$c"
done
