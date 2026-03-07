# Workspace Cleanup Archive

Archived on `2026-03-07`.

Contents:

- `docs/FILE_TREE.before-cleanup.md`: outdated project tree document kept for reference.
- `generated-test-dbs/`: temporary SQLite files produced by backend project API tests.
- `pytest-cache-files/`: transient pytest cache directories moved out of the project root when access allowed.

Reason:

- keep the active project tree focused on source, docs, and runtime assets;
- preserve old/generated artifacts without deleting them.
