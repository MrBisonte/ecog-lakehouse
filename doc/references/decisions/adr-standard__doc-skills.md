# ADR standard

Source: doc-skills monorepo, `adr` skill.

- One decision per record. Two decisions in one discussion are two ADRs.
- A record with one option is an announcement, not a decision. Every ADR lists the alternatives, or states that none were considered and why.
- Numbered `ADR-NNNN`, next number taken from the directory.
- Status: `proposed`, `accepted`, `superseded by ADR-NNNN`, `deprecated`.
- Accepted records are immutable. Typos may be fixed; reasoning may not. A change of mind is a new ADR that supersedes the old one, which gets its status updated and nothing else.
- Sections: Context (forces, no solutions), Options considered (table with rejected because), Decision (present tense, one sentence then reasoning), Consequences (positive and negative; the negative ones are the valuable ones).
- Template: any file in `adr/`.
