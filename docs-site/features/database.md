# Database backends

The backend supports two storage modes:

- SQLite: default for local development, single-user runs, and Hugging Face demo deployments
- Postgres: optional for production deployments that need concurrent access, multiple instances, or database-native backup/replication

## Choosing a backend

Use SQLite when:

- one backend process owns the database file
- you want zero extra infrastructure
- startup/demo portability matters more than shared-write throughput

Use Postgres when:

- multiple workers or replicas must share the same workspace state
- you need connection pooling instead of file locking
- operational backup/restore already lives in your database platform

## Configuration

SQLite remains the default when `AB_DATABASE_URL` is empty. The backend computes the database path from the package location, so `AB_DB_PATH` only needs to be set if you want the file to live somewhere else, and the override must be an **absolute** path:

```bash
# Linux/macOS
export AB_DB_PATH=/var/lib/ab-test-research-designer/projects.sqlite3
# Windows
set AB_DB_PATH=C:\AB_TEST\data\projects.sqlite3
```

Switch to Postgres with:

```bash
set AB_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/abtest
set AB_DB_POOL_SIZE=10
```

## Operational notes

- Postgres schema creation happens automatically on startup
- SQLite snapshot sync is intentionally skipped for Postgres runtimes
- Workspace export/import APIs stay the same across both backends
- Existing SQLite databases are not modified unless you explicitly migrate them
