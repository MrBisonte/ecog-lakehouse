# Architecture conventions

Source: the author's standing architecture conventions, applied across personal projects.

| Convention | Rule | Applied here |
|---|---|---|
| Guideline | Data mesh principles (datamesh-architecture.com) are the default when no direct instruction exists | Domain ownership of Gold marts; contracts per dataset |
| Contracts | Open Data Contract Standard (ODCS), v3 | `contracts/*.yaml` |
| Regulation | GDPR and other applicable regulation are design inputs, not review items | `governance/requirements.csv` |
| Layers | Bronze, Silver, Gold, with documentation at conceptual, logical and physical level | `doc/spec.md` section 3 |
| SQL | SQL over ORM, always | `sql/` plus a 20-line renderer |
| Interchange | Apache Arrow in pipeline contexts; Parquet at rest; Hive partitioning on object storage | All layers |
| Storage | Minimise storage size; partition pruning is a correctness invariant, not an optimisation | Sorted files, row group size in the spec |
| Code | OOP principles and known patterns only where they pay; known algorithms chosen for performance; elegance counts | Adapter registry in `convert_mat.py` is the one pattern in use |
| Commits | Conventional Commits v1.0.0 | Enforced by review |
| Diagrams | Mermaid before prose, high level then logical then physical; tables over prose for comparisons | Every doc in `doc/` |
| Decisions | Every significant decision gets an ADR | `adr/` |
