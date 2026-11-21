---
pr: pending
branch: claude/fd-personal-links
---
FD-02 backend: a person's Home document accepts personal web links (name, https address, optional icon) that can be pinned to the dock, grid and widgets as link:<id>. Addresses that are not plain https are refused. Each person's links are private to them and the audit log records only that links changed. The Home contract in the OpenAPI spec now lists links. The dashboard Links section follows in a UI PR.
