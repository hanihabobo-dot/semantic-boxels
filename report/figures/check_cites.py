#!/usr/bin/env python3
"""Checks of the report (the second of the brief's three checks).

1. Every \\cite key of the report is found in one of the two bibliography files
   (../thesis/resources/references.bib and resources/report_extra.bib).
2. Every source tag (\\BF{n}, \\PW{n}, \\TK{n}, \\ID{label}{text}) used in the text
   has its row (\\isrcrow{label}...) in chapters/appendix-sources.tex, and every row
   is used by at least one tag.
3. The style rules: no em dash, no triple hyphen, no double hyphen in prose, never
   the word "faithful", no "orthogonal", no gendered pronoun for a person (their
   pronouns are not stated anywhere: write the name).
4. Every new entry of report_extra.bib has a row in the citation record
   (tracks/report/CITATIONS.md).

Run from the report folder:  python -I figures/check_cites.py
Exit code 0 when everything passes, 1 otherwise.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # report/
REPO = ROOT.parent
THESIS_BIB = REPO / "thesis" / "resources" / "references.bib"
EXTRA_BIB = ROOT / "resources" / "report_extra.bib"
CITATIONS = (REPO / "archive" / "tampura_bridge_plan_2026-10-25" / "tracks" /
             "report" / "CITATIONS.md")
APPENDIX = ROOT / "chapters" / "appendix-sources.tex"

SOURCES = [ROOT / "main.tex"] + sorted((ROOT / "chapters").glob("*.tex")) + \
    sorted((ROOT / "resources").glob("*.tex"))


def strip_comments(text):
    out = []
    for line in text.splitlines():
        # a percent sign that is not escaped starts a comment
        m = re.search(r"(?<!\\)%", line)
        out.append(line[:m.start()] if m else line)
    return "\n".join(out)


def bib_keys(path):
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", text))


def main():
    problems = []
    keys = bib_keys(THESIS_BIB) | bib_keys(EXTRA_BIB)
    extra_keys = bib_keys(EXTRA_BIB)

    cite_keys = {}
    tags = {}          # row label -> list of files using it
    for f in SOURCES:
        if f == APPENDIX:
            continue
        text = strip_comments(f.read_text(encoding="utf-8"))
        for m in re.finditer(r"\\(?:cite|citep|citet|parencite|textcite|autocite)"
                             r"\*?(?:\[[^\]]*\])*\{([^}]*)\}", text):
            for k in m.group(1).split(","):
                cite_keys.setdefault(k.strip(), []).append(f.name)
        for m in re.finditer(r"\\BF\{(\d+)\}", text):
            tags.setdefault("BF" + m.group(1), []).append(f.name)
        for m in re.finditer(r"\\PW\{(\d+)\}", text):
            tags.setdefault("P" + m.group(1), []).append(f.name)
        for m in re.finditer(r"\\TK\{(\d+)\}", text):
            tags.setdefault("TK" + m.group(1), []).append(f.name)
        for m in re.finditer(r"\\ID\{([^}]*)\}\{", text):
            tags.setdefault(m.group(1), []).append(f.name)

    print("== citations ==")
    for k in sorted(cite_keys):
        status = "ok" if k in keys else "MISSING"
        where = "report_extra.bib" if k in extra_keys else (
            "thesis references.bib" if k in keys else "-")
        print(f"  {k:28s} {status:8s} {where:24s} used in {sorted(set(cite_keys[k]))}")
        if k not in keys:
            problems.append(f"cite key {k} is in no bibliography file")

    print("== new bibliography entries and the citation record ==")
    cit_text = CITATIONS.read_text(encoding="utf-8") if CITATIONS.exists() else ""
    for k in sorted(extra_keys):
        has_row = ("`%s`" % k) in cit_text
        print(f"  {k:28s} row in CITATIONS.md: {'yes' if has_row else 'NO'}")
        if not has_row:
            problems.append(f"{k} is in report_extra.bib without a CITATIONS.md row")
        if k not in cite_keys:
            print(f"     (note: {k} is not cited in the text)")

    print("== source tags and the rows of Appendix B ==")
    rows = set()
    if APPENDIX.exists():
        atext = strip_comments(APPENDIX.read_text(encoding="utf-8"))
        rows = set(re.findall(r"\\isrcrow\{([^}]*)\}", atext))
    for t in sorted(tags, key=lambda s: (re.sub(r"\d+", "", s),
                                          int(re.sub(r"\D", "", s) or 0), s)):
        status = "ok" if t in rows else "NO ROW"
        print(f"  {t:14s} {status:7s} used in {sorted(set(tags[t]))}")
        if t not in rows:
            problems.append(f"tag {t} has no row in appendix-sources.tex")
    for r in sorted(rows - set(tags)):
        print(f"  {r:14s} ROW NOT USED")
        problems.append(f"row {r} of appendix-sources.tex is used by no tag")

    print("== style rules ==")
    for f in SOURCES:
        text = strip_comments(f.read_text(encoding="utf-8"))
        for n, line in enumerate(text.splitlines(), 1):
            for pat, label in ((r"\u2014", "em dash"), (r"---", "triple hyphen"),
                               (r"(?<!-)--(?!-)", "double hyphen"),
                               (r"(?i)faithful", "the word faithful"),
                               (r"(?i)orthogonal", "the word orthogonal"),
                               (r"(?i)\b(?:he|him|his|himself|she|her|hers|herself)\b",
                                "gendered pronoun (use the name; a verbatim quote needs a look)")):
                if re.search(pat, line):
                    problems.append(f"{f.name}:{n}: {label}: {line.strip()[:70]}")
                    print(f"  {f.name}:{n}: {label}")

    print("== result ==")
    if problems:
        for p in problems:
            print("  PROBLEM:", p)
        return 1
    print("  all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
