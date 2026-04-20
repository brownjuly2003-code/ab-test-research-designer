from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.backend.app.config import get_settings
from app.backend.app.repository import ProjectRepository


def build_repository(db_path: Path, settings) -> ProjectRepository:
    return ProjectRepository(
        str(db_path),
        busy_timeout_ms=settings.sqlite_busy_timeout_ms,
        journal_mode=settings.sqlite_journal_mode,
        synchronous=settings.sqlite_synchronous,
        workspace_signing_key=settings.workspace_signing_key,
    )


def seed_fixture(repository: ProjectRepository) -> None:
    first_project = repository.create_project(
        {
            "project": {"project_name": "Fixture checkout"},
            "hypothesis": {"change_description": "Simplify checkout"},
            "setup": {"variants_count": 2},
            "metrics": {"metric_type": "binary"},
            "constraints": {},
            "additional_context": {},
        }
    )
    repository.update_project(
        first_project["id"],
        {
            "project": {"project_name": "Fixture checkout v2"},
            "hypothesis": {"change_description": "Simplify checkout further"},
            "setup": {"variants_count": 2},
            "metrics": {"metric_type": "binary"},
            "constraints": {},
            "additional_context": {},
        },
    )
    analyzed_project = repository.record_analysis(
        first_project["id"],
        {
            "calculations": {
                "calculation_summary": {"metric_type": "binary"},
                "results": {
                    "sample_size_per_variant": 100,
                    "total_sample_size": 200,
                    "estimated_duration_days": 10,
                },
                "warnings": [{"code": "LONG_DURATION"}],
            },
            "report": {"executive_summary": "Fixture summary"},
            "advice": {"available": False},
        },
    )
    if analyzed_project is None:
        raise RuntimeError("Failed to seed analysis history for fixture project")
    repository.record_export(
        first_project["id"],
        "markdown",
        analyzed_project["last_analysis_run_id"],
    )
    repository.create_project(
        {
            "project": {"project_name": "Fixture pricing"},
            "hypothesis": {"change_description": "Change pricing copy"},
            "setup": {"variants_count": 2},
            "metrics": {"metric_type": "binary"},
            "constraints": {},
            "additional_context": {},
        }
    )


def bundle_counts(bundle: dict) -> dict[str, int]:
    return {
        "projects": len(bundle.get("projects", [])),
        "analysis_runs": len(bundle.get("analysis_runs", [])),
        "export_events": len(bundle.get("export_events", [])),
        "project_revisions": len(bundle.get("project_revisions", [])),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", help="Existing SQLite database to export and verify.")
    parser.add_argument("--output", help="Optional path to write the exported workspace bundle JSON.")
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Use an ephemeral seeded SQLite fixture instead of an existing DB.",
    )
    args = parser.parse_args()

    settings = get_settings()

    artifact_dir = (
        ROOT_DIR
        / "archive"
        / "verify-workspace-backup"
        / f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)

    if args.fixture or not args.db_path:
        source_db = artifact_dir / "source.sqlite3"
        source_repository = build_repository(source_db, settings)
        seed_fixture(source_repository)
    else:
        source_db = Path(args.db_path)
        source_repository = build_repository(source_db, settings)

    bundle = source_repository.export_workspace()
    counts = bundle_counts(bundle)
    integrity = bundle.get("integrity")

    if not isinstance(integrity, dict):
        raise SystemExit("Workspace backup verification failed: integrity block is missing")
    if integrity.get("counts") != counts:
        raise SystemExit(
            f"Workspace backup verification failed: integrity counts mismatch {integrity.get('counts')} vs {counts}"
        )
    checksum = str(integrity.get("checksum_sha256") or "")
    if len(checksum) != 64:
        raise SystemExit("Workspace backup verification failed: checksum is missing or malformed")
    signature = str(integrity.get("signature_hmac_sha256") or "")
    if signature and len(signature) != 64:
        raise SystemExit("Workspace backup verification failed: signature is malformed")

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        output_path = artifact_dir / "workspace-backup.json"
    output_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    target_repository = build_repository(artifact_dir / "restored.sqlite3", settings)
    validation = target_repository.validate_workspace_bundle(bundle)
    import_summary = target_repository.import_workspace(bundle)
    restored_summary = target_repository.get_diagnostics_summary()

    expected_import_summary = {
        "status": "imported",
        "imported_projects": counts["projects"],
        "imported_analysis_runs": counts["analysis_runs"],
        "imported_export_events": counts["export_events"],
        "imported_project_revisions": counts["project_revisions"],
    }
    if import_summary != expected_import_summary:
        raise SystemExit(
            f"Workspace import summary mismatch: expected {expected_import_summary}, got {import_summary}"
        )

    restored_counts = {
        "projects": restored_summary["projects_total"],
        "analysis_runs": restored_summary["analysis_runs_total"],
        "export_events": restored_summary["export_events_total"],
        "project_revisions": restored_summary["project_revisions_total"],
    }
    if restored_counts != counts:
        raise SystemExit(f"Workspace backup verification failed: expected {counts}, got {restored_counts}")

    print(
        "Workspace backup verification passed:",
        json.dumps(
            {
                "artifacts": str(artifact_dir),
                "source_db": str(source_db),
                "counts": counts,
                "checksum_sha256": checksum,
                "signature_hmac_sha256": signature or None,
                "signature_verified": validation["signature_verified"],
            },
            ensure_ascii=True,
            sort_keys=True,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
