#!/usr/bin/env python3
"""lint_doc.py - mechanical style checks for the reference-docs house style.

Checks only what a machine can decide with certainty: em/en dashes, filler and
marketing words, and undefined-acronym candidates. Judgment (missing specs,
weak examples, severity calls) stays with the model and the self-check.

Usage:
    python lint_doc.py <file.md> [<file.md> ...]

Exit code:
    0  no dash or filler issues found
    1  at least one dash or filler issue found (acronym candidates are advisory)

The word lists mirror references/style.md. Keep them in sync.
"""

import re
import sys

# Filler and marketing words. Phrases are matched as-is; single words on word
# boundaries. Mirrors the banned list in references/style.md.
BANNED = [
    "utilize", "utilizes", "utilized", "utilizing",
    "leverage", "leverages", "leveraged",
    "seamless", "seamlessly",
    "robust", "powerful", "comprehensive", "rich", "flexible",
    "modular", "complex", "high-security",
    "simply", "just", "easily", "of course",
    "essentially", "basically", "fundamentally",
    "delve", "dive into", "explore",
    "state-of-the-art", "cutting-edge", "modern",
    "in order to", "designed to", "aims to", "aim to",
    "facilitate", "facilitates",
    "it is important to note", "it should be noted",
    "a variety of", "a number of",
    "allows you to", "enables you to",
]

# Acronyms that are common enough in this domain to assume the reader knows them.
# Anything outside this set is reported as a candidate to check for a definition.
KNOWN_ACRONYMS = {
    "SQL", "API", "HTTP", "HTTPS", "JSON", "CSV", "TSV", "URL", "URN", "ID",
    "OAUTH2", "ADR", "CI", "CD", "TUI", "CLI", "DDL", "DML", "NULL", "S3",
    "AWS", "GCS", "IAM", "OS", "C", "SRE", "OTEL", "OTLP", "PR", "TODO",
    "UUID", "PK", "FK", "NDJSON", "HLL", "HLAD", "PII", "ANSI", "GIN",
    "README", "MD", "PDF", "HTML", "F1", "F5", "M",
    # units and markdown callout keywords (not acronyms to define)
    "GB", "MB", "KB", "TB", "PB", "MS", "NS", "B",
    "NOTE", "WARNING", "TIP", "IMPORTANT", "CAUTION",
}


def strip_code(lines):
    """Blank out fenced and inline code so prose checks do not fire on
    identifiers, flags, or SQL keywords. Line count is preserved so reported
    line numbers stay correct."""
    out = []
    in_fence = False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append("")  # the fence line itself carries no prose
            continue
        if in_fence:
            out.append("")
            continue
        # blank inline `code` spans, preserving length for column accuracy
        out.append(re.sub(r"`[^`]*`", lambda m: " " * len(m.group(0)), line))
    return out


def check_dashes(prose):
    hits = []
    for i, line in enumerate(prose, 1):
        for m in re.finditer(r"[\u2014\u2013]", line):  # em dash, en dash
            hits.append((i, m.start() + 1, line.strip()))
    return hits


def check_banned(prose):
    hits = []
    # longer phrases first so "in order to" wins over a stray "to"
    patterns = sorted(BANNED, key=len, reverse=True)
    for i, line in enumerate(prose, 1):
        low = line.lower()
        for word in patterns:
            if " " in word or "-" in word:
                pat = re.escape(word)
            else:
                pat = r"\b" + re.escape(word) + r"\b"
            for m in re.finditer(pat, low):
                hits.append((i, word, line.strip()))
    return hits


def check_acronyms(prose):
    """Report all-caps tokens not in the known set, with first-seen line.
    Advisory only: the model decides whether each is defined nearby."""
    seen = {}
    for i, line in enumerate(prose, 1):
        for m in re.finditer(r"\b([A-Z][A-Z0-9]{1,})\b", line):
            tok = m.group(1)
            if tok.upper() in KNOWN_ACRONYMS:
                continue
            if len(tok) > 5:  # long all-caps tokens are filenames or SHOUTING, not acronyms
                continue
            seen.setdefault(tok, i)
    return seen


def lint(path):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    prose = strip_code(lines)

    dashes = check_dashes(prose)
    banned = check_banned(prose)
    acronyms = check_acronyms(prose)

    print(f"\n=== {path} ===")
    print(f"{'check':<22}{'count':>6}")
    print(f"{'-'*28}")
    print(f"{'em/en dashes':<22}{len(dashes):>6}")
    print(f"{'filler/marketing':<22}{len(banned):>6}")
    print(f"{'acronym candidates':<22}{len(acronyms):>6} (advisory)")

    if dashes:
        print("\nem/en dashes (house rule: none):")
        for ln, col, text in dashes:
            print(f"  L{ln}:{col}  {text[:90]}")

    if banned:
        print("\nfiller / marketing words:")
        # group by word
        by_word = {}
        for ln, word, text in banned:
            by_word.setdefault(word, []).append(ln)
        for word in sorted(by_word, key=lambda w: -len(by_word[w])):
            lns = ", ".join(f"L{n}" for n in by_word[word])
            print(f"  {word:<22} x{len(by_word[word]):<3} ({lns})")

    if acronyms:
        print("\nacronym candidates (confirm each is defined on first use):")
        for tok, ln in sorted(acronyms.items(), key=lambda kv: kv[1]):
            print(f"  L{ln:<5} {tok}")

    fail = bool(dashes or banned)
    print(f"\nresult: {'FAIL' if fail else 'pass'} "
          f"({len(dashes)} dashes, {len(banned)} filler)\n")
    return fail


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    any_fail = False
    for path in argv[1:]:
        try:
            any_fail |= lint(path)
        except FileNotFoundError:
            print(f"not found: {path}", file=sys.stderr)
            any_fail = True
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
