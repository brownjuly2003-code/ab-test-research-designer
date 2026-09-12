from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

from app.backend.app.evidence.abx import (
    BUNDLE_SUFFIX,
    AbxError,
    inspect_bundle,
    pack_bundle,
    verify_bundle,
    verify_logical_bundle,
)
from app.backend.app.redaction import mask_inline_credentials

if TYPE_CHECKING:
    from app.backend.app.evidence.decisions import HumanVerdict
    from app.backend.app.evidence.pilot_records import PilotOutcome, PilotReuseKind
    from app.backend.app.evidence.runs import CompletedEvidenceRun
    from app.backend.app.repository import ProjectRepository

# Only `abx` is imported here, because verifying a bundle is what this command
# line is for. Everything a persisted run needs -- settings, the repository,
# the pipeline, and DuckDB, psycopg and numpy behind them -- is imported inside
# the handler that needs it. Someone checking a bundle a colleague emailed them
# should wait for a ZIP and a few digests, not for a query engine that will
# never open a file.

_ARTIFACT_ROOT_HELP = (
    "Artifact tree for persisted runs (default: $AB_ARTIFACT_ROOT, else .trialmark/artifacts)."
)


def _artifact_root(explicit: Path | None) -> Path:
    """The artifact tree to read and write, defaulting to the one the API serves.

    A relative default resolved per call site is what made a successful CLI run
    invisible to an API server started from another directory. `Settings` resolves
    `AB_ARTIFACT_ROOT` once, absolutely, so both sides land in the same tree; an
    explicit `--artifact-root` still wins, for the operator holding two of them.
    """
    if explicit is not None:
        return explicit
    from app.backend.app.config import get_settings

    return get_settings().artifact_root


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trialmark",
        description="Run protocols and manage verifiable Trialmark bundles.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    pack = subcommands.add_parser(
        "pack",
        help="Pack a logical Trialmark directory or a persisted completed run.",
    )
    pack_source = pack.add_mutually_exclusive_group(required=True)
    pack_source.add_argument("source", type=Path, nargs="?")
    pack_source.add_argument("--run", dest="run_id", metavar="RUN_ID")
    pack.add_argument("--artifact-root", type=Path, help=_ARTIFACT_ROOT_HELP)
    pack.add_argument("--out", type=Path, required=True, dest="output")

    verify = subcommands.add_parser("verify", help="Verify a Trialmark archive without extracting it.")
    verify.add_argument("archive", type=Path)
    verify.add_argument("--offline", action="store_true", help="Assert offline operation (always enforced).")
    verify.add_argument("--policy", choices=("strict",), default="strict")

    inspect = subcommands.add_parser("inspect", help="Inspect Trialmark identity and artifact roles.")
    inspect.add_argument("archive", type=Path)
    inspect.add_argument("--format", choices=("json", "summary"), default="json")

    run = subcommands.add_parser("run", help="Run and persist a frozen protocol.")
    run.add_argument("--protocol", type=Path, required=True)
    run.add_argument("--source", type=Path, required=True)
    run.add_argument("--actor")
    run.add_argument("--artifact-root", type=Path, help=_ARTIFACT_ROOT_HELP)
    run.add_argument("--out", type=Path, required=True, dest="output")

    decide = subcommands.add_parser("decide", help="Record an append-only human decision.")
    decide.add_argument("--run", required=True, dest="run_id", metavar="RUN_ID")
    decide.add_argument("--verdict", choices=("ship", "hold", "stop"), required=True)
    decide.add_argument("--rationale", required=True)
    decide.add_argument("--actor")
    decide.add_argument(
        "--role",
        help=(
            "Approval role to decide under. Must be listed in the frozen "
            "protocol policy. Recorded as role_source=asserted, because nothing "
            "here verifies the claim. Omitted, the policy's first role applies "
            "and the decision records role_source=policy_default."
        ),
    )
    decide.add_argument("--artifact-root", type=Path, help=_ARTIFACT_ROOT_HELP)
    decide.add_argument("--out", type=Path, required=True, dest="output")

    runs = subcommands.add_parser("runs", help="Inspect persisted runs.")
    run_commands = runs.add_subparsers(dest="runs_command", required=True)
    runs_list = run_commands.add_parser("list", help="List persisted runs.")
    runs_list.add_argument("--artifact-root", type=Path, help=_ARTIFACT_ROOT_HELP)

    pilot_sessions = subcommands.add_parser(
        "pilot-session",
        help="Create or validate a privacy-safe external pilot record.",
    )
    pilot_commands = pilot_sessions.add_subparsers(
        dest="pilot_command",
        required=True,
    )
    pilot_create = pilot_commands.add_parser(
        "create",
        help="Create a record from an observed external pilot session.",
    )
    pilot_create.add_argument("--participant-ref", required=True)
    pilot_create.add_argument("--source-ready-at", required=True)
    pilot_create.add_argument(
        "--outcome",
        choices=("completed", "incomplete"),
        required=True,
    )
    pilot_create.add_argument("--bundle-ready-at")
    pilot_create.add_argument("--bundle", type=Path)
    pilot_create.add_argument(
        "--reuse-kind",
        choices=("second_run", "evidence_reopen"),
    )
    pilot_create.add_argument("--reuse-at")
    pilot_create.add_argument("--out", type=Path, required=True, dest="output")

    pilot_validate = pilot_commands.add_parser(
        "validate",
        help="Validate a canonical external pilot record.",
    )
    pilot_validate.add_argument("record", type=Path)

    sources = subcommands.add_parser(
        "source",
        help="Check a practitioner source against a frozen protocol.",
    )
    source_commands = sources.add_subparsers(dest="source_command", required=True)
    source_validate = source_commands.add_parser(
        "validate",
        help="Pre-flight one aggregate CSV. Writes nothing and packs nothing.",
    )
    source_validate.add_argument("--protocol", type=Path, required=True)
    source_validate.add_argument("--source", type=Path, required=True)

    gate3 = subcommands.add_parser(
        "gate3",
        help="Aggregate validated pilot records into the Gate 3 decision.",
    )
    gate3.add_argument(
        "--records",
        type=Path,
        required=True,
        help=(
            "Directory of canonical <date>-<anon>.md pilot records. Every .md "
            "file in it must be one; anything else is an error, not a skip."
        ),
    )
    gate3.add_argument(
        "--out",
        type=Path,
        dest="output",
        help=(
            "Write the rendered Markdown report here. Re-running over an "
            "unchanged cohort produces identical bytes."
        ),
    )
    return parser


