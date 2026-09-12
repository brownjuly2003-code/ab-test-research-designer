import { useEffect, useMemo, useState, type FormEvent } from "react";

import {
  downloadRunBundle,
  loadRun,
  loadRunPortfolio,
  overrideRunFinding,
  recordRunDecision,
  remediateRunFinding,
  type PersistedDecisionRequest,
  type PersistedRunPortfolio,
  type PersistedRunSummary,
  type PersistedRunView
} from "../../lib/api/workbench";
import styles from "./WorkbenchPage.module.css";

type DocumentRecord = Record<string, unknown>;

function asRecord(value: unknown): DocumentRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as DocumentRecord)
    : {};
}

function textValue(record: DocumentRecord, key: string, fallback = "n/a"): string {
  const value = record[key];
  return typeof value === "string" && value.length > 0 ? value : fallback;
}

function numberValue(record: DocumentRecord, key: string): number | null {
  const value = record[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function routeRunId(): string | null {
  const match = /^\/runs\/([^/]+)\/?$/.exec(window.location.pathname);
  return match ? decodeURIComponent(match[1]) : null;
}

function runHref(runId: string): string {
  return `/runs/${encodeURIComponent(runId)}`;
}

function protocolTitle(view: PersistedRunView): string {
  return textValue(asRecord(view.protocol.protocol), "title", view.run_id);
}

function protocolId(view: PersistedRunView): string {
  return textValue(asRecord(view.protocol.protocol), "protocol_id", view.protocol_revision_id);
}

function findingRank(finding: DocumentRecord): number {
  const state = textValue(finding, "state", "open");
  if (finding.blocking === true && state !== "resolved" && state !== "overridden") return 0;
  if (textValue(finding, "severity") === "warning" && state === "open") return 1;
  return 2;
}

function formatEstimate(value: number | null): string {
  if (value === null) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString("en-US", { maximumSignificantDigits: 6 })}`;
}

function PortfolioCard({ run }: { run: PersistedRunSummary }) {
  return (
    <article className={styles.finding}>
      <div className={styles.findingHeader}>
        <div>
          <span className={styles.findingCode}>{run.kind}</span>
          <h2>
            <a href={runHref(run.run_id)} aria-label={run.run_id}>
              {run.run_id}
            </a>
          </h2>
        </div>
        <span className={styles.stateBadge} data-state={run.status}>
          {run.status}
        </span>
      </div>
      <dl className={styles.evidenceBlock}>
        <div>
          <dt>Protocol revision</dt>
          <dd><code>{run.protocol_revision_id}</code></dd>
        </div>
        <div>
          <dt>Lineage</dt>
          <dd>{run.verdicts.lineage ?? "not checked"}</dd>
        </div>
        <div>
          <dt>Bundle</dt>
          <dd><code>{run.bundle_id}</code></dd>
        </div>
      </dl>
    </article>
  );
}

function FindingCard({
  finding,
  busy,
  onRemediate,
  onOverride
}: {
  finding: DocumentRecord;
  busy: boolean;
  onRemediate: () => void;
  onOverride: (reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  const findingId = textValue(finding, "finding_id");
  const code = textValue(finding, "code", "UNKNOWN_FINDING");
  const state = textValue(finding, "state", "open");
  const evidence = asRecord(finding.evidence);
  const remediation = asRecord(finding.remediation);
  const override = asRecord(finding.override);
  const closed = state === "resolved" || state === "overridden";

  function submitOverride(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onOverride(reason.trim());
  }

  return (
    <article
      className={`${styles.finding} ${
        textValue(finding, "severity") === "error" ? styles.findingError : styles.findingWarning
      } ${closed ? styles.findingClosed : ""}`}
      aria-labelledby={`${findingId}-title`}
    >
      <div className={styles.findingHeader}>
        <div>
          <span className={styles.findingCode}>{code}</span>
          <h3 id={`${findingId}-title`}>{textValue(finding, "summary", code)}</h3>
        </div>
        <span className={styles.stateBadge} data-state={state}>{state.replace("_", " ")}</span>
      </div>

      {Object.keys(evidence).length > 0 ? (
        <dl className={styles.evidenceBlock}>
          <div>
            <dt>{textValue(evidence, "label", "Evidence")}</dt>
            <dd>{textValue(evidence, "value")}</dd>
          </div>
          <div>
            <dt>Reference</dt>
            <dd><code>{textValue(evidence, "json_pointer")}</code></dd>
          </div>
        </dl>
      ) : null}

      {Object.keys(remediation).length > 0 ? (
        <div className={styles.remediation}>
          <span>{textValue(remediation, "code", "Remediation")}</span>
          <p>{textValue(remediation, "guidance")}</p>
        </div>
      ) : null}

      {!closed ? (
        <button
          type="button"
          className={styles.primaryAction}
          disabled={busy || findingId === "n/a"}
          onClick={onRemediate}
        >
          Mark {code} remediated
        </button>
      ) : null}

      {finding.override_allowed === true && !closed ? (
        <form className={styles.overrideForm} onSubmit={submitOverride}>
          <label>
            Override rationale
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Why this persisted finding is acceptable"
              rows={3}
            />
          </label>
          <button
            type="submit"
            className={styles.secondaryAction}
            disabled={busy || reason.trim().length < 20}
          >
            Record formal override
          </button>
        </form>
      ) : null}

      {Object.keys(override).length > 0 ? (
        <p className={styles.overrideRecord}>
          Overridden by <strong>{textValue(override, "actor_ref")}</strong>: {textValue(override, "reason")}
        </p>
      ) : null}
    </article>
  );
}

export default function WorkbenchPage() {
  const [activeRunId, setActiveRunId] = useState<string | null>(routeRunId);
  const [portfolio, setPortfolio] = useState<PersistedRunPortfolio | null>(null);
  const [view, setView] = useState<PersistedRunView | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const [decisionVerdict, setDecisionVerdict] = useState<PersistedDecisionRequest["verdict"]>("ship");
  const [decisionRationale, setDecisionRationale] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    if (activeRunId) {
      loadRun(activeRunId, controller.signal)
        .then((loaded) => {
          setView(loaded);
          setPortfolio(null);
        })
        .catch((loadError: unknown) => {
          if (!controller.signal.aborted) {
            setError(loadError instanceof Error ? loadError.message : "Unable to load evidence run.");
          }
        });
    } else {
      loadRunPortfolio(controller.signal)
        .then((loaded) => {
          setPortfolio(loaded);
          setView(null);
        })
        .catch((loadError: unknown) => {
          if (!controller.signal.aborted) {
            setError(loadError instanceof Error ? loadError.message : "Unable to load evidence runs.");
          }
        });
    }
    return () => controller.abort();
  }, [activeRunId]);

  const findings = useMemo(
    () => (view?.findings ?? []).map(asRecord).sort((left, right) => findingRank(left) - findingRank(right)),
    [view]
  );
  const estimates = useMemo(() => (view?.estimates ?? []).map(asRecord), [view]);

  function acceptChild(nextView: PersistedRunView, label: string) {
    window.history.pushState(null, "", runHref(nextView.run_id));
    setView(nextView);
    setActiveRunId(nextView.run_id);
    setAnnouncement(label);
  }

  async function perform(label: string, action: () => Promise<PersistedRunView>) {
    setBusy(label);
    setError("");
    try {
      acceptChild(await action(), label);
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : `Unable to ${label.toLowerCase()}.`);
    } finally {
      setBusy("");
    }
  }

  async function handleDownload() {
    if (!view) return;
    setBusy("Downloading evidence bundle");
    setError("");
    try {
      const artifact = await downloadRunBundle(view.run_id);
      const objectUrl = URL.createObjectURL(artifact.blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = artifact.filename;
      anchor.click();
      URL.revokeObjectURL(objectUrl);
      setAnnouncement(`${artifact.filename} downloaded.`);
    } catch (downloadError) {
      setError(downloadError instanceof Error ? downloadError.message : "Unable to download bundle.");
    } finally {
      setBusy("");
    }
  }

  async function handleDecision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!view) return;
    await perform("Human decision recorded", () =>
      recordRunDecision(view.run_id, {
        verdict: decisionVerdict,
        rationale: decisionRationale.trim()
      })
    );
  }

  if (!activeRunId) {
    return (
      <div className={styles.shell}>
        <section className={styles.masthead} aria-labelledby="run-portfolio-title">
          <div>
            <p className={styles.eyebrow}>Trialmark Workbench · persisted evidence</p>
            <h1 id="run-portfolio-title">Evidence runs</h1>
            <p>Content-bound runs remain immutable; every action creates a child run.</p>
          </div>
          <dl className={styles.statusGrid}>
            <div>
              <dt>Portfolio</dt>
              <dd>{portfolio ? `${portfolio.runs.length} persisted runs` : "Loading…"}</dd>
            </div>
          </dl>
        </section>
        {error ? <p className={styles.errorNotice} role="alert">{error}</p> : null}
        <section className={styles.findingsColumn} aria-label="Persisted evidence portfolio">
          <div className={styles.findingList}>
            {(portfolio?.runs ?? []).map((run) => <PortfolioCard key={run.run_id} run={run} />)}
          </div>
        </section>
      </div>
    );
  }

  if (!view) {
    return (
      <section className={styles.loadingPanel} aria-busy={!error}>
        <p className={styles.eyebrow}>Trialmark Workbench</p>
        <h1>{error ? "Run unavailable" : "Opening persisted evidence…"}</h1>
        {error ? <p role="alert">{error}</p> : <div className={styles.loadingBar} aria-hidden="true" />}
      </section>
    );
  }

  const source = asRecord(view.sources[0]);
  const fingerprint = asRecord(source.fingerprint);
  const decision = asRecord(view.decisions[0]);
  const decidedBy = asRecord(decision.decided_by);
  const decisionState = textValue(decision, "state", "");
  const humanDecisionRecorded = decisionState === "approved" || decisionState === "rejected";
  const parentRunId = textValue(asRecord(view.run), "parent_run_id", "none");
  const lineageVerdict = view.bundle.verdicts.lineage ?? "not checked";
  const stages = [
    { name: "Protocol", detail: "Frozen", state: "complete" },
    { name: "Run", detail: view.status, state: "complete" },
    { name: "Bundle", detail: `lineage ${lineageVerdict}`, state: lineageVerdict === "pass" ? "complete" : "current" },
    { name: "Decision", detail: humanDecisionRecorded ? "Recorded" : "Awaiting owner", state: humanDecisionRecorded ? "complete" : "current" }
  ];

  return (
    <div className={styles.shell}>
      <section className={styles.masthead} aria-labelledby="workbench-title">
        <div>
          <p className={styles.eyebrow}>Trialmark Workbench · persisted evidence</p>
          <h1 id="workbench-title">{protocolTitle(view)}</h1>
          <p className={styles.protocolId}>{protocolId(view)} / {view.protocol_revision_id}</p>
          <p><a href="/runs">← All evidence runs</a></p>
        </div>
        <dl className={styles.statusGrid}>
          <div><dt>Run</dt><dd>{view.run_id}</dd></div>
          <div><dt>Kind</dt><dd>{view.kind}</dd></div>
          <div><dt>Parent</dt><dd>{parentRunId}</dd></div>
        </dl>
      </section>

      <ol className={styles.progressRail} aria-label="Evidence workflow progress">
        {stages.map((stage, index) => (
          <li key={stage.name} data-state={stage.state}>
            <span className={styles.stageNumber}>{index + 1}</span>
            <span><strong>{stage.name}</strong><small>{stage.detail}</small></span>
          </li>
        ))}
      </ol>

      <div className={styles.noticeRegion}>
        {error ? <p className={styles.errorNotice} role="alert">{error}</p> : null}
        <p className={styles.srOnly} role="status" aria-live="polite">{announcement}</p>
      </div>

      <div className={styles.workbenchGrid}>
        <section className={styles.findingsColumn} aria-labelledby="preflight-findings-title">
          <div className={styles.sectionHeading}>
            <div>
              <p className={styles.kicker}>Persisted findings</p>
              <h2 id="preflight-findings-title">Reviewable evidence state</h2>
            </div>
          </div>
          <div className={styles.findingList}>
            {findings.length > 0 ? findings.map((finding) => {
              const findingId = textValue(finding, "finding_id");
              return (
                <FindingCard
                  key={findingId}
                  finding={finding}
                  busy={busy.length > 0}
                  onRemediate={() => void perform("Finding remediation persisted", () =>
                    remediateRunFinding(view.run_id, findingId)
                  )}
                  onOverride={(reason) => void perform("Formal override persisted", () =>
                    overrideRunFinding(view.run_id, findingId, { reason })
                  )}
                />
              );
            }) : (
              <article className={styles.finding}>
                <span className={styles.findingCode}>CLEAR</span>
                <h3>No persisted findings</h3>
                <p>This run reached publication without a blocking finding.</p>
              </article>
            )}
          </div>
        </section>

        <aside className={styles.evidenceColumn} aria-label="Evidence provenance and actions">
          <section className={styles.sourcePanel}>
            <div className={styles.panelLabel}>Source evidence</div>
            <h2>{textValue(source, "source_snapshot_id", "Persisted source")}</h2>
            <dl className={styles.sourceFacts}>
              <div><dt>Kind</dt><dd>{textValue(source, "kind")}</dd></div>
              <div><dt>Fingerprint</dt><dd><code>{textValue(fingerprint, "value")}</code></dd></div>
              <div><dt>Captured</dt><dd>{textValue(source, "captured_at")}</dd></div>
            </dl>
          </section>

          <section className={styles.estimatePanel} aria-label="Effect estimates">
            <div className={styles.panelLabel}>Persisted analysis</div>
            <h2>{estimates.length} estimates</h2>
            <div className={styles.findingList}>
              {estimates.map((estimate, index) => {
                const uncertainty = asRecord(estimate.uncertainty);
                const lineage = asRecord(estimate.lineage);
                const metric = asRecord(lineage.metric);
                return (
                  <article className={styles.finding} key={textValue(estimate, "estimate_id", String(index))}>
                    <span className={styles.findingCode}>{textValue(metric, "metric_id", `metric ${index + 1}`)}</span>
                    <h3>{formatEstimate(numberValue(estimate, "point_estimate"))}</h3>
                    <p>
                      {textValue(estimate, "effect_measure")} · {Number(textValue(uncertainty, "level", "0")) * 100}% CI {formatEstimate(numberValue(uncertainty, "lower"))} to {formatEstimate(numberValue(uncertainty, "upper"))}
                    </p>
                  </article>
                );
              })}
            </div>
          </section>

          <section className={styles.actionPanel}>
            <div className={styles.panelLabel}>Verified evidence artifact</div>
            <h2>Trialmark bundle</h2>
            <p>Bundle ID · <code>{view.bundle.bundle_id}</code></p>
            <dl className={styles.sourceFacts}>
              {Object.entries(view.bundle.verdicts).map(([name, verdict]) => (
                <div key={name}><dt>{name.replaceAll("_", " ")}</dt><dd>{verdict}</dd></div>
              ))}
            </dl>
            <button
              type="button"
              className={styles.primaryAction}
              disabled={busy.length > 0}
              onClick={() => void handleDownload()}
            >
              {busy === "Downloading evidence bundle" ? "Packing…" : "Download .tmk"}
            </button>
          </section>

          <section className={styles.decisionPanel}>
            <div className={styles.panelLabel}>Human authority</div>
            <h2>{humanDecisionRecorded ? "Decision record" : "Record decision"}</h2>
            {humanDecisionRecorded ? (
              <div className={styles.decisionRecord}>
                <strong>{textValue(decision, "human_verdict", textValue(decision, "state"))}</strong>
                <p>{textValue(decision, "rationale")}</p>
                <small><strong>{textValue(decidedBy, "actor_ref")}</strong></small>
              </div>
            ) : (
              <form className={styles.decisionForm} onSubmit={handleDecision}>
                <label>
                  Verdict
                  <select
                    value={decisionVerdict}
                    onChange={(event) => setDecisionVerdict(event.target.value as PersistedDecisionRequest["verdict"])}
                  >
                    <option value="ship">Ship</option>
                    <option value="hold">Hold</option>
                    <option value="stop">Stop</option>
                  </select>
                </label>
                <label>
                  Rationale
                  <textarea
                    value={decisionRationale}
                    onChange={(event) => setDecisionRationale(event.target.value)}
                    placeholder="Decision grounded in the persisted evidence"
                    rows={4}
                  />
                </label>
                <button
                  type="submit"
                  className={styles.primaryAction}
                  disabled={busy.length > 0 || decisionRationale.trim().length < 20}
                >
                  Record human decision
                </button>
              </form>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
