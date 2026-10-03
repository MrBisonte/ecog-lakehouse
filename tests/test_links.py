"""Every relative markdown link resolves, and every repository path CLAUDE.md quotes exists."""

import itertools
import os
import re
from pathlib import Path
from urllib.parse import unquote

REPO = Path(__file__).resolve().parents[1]

# Links known broken in a file this change does not own, one line each: (file, target).
KNOWN_BROKEN: set[tuple[str, str]] = set()

LINK = re.compile(r"\[[^\]]*\]\(<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\)")
EXTERNAL = ("http://", "https://", "mailto:")
QUOTED_PATH = re.compile(r"`((?:doc|docs|sql|faults)/[^`\s]*)`")


def markdown_files() -> list[Path]:
    """Every .md file under the repository, hidden directories (.git, .venv, caches) skipped."""
    found = []
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        found += [Path(root) / f for f in files if f.endswith(".md")]
    return sorted(found)


def prose(text: str) -> str:
    """The text without fenced blocks and inline code, where brackets are not links."""
    out, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced:
            out.append(re.sub(r"`[^`]*`", "", line))
    return "\n".join(out)


def relative_targets(text: str) -> list[str]:
    """Link targets that point inside the repository, anchor and query removed."""
    targets = []
    for raw in LINK.findall(prose(text)):
        if raw.startswith(EXTERNAL) or raw.startswith("#"):
            continue
        targets.append(unquote(re.split(r"[#?]", raw)[0]))
    return targets


def expand(path: str) -> list[str]:
    """`faults/<a|d|f|g>/` names four directories; a path without a placeholder names one."""
    parts = re.split(r"<([^>]+)>", path)
    choices = [[p] if i % 2 == 0 else p.split("|") for i, p in enumerate(parts)]
    return ["".join(c) for c in itertools.product(*choices)]


def test_relative_targets_skip_external_anchors_and_code():
    text = "[a](x.md#s) [b](https://e.org) [c](#top) [d](mailto:m@e.org) `[e](no.md)`\n```\n[f](no.md)\n```"
    assert relative_targets(text) == ["x.md"]


def test_expand_placeholders():
    assert expand("faults/<a|d>/") == ["faults/a/", "faults/d/"]
    assert expand("doc/spec.md") == ["doc/spec.md"]


def test_every_relative_markdown_link_resolves():
    broken = []
    for md in markdown_files():
        rel = md.relative_to(REPO).as_posix()
        for target in relative_targets(md.read_text(encoding="utf-8")):
            if not (md.parent / target).exists() and (rel, target) not in KNOWN_BROKEN:
                broken.append(f"{rel} -> {target}")
    assert broken == []


def test_every_path_quoted_in_claude_md_exists():
    quoted = QUOTED_PATH.findall((REPO / "CLAUDE.md").read_text(encoding="utf-8"))
    assert quoted, "CLAUDE.md quotes no repository path; the pattern no longer matches"
    missing = [p for q in quoted for p in expand(q) if not (REPO / p).exists()]
    assert missing == []