def _print_json(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _print_summary(value: dict[str, Any]) -> None:
    roles = ", ".join(f"{role}={count}" for role, count in value["roles"].items()) or "none"
    print(f"Trialmark {value['abx_version'] or 'unknown'}: {'valid' if value['valid'] else 'invalid'}")
    print(f"bundle_id: {value['bundle_id'] or 'unavailable'}")
    print(f"run_id: {value['run_id'] or 'unavailable'}")
    print(f"artifacts: {value['artifact_count']} ({roles})")
    raw_bindings = value.get("unbound_bindings")
    if raw_bindings is None:
        print("unbound_bindings: not_checked")
    else:
        bindings = [str(path) for path in raw_bindings]
        if bindings:
            print(f"unbound_bindings: {len(bindings)} ({', '.join(bindings)})")
        else:
            print("unbound_bindings: 0")


def _print_error(code: str, exc: BaseException) -> None:
    _print_json(
        {
            "valid": False,
            "error": {
                "code": code,
                "message": mask_inline_credentials(str(exc)),
            },
        }
    )


def _create_repository() -> ProjectRepository:
    from app.backend.app.config import get_settings
    from app.backend.app.repository import ProjectRepository

    settings = get_settings()
    return ProjectRepository(
        settings.database_url,
        busy_timeout_ms=settings.sqlite_busy_timeout_ms,
        journal_mode=settings.sqlite_journal_mode,
        synchronous=settings.sqlite_synchronous,
        workspace_signing_key=settings.workspace_signing_key,
        pool_size=settings.db_pool_size,
    )


def _publish_persisted_run(
    *,
    run_id: str,
    artifact_root: Path,
    destination: Path,
) -> dict[str, Any]:
    from app.backend.app.evidence.run_abx import publish_completed_run_abx

    repository = _create_repository()
    try:
        run_store = repository.create_evidence_run_store(artifact_root)
        return publish_completed_run_abx(
            run_store,
            run_id=run_id,
            destination=destination,
        )
    finally:
        repository.close()


def _resolve_principal(actor: str | None) -> str:
    return actor if actor is not None else os.environ.get("USER") or "local-operator"


def _run_persisted_protocol(
    *,
    protocol: Path,
    source: Path,
    actor: str | None,
    artifact_root: Path,
    destination: Path,
) -> dict[str, Any]:
    from app.backend.app.evidence.lifecycle_store import LifecycleEvidenceRunStore
    from app.backend.app.evidence.pipeline import run_protocol
    from app.backend.app.evidence.protocol_io import freeze, load_protocol
    from app.backend.app.evidence.run_abx import publish_completed_run_abx

    frozen = freeze(load_protocol(protocol))
    repository = _create_repository()
    try:
        run_store = LifecycleEvidenceRunStore(repository, artifact_root)
        run = run_protocol(
            frozen,
            source,
            principal=_resolve_principal(actor),
            out_store=run_store,
        )
        result = publish_completed_run_abx(
            run_store,
            run_id=run.run_id,
            destination=destination,
        )
        run_store.complete(
            run,
            bundle_id=cast(str, result["bundle_id"]),
            artifact_ref=str(destination.resolve()),
        )
        return result
    finally:
        repository.close()


def _record_persisted_decision(
    *,
    run_id: str,
    verdict: HumanVerdict,
    rationale: str,
    actor: str | None,
    role: str | None,
    artifact_root: Path,
    destination: Path,
) -> dict[str, Any]:
    from app.backend.app.evidence.decisions import (
        AssertedPrincipal,
        record_human_decision,
    )
    from app.backend.app.evidence.lifecycle_store import LifecycleEvidenceRunStore
    from app.backend.app.evidence.run_abx import publish_completed_run_abx

    repository = _create_repository()
    try:
        run_store = LifecycleEvidenceRunStore(repository, artifact_root)
        run = record_human_decision(
            run_id,
            AssertedPrincipal(actor_ref=_resolve_principal(actor), role=role),
            verdict,
            rationale,
            out_store=run_store,
        )
        result = publish_completed_run_abx(
            run_store,
            run_id=run.run_id,
            destination=destination,
        )
        run_store.complete(
            run,
            bundle_id=cast(str, result["bundle_id"]),
            artifact_ref=str(destination.resolve()),
        )
        return result
    finally:
        repository.close()


def _summarize_run(run: CompletedEvidenceRun) -> dict[str, Any]:
    from app.backend.app.evidence.run_abx import (
        materialize_completed_run_logical_abx,
    )

    logical = materialize_completed_run_logical_abx(run)
    verification = verify_logical_bundle(
        logical.manifest_payload,
        tuple((member.path, member.payload) for member in logical.members[1:]),
    )
    return {
        "run_id": run.run_id,
        "bundle_id": logical.bundle_id,
        "verdicts": verification["verdicts"],
    }


def _list_persisted_runs(artifact_root: Path) -> dict[str, Any]:
    from app.backend.app.evidence.lifecycle_store import LifecycleEvidenceRunStore
    from app.backend.app.evidence.run_abx import EvidenceRunNotFoundError

    repository = _create_repository()
    try:
        run_store = LifecycleEvidenceRunStore(repository, artifact_root)
        runs = []
        for run_id in run_store.list_run_ids():
            run = run_store.get(run_id)
            if run is None:
                raise EvidenceRunNotFoundError(
                    f"completed evidence run not found: {run_id}"
                )
            runs.append(_summarize_run(run))
        return {"runs": runs}
    finally:
        repository.close()


def _require_bundle_suffix(parser: argparse.ArgumentParser, path: Path) -> None:
    if path.suffix.lower() != BUNDLE_SUFFIX:
        parser.error(f"bundle path must use the {BUNDLE_SUFFIX} suffix")


# (module, exception attribute, envelope code) in the order the `except` arms
# used to run in. Nothing here is imported in order to match an error: an
# exception can only come from a module that is already loaded, so a missing
# `sys.modules` entry is proof this is not that error.
_ERROR_CODES: Final = (
    ("app.backend.app.evidence.run_abx", "EvidenceRunNotFoundError", "run_not_found"),
    (
        "app.backend.app.evidence.sql_run_store",
        "EvidenceRunStoreCorruptionError",
        "run_store_error",
    ),
    (
        "app.backend.app.evidence.sql_run_store",
        "EvidenceRunSchemaError",
        "run_store_error",
    ),
    ("app.backend.app.evidence.run_abx", "EvidenceRunBundleError", "pack_failed"),
    (
        "app.backend.app.evidence.decisions",
        "RoleNotPermittedError",
        "role_not_permitted",
    ),
    (
        "app.backend.app.evidence.decisions",
        "ApprovalQuorumUnmetError",
        "approval_quorum_unmet",
    ),
    (
        "app.backend.app.evidence.binary_aggregate",
        "BinaryAggregateValidationError",
        "source_invalid",
    ),
    (
        "app.backend.app.evidence.pilot_records",
        "PilotRecordValidationError",
        "pilot_record_error",
    ),
    ("app.backend.app.evidence.gate3", "Gate3Error", "gate3_error"),
)


def _deferred_error_code(exc: BaseException) -> str | None:
    """The envelope code for an error raised by a lazily imported module."""

    for module_name, attribute, code in _ERROR_CODES:
        module = sys.modules.get(module_name)
        if module is None:
            continue
        error_type: object = getattr(module, attribute, None)
        if isinstance(error_type, type) and isinstance(exc, error_type):
            return code
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "pack":
        # `--run` no longer needs an explicit root: it falls back to the configured
        # one, which is the same tree the API serves. Passing it with a directory
        # source is still a mistake -- that path packs a logical directory and
        # never touches the persisted store.
        if args.source is not None and args.artifact_root is not None:
            parser.error("--artifact-root can only be used with --run")
        _require_bundle_suffix(parser, args.output)
    elif args.command in {"run", "decide"}:
        _require_bundle_suffix(parser, args.output)

    persisted_command = args.command in {"run", "decide", "runs"} or (
        args.command == "pack" and args.run_id is not None
    )
    # `source validate` opens no store, but a practitioner pointing it at a
    # broken protocol wants the JSON envelope every other command gives them,
    # not a traceback.
    reports_configuration_errors = persisted_command or args.command == "source"

    try:
        if args.command == "pack":
            if args.run_id is None:
                result = pack_bundle(args.source, args.output)
            else:
                if os.path.lexists(args.output):
                    raise AbxError(f"destination already exists: {args.output}")
                result = _publish_persisted_run(
                    run_id=args.run_id,
                    artifact_root=_artifact_root(args.artifact_root),
                    destination=args.output,
                )
        elif args.command == "run":
            if os.path.lexists(args.output):
                raise AbxError(f"destination already exists: {args.output}")
            result = _run_persisted_protocol(
                protocol=args.protocol,
                source=args.source,
                actor=args.actor,
                artifact_root=_artifact_root(args.artifact_root),
                destination=args.output,
            )
        elif args.command == "decide":
            if os.path.lexists(args.output):
                raise AbxError(f"destination already exists: {args.output}")
            result = _record_persisted_decision(
                run_id=args.run_id,
                verdict=cast("HumanVerdict", args.verdict),
                rationale=args.rationale,
                actor=args.actor,
                role=args.role,
                artifact_root=_artifact_root(args.artifact_root),
                destination=args.output,
            )
        elif args.command == "runs":
            result = _list_persisted_runs(_artifact_root(args.artifact_root))
            _print_json(result)
            return 0
        elif args.command == "pilot-session":
            from app.backend.app.evidence.pilot_records import (
                create_pilot_session_record,
                load_pilot_record,
                summarize_pilot_record,
                write_pilot_record,
            )

            if args.pilot_command == "create":
                record = create_pilot_session_record(
                    participant_ref=args.participant_ref,
                    source_ready_at=args.source_ready_at,
                    outcome=cast("PilotOutcome", args.outcome),
                    bundle_path=args.bundle,
                    bundle_ready_at=args.bundle_ready_at,
                    reuse_kind=cast("PilotReuseKind | None", args.reuse_kind),
                    reuse_observed_at=args.reuse_at,
                )
                write_pilot_record(record, args.output)
                result = summarize_pilot_record(record, args.output)
            else:
                record = load_pilot_record(args.record)
                result = summarize_pilot_record(record, args.record)
        elif args.command == "source":
            from app.backend.app.evidence.pipeline import validate_source_document
            from app.backend.app.evidence.protocol_io import freeze, load_protocol

            result = validate_source_document(
                freeze(load_protocol(args.protocol)),
                args.source,
            )
        elif args.command == "gate3":
            from app.backend.app.evidence.gate3 import (
                evaluate_gate3,
                summarize_gate3_report,
                write_gate3_report,
            )

            report = evaluate_gate3(args.records)
            if args.output is not None:
                write_gate3_report(report, args.output)
            result = summarize_gate3_report(report, args.output)
            _print_json(result)
            # Exit 0 whatever the gate decided: `stop` is a successful
            # measurement of a disappointing cohort, not a failed command.
            return 0
        elif args.command == "verify":
            result = verify_bundle(args.archive)
        elif args.command == "inspect":
            result = inspect_bundle(args.archive)
            if args.format == "summary":
                _print_summary(result)
                return 0 if result["valid"] else 1
        else:
            raise AssertionError(f"unhandled command: {args.command}")
    except Exception as exc:
        deferred = _deferred_error_code(exc)
        if deferred is not None:
            _print_error(deferred, exc)
            return 1
        if isinstance(exc, AbxError):
            _print_error("pack_failed", exc)
            return 1
        if isinstance(exc, OSError):
            _print_error("io_error", exc)
            return 1
        if isinstance(exc, ValueError):
            if not reports_configuration_errors:
                raise
            _print_error("configuration_error", exc)
            return 1
        if not persisted_command:
            raise
        _print_error("repository_error", exc)
        return 1

    _print_json(result)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
