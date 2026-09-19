# Reference documentation standard

Source: doc-skills monorepo, `reference-docs` skill (v0.6.1), with its deterministic linter copied to `scripts/lint_doc.py`.

## Style

- Plain, direct, example driven, in the manner of classic database manuals.
- One sentence states one fact. Present tense. No marketing words.
- Commas, never em or en dashes.
- Define an acronym on first use or in a terms table.
- Tables over prose for anything with more than two attributes.
- Every schema is a table of column name and type, followed by one line per column: meaning, nullability, references.
- Every claim of behaviour has an example that can be run.

## Structure of a reference page

1. Scope, one paragraph.
2. Definitions, when needed.
3. Specification, as tables.
4. Examples, runnable.
5. Limits and errors.

## Linter

`python3 scripts/lint_doc.py <files>` fails on dashes and filler words and lists acronym candidates. It runs on every commit through `make lint`.
