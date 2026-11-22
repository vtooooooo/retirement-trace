import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AlertTriangle,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  CalendarDays,
  ChartNoAxesCombined,
  ChevronRight,
  CircleHelp,
  ClipboardList,
  Clock3,
  FileSearch,
  Fingerprint,
  GitBranch,
  LayoutDashboard,
  LockKeyhole,
  Menu,
  Network,
  ScanLine,
  Search,
  ShieldCheck,
  Sparkles,
  UsersRound,
  X,
} from "lucide-react";
import type { Alert, Case, Counts, Dataset, Evidence, Match } from "./types";
import { availableDecisions, prioritize, type Role } from "./workflow";
import { api, ApiError, post, type Participant, type Session } from "./api";
import "./style.css";

const nav = [
  ["overview", "Command Center", LayoutDashboard],
  ["identity", "Identity Resolution", Fingerprint],
  ["alerts", "Benefit Discrepancies", AlertTriangle],
  ["graph", "Evidence Graph", Network],
  ["intelligence", "Investigation Intelligence", Sparkles],
  ["cases", "Case Workflow", ClipboardList],
  ["analytics", "Model & Operations", ChartNoAxesCombined],
  ["audit", "Audit & Governance", ShieldCheck],
] as const;
type Page = (typeof nav)[number][0];
const n = (value: number) => new Intl.NumberFormat("en-US").format(value);
const pct = (value: number) => (value * 100).toFixed(1) + "%";
const pretty = (value: string) => value.replaceAll("_", " ");
const money = (value: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    value / 100,
  );
const titleCase = (v: string) => v.charAt(0).toUpperCase() + v.slice(1);
const formatDate = (value: string) =>
  new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(value));
const stateTone = (v: string) =>
  v.startsWith("Pending")
    ? "violet"
    : v === "Awaiting evidence"
      ? "amber"
      : v === "Under investigation"
        ? "blue"
        : v === "Closed" || v === "Resolved"
          ? "green"
          : "neutral";

function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return <span className={"badge " + tone}>{children}</span>;
}
function Panel({
  title,
  subtitle,
  side,
  children,
}: {
  title: string;
  subtitle?: string;
  side?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="panel">
      <header className="panel-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {side}
      </header>
      {children}
    </section>
  );
}
function RankedBars({ values }: { values: Counts }) {
  const entries = Object.entries(values);
  const max = Math.max(1, ...Object.values(values));
  return (
    <div className="bars">
      {entries.map(([label, count], i) => (
        <div key={label}>
          <div>
            <span>{label}</span>
            <strong>{n(count)}</strong>
          </div>
          <div className="track">
            <span
              className={"bar c" + (i % 4)}
              style={{ width: (count / max) * 100 + "%" }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
function EvidenceItem({ item }: { item: Evidence }) {
  return (
    <article className="evidence-item">
      <div className="row">
        <Badge>{pretty(item.kind)}</Badge>
        <small>{item.id}</small>
      </div>
      <h3>{item.label}</h3>
      <p>
        {item.system} · {item.batch} · v{item.version}
      </p>
      <dl>
        {Object.entries({
          Status: item.status,
          Identifier: item.identifier,
          "Service year": item.year,
          District: item.address,
          Amount: item.cents === undefined ? undefined : money(item.cents),
          Ingested: item.ingested,
          Validation: item.validation,
        })
          .filter(([, v]) => v !== undefined && v !== null)
          .map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
      </dl>
    </article>
  );
}
function Timeline({ current }: { current: Case }) {
  return (
    <ol className="timeline">
      {[...current.timeline].reverse().map((e) => (
        <li key={e.version}>
          <span className="event-dot" />
          <div>
            <strong>{titleCase(pretty(e.kind))}</strong>
            <p>{e.note}</p>
            <small>
              {e.actor} · {formatDate(e.at)} · {e.state}
              {e.reference && " · " + e.reference}
            </small>
          </div>
        </li>
      ))}
    </ol>
  );
}
function Table({
  items,
  onCase,
}: {
  items: Case[];
  onCase: (c: Case) => void;
}) {
  if (!items.length)
    return <p className="empty">No cases match the current filters.</p>;
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Case / participant</th>
            <th>Discrepancy</th>
            <th>Priority</th>
            <th>Status</th>
            <th>Assigned to</th>
            <th>
              <span className="sr-only">Open</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr key={c.id}>
              <td>
                <button className="table-link" onClick={() => onCase(c)}>
                  {c.id}
                </button>
                <small>{c.name}</small>
              </td>
              <td>{c.alert.title}</td>
              <td>
                <Badge tone={c.alert.severity === "high" ? "red" : "amber"}>
                  <i />
                  {titleCase(c.alert.severity)}
                </Badge>
              </td>
              <td>
                <Badge tone={stateTone(c.state)}>{c.state}</Badge>
              </td>
              <td>{c.assignee ?? "Unassigned"}</td>
              <td>
                <button
                  aria-label={"Open " + c.id}
                  className="icon-btn"
                  onClick={() => onCase(c)}
                >
                  <ChevronRight size={16} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function Overview({
  data,
  onCase,
  go,
}: {
  data: Dataset;
  onCase: (c: Case) => void;
  go: (p: Page) => void;
}) {
  const { metrics: m, benchmark: b } = data;
  const stats = [
    [
      UsersRound,
      "Participant records",
      b.ingestion.sources,
      "Across synthetic source systems",
      "blue",
    ],
    [
      ClipboardList,
      "Open investigations",
      m.open,
      n(m.awaiting) + " awaiting evidence",
      "violet",
    ],
    [
      AlertTriangle,
      "High-priority cases",
      m.high,
      n(m.uncashed) + " potential uncashed payments",
      "amber",
    ],
    [
      ShieldCheck,
      "Pending human review",
      m.review,
      n(m.resolved) + " resolved or closed",
      "green",
    ],
  ] as const;
  const statuses = Object.entries(m.statuses);
  let offset = 0;
  const colors = [
    "#4166e6",
    "#849af7",
    "#a99aed",
    "#f4af52",
    "#48a995",
    "#7b879c",
    "#dd7c8b",
    "#3ab0ca",
    "#7a60d2",
  ];
  const segments = statuses.map(([s, q], i) => {
    const start = offset;
    offset += (q / Math.max(1, m.total)) * 100;
    return { s, q, color: colors[i % colors.length], start, end: offset };
  });
  const queue = prioritize(data.cases);
  return (
    <>
      <div className="stats">
        {stats.map(([Icon, label, value, detail, tone]) => (
          <div className="stat" key={label}>
            <div className="row">
              <span className={"stat-icon " + tone}>
                <Icon size={19} strokeWidth={1.8} />
              </span>
              <span>{label}</span>
            </div>
            <strong>{n(value)}</strong>
            <small>{detail}</small>
          </div>
        ))}
      </div>
      <div className="dashboard-charts">
        <Panel
          title="Investigation status"
          subtitle="Cases by current workflow stage"
          side={<Badge>All cases</Badge>}
        >
          <div className="distribution">
            <div
              aria-label={n(m.total) + " cases"}
              className="donut"
              style={{
                background: segments.length
                  ? "conic-gradient(" +
                    segments
                      .map((x) => x.color + " " + x.start + "% " + x.end + "%")
                      .join(",") +
                    ")"
                  : "#e9edf7",
              }}
            >
              <div>
                <strong>{n(m.total)}</strong>
                <small>Total cases</small>
              </div>
            </div>
            <div className="legend">
              {segments.map((x) => (
                <div key={x.s}>
                  <span style={{ background: x.color }} />
                  <label>{x.s}</label>
                  <strong>{n(x.q)}</strong>
                </div>
              ))}
            </div>
          </div>
        </Panel>
        <Panel
          title="Case aging"
          subtitle="Open investigations by age"
          side={
            <span className="muted overview-age">
              <Clock3 size={15} />
              {m.average_age} days avg.
            </span>
          }
        >
          <RankedBars
            values={Object.fromEntries(
              ["0–7 days", "8–14 days", "15–30 days", "31+ days"].map(
                (label) => [label, m.aging[label]],
              ),
            )}
          />
        </Panel>
      </div>
      <Panel
        title="Priority work queue"
        subtitle="High-priority cases ordered by age"
        side={
          <button className="button secondary" onClick={() => go("cases")}>
            View all cases <ArrowRight size={15} />
          </button>
        }
      >
        <Table items={queue.slice(0, 6)} onCase={onCase} />
      </Panel>
      <div className="dashboard-charts secondary-charts">
        <Panel
          title="Discrepancy categories"
          subtitle={
            n(b.ingestion.participants) +
            " synthetic participant anchors · " +
            n(m.reviewed_identities) +
            " independently reviewed"
          }
        >
          <RankedBars values={m.categories} />
        </Panel>
        <div className="stack">
          <Panel
            title="Analyst workload"
            subtitle="Open cases by assigned analyst"
          >
            <RankedBars values={m.workload} />
          </Panel>
          <Panel
            title="Resolution throughput"
            subtitle="Administrative resolution decisions by month"
          >
            {Object.keys(m.throughput).length ? (
              <RankedBars values={m.throughput} />
            ) : (
              <p className="content muted">
                No administrative resolutions have been recorded in this
                portfolio.
              </p>
            )}
          </Panel>
          <Panel
            title="Recent case activity"
            subtitle="Events in the currently accessible queue"
          >
            <ul className="activity-list">
              {data.cases
                .flatMap((c) => c.timeline.map((event) => ({ c, event })))
                .sort((a, b) => b.event.at.localeCompare(a.event.at))
                .slice(0, 4)
                .map(({ c, event }) => (
                  <li key={c.id + event.version}>
                    <button className="table-link" onClick={() => onCase(c)}>
                      {c.id}
                    </button>{" "}
                    {titleCase(pretty(event.kind))}{" "}
                    <small>{formatDate(event.at)}</small>
                  </li>
                ))}
            </ul>
          </Panel>
        </div>
      </div>
    </>
  );
}
function MatchView({ data, current }: { data: Dataset; current: Case }) {
  const matches = data.matches.filter((m) => m.person === current.person);
  const [selection, setSelection] = useState("");
  const match = matches.find((x) => x.id === selection) ?? matches[0];
  const decision =
    match &&
    [...current.timeline]
      .reverse()
      .find(
        (e) =>
          e.reference === match.id &&
          ["approve_identity", "reject_identity"].includes(e.kind),
      );
  return (
    <Panel
      title="Candidate comparison"
      subtitle="Relative confidence ranks source pairs for human review."
    >
      {!match ? (
        <p className="empty">
          No ranked cross-source candidates are available for this case. Select
          a different case to compare records.
        </p>
      ) : (
        <div className="content">
          <label className="field">
            Candidate pair
            <select
              value={match.id}
              onChange={(e) => setSelection(e.target.value)}
            >
              {matches.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.left} / {m.right} · {pct(m.score)}
                </option>
              ))}
            </select>
          </label>
          <div className="row wrap">
            <Badge
              tone={
                decision?.kind === "approve_identity"
                  ? "green"
                  : match.status === "abstain"
                    ? "amber"
                    : "blue"
              }
            >
              {decision
                ? pretty(decision.kind)
                : match.status === "abstain"
                  ? "Abstained"
                  : "Proposed match"}
            </Badge>
            <strong>{pct(match.score)} estimated probability</strong>
            <small>Model {match.version}</small>
          </div>
          <div className="twocol">
            {[match.left, match.right].map((id) => (
              <EvidenceItem key={id} item={data.evidence[id]} />
            ))}
          </div>
          <div className="twocol">
            <div>
              <h3>Supporting features</h3>
              <p>{match.agreements.join(" · ") || "No agreeing features"}</p>
            </div>
            <div>
              <h3>Conflicting features</h3>
              <p>
                {match.conflicts.join(" · ") ||
                  "No explicit conflicts recorded"}
              </p>
            </div>
          </div>
        </div>
      )}
    </Panel>
  );
}
function AlertDetails({ alert, onGo }: { alert: Alert; onGo: () => void }) {
  return (
    <Panel
      title={alert.title}
      subtitle={alert.id}
      side={
        <Badge tone={alert.severity === "high" ? "red" : "amber"}>
          {titleCase(alert.severity)} priority
        </Badge>
      }
    >
      <div className="content">
        <p>
          This is a rule-based flag for review. Benefit entitlement and payment
          decisions require independent administrative evidence.
        </p>
        <dl className="facts">
          <div>
            <dt>Source system</dt>
            <dd>{alert.source}</dd>
          </div>
          <div>
            <dt>Detection date</dt>
            <dd>{formatDate(alert.detected)}</dd>
          </div>
          <div>
            <dt>Rule version</dt>
            <dd>{alert.version}</dd>
          </div>
          <div>
            <dt>Review action</dt>
            <dd>{alert.action}</dd>
          </div>
          <div>
            <dt>Supporting evidence</dt>
            <dd>{alert.supporting.join(", ")}</dd>
          </div>
          <div>
            <dt>Conflicting evidence</dt>
            <dd>{alert.conflicting.join(", ") || "None recorded"}</dd>
          </div>
        </dl>
        <button className="button secondary" onClick={onGo}>
          Explore evidence <ArrowRight size={16} />
        </button>
      </div>
    </Panel>
  );
}
function Graph({ data, current }: { data: Dataset; current: Case }) {
  const [node, setNode] = useState("");
  const [filter, setFilter] = useState("all");
  const [until, setUntil] = useState(data.as_of);
  const [showSource, setShowSource] = useState(false);
  const matches = data.matches.filter((m) => m.person === current.person);
  const matchByRight = new Map<string, Match>(
    [...matches].reverse().map((m) => [m.right, m]),
  );
  const items = [...new Set([...current.evidence, ...matchByRight.keys()])]
    .map((id) => data.evidence[id])
    .filter(
      (r) => r.ingested <= until && (filter === "all" || r.kind === filter),
    );
  const selected = items.find((x) => x.id === node) ?? items[0];
  function relation(item: Evidence) {
    const match = matchByRight.get(item.id);
    if (match) {
      const decision = [...current.timeline]
        .reverse()
        .find(
          (e) =>
            e.reference === match.id &&
            ["approve_identity", "reject_identity"].includes(e.kind),
        );
      if (decision?.kind === "approve_identity") return "Review approved";
      if (decision?.kind === "reject_identity" || match.conflicts.length)
        return "Contradicted";
      return "Proposed";
    }
    if (current.alert.conflicting.includes(item.id)) return "Contradicted";
    return item.status === "historical" ? "Historical" : "Source-linked";
  }
  return (
    <Panel
      title="Case evidence graph"
      subtitle="Explore recorded provenance and proposed identity relationships."
    >
      <div className="content">
        <div className="row wrap">
          <label className="field">
            Evidence type
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="all">All evidence</option>
              {Array.from(
                new Set(
                  [...current.evidence, ...matchByRight.keys()].map(
                    (id) => data.evidence[id].kind,
                  ),
                ),
              ).map((k) => (
                <option key={k}>{k}</option>
              ))}
            </select>
          </label>
          <label className="field">
            Ingested on or before
            <input
              type="date"
              value={until}
              onChange={(e) => setUntil(e.target.value || data.as_of)}
            />
          </label>
        </div>
        <div className="graph">
          <div className="graph-center">
            <Network size={22} />
            <strong>{current.name}</strong>
            <small>{current.id}</small>
          </div>
          <div className="graph-edges">
            {items.map((item) => (
              <button
                key={item.id}
                onClick={() => {
                  setNode(item.id);
                  setShowSource(false);
                }}
                className={
                  "graph-node " +
                  (item.id === selected?.id ? "selected " : "") +
                  relation(item).toLowerCase().replace(" ", "-")
                }
              >
                <GitBranch size={15} />
                <span>
                  {item.label}
                  <small>
                    {relation(item)} · {item.system}
                  </small>
                </span>
              </button>
            ))}
          </div>
        </div>
        <div className="row wrap muted">
          <Badge tone="blue">Source-linked</Badge>
          <Badge tone="violet">Proposed</Badge>
          <Badge tone="red">Contradicted</Badge>
          <Badge tone="green">Review approved</Badge>
          <Badge>Historical</Badge>
        </div>
        <div>
          <h3>Cross-record links</h3>
          <ul className="edge-list">
            {items
              .filter((r) => r.obligation || matchByRight.has(r.id))
              .map((r) => {
                const pair = matchByRight.get(r.id);
                const from = pair?.left ?? r.id;
                const to = pair?.right ?? r.obligation!;
                return (
                  <li key={r.id}>
                    <span>
                      {from} → {to}
                    </span>
                    <button
                      className="table-link"
                      onClick={() => {
                        setNode(r.id);
                        setShowSource(false);
                      }}
                    >
                      {pair ? relation(r) : "Payment references obligation"}
                    </button>
                  </li>
                );
              })}
          </ul>
        </div>
        {selected ? (
          <div>
            <h3>{relation(selected)} relationship</h3>
            <p>
              {selected.obligation
                ? "Payment ledger references obligation " +
                  selected.obligation +
                  "."
                : selected.system +
                  " supplied this record in batch " +
                  selected.batch +
                  "."}{" "}
              {matchByRight.has(selected.id) &&
                " Candidate score " +
                  pct(matchByRight.get(selected.id)!.score) +
                  "."}
            </p>
            <button
              className="button secondary"
              onClick={() => setShowSource(!showSource)}
            >
              {showSource ? "Hide source record" : "Open source record"}
            </button>
            {showSource && <EvidenceItem item={selected} />}
          </div>
        ) : (
          <p>No evidence matches the current filters.</p>
        )}
      </div>
    </Panel>
  );
}
function Intelligence({ current }: { current: Case }) {
  return (
    <Panel
      title="Recommended investigation actions"
      subtitle="Ranked by modeled information gain, investigation effort, and association risk."
    >
      <div className="content">
        {current.actions.map((action, i) => (
          <article
            className={"action " + (i === 0 ? "featured" : "")}
            key={action.name}
          >
            <div className="row wrap">
              <span className="stat-icon violet">
                <Sparkles size={18} />
              </span>
              <h3>{action.name}</h3>
              {i === 0 && <Badge tone="violet">Recommended</Badge>}
            </div>
            <p>
              {i === 0
                ? "Highest eligible score for the available evidence."
                : "Scores " +
                  (current.actions[0].score - action.score).toFixed(3) +
                  " below the lead action after effort and risk penalties."}{" "}
              {action.uncertainty}
            </p>
            <dl className="facts">
              <div>
                <dt>Modeled information gain</dt>
                <dd>{action.gain} bits</dd>
              </div>
              <div>
                <dt>Estimated effort</dt>
                <dd>{action.effort} min</dd>
              </div>
              <div>
                <dt>Association risk</dt>
                <dd>{pct(action.risk)}</dd>
              </div>
              <div>
                <dt>Evidence reliability</dt>
                <dd>{pct(action.reliability)}</dd>
              </div>
              <div>
                <dt>Human approval</dt>
                <dd>{action.approval}</dd>
              </div>
              <div>
                <dt>Evidence prerequisites</dt>
                <dd>{action.evidence.join(", ")}</dd>
              </div>
            </dl>
          </article>
        ))}
      </div>
    </Panel>
  );
}
function Workflow({
  current,
  data,
  go,
  role,
  reload,
  expired,
}: {
  current: Case;
  data: Dataset;
  go: (p: Page) => void;
  role?: Role;
  reload: () => Promise<void>;
  expired: () => void;
}) {
  const [action, setAction] = useState("");
  const [note, setNote] = useState("");
  const [reference, setReference] = useState("");
  const [result, setResult] = useState("");
  const [busy, setBusy] = useState(false);
  const options = availableDecisions(current.state, current.alert.kind, role);
  const selected = options.includes(action) ? action : (options[0] ?? "");
  const refs = selected.endsWith("_identity")
    ? data.matches
        .filter(
          (m) =>
            m.person === current.person &&
            (current.alert.kind !== "identifier" ||
              current.alert.conflicting.includes(m.right)),
        )
        .map((m) => m.id)
    : selected === "assign"
      ? ["Maya Chen", "Jon Bell"]
      : selected === "record_action"
        ? current.actions.map((a) => a.name)
        : [];
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setResult("");
    try {
      await api(
        "/cases/" + current.id + "/decisions",
        post(
          {
            action: selected,
            note,
            version: current.version,
            reference: reference || null,
          },
          { "Idempotency-Key": crypto.randomUUID() },
        ),
      );
      await reload();
      setResult("Decision recorded in the audit trail.");
      setNote("");
      setReference("");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) expired();
      setResult((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel
      title={current.id + " · " + current.name}
      subtitle={current.alert.title}
      side={<Badge tone={stateTone(current.state)}>{current.state}</Badge>}
    >
      <div className="content">
        <div className="row wrap">
          {(
            [
              ["graph", "Evidence graph"],
              ["identity", "Compare identities"],
              ["intelligence", "Next actions"],
              ["audit", "Audit report"],
            ] as const
          ).map(([page, text]) => (
            <button
              key={page}
              className="button secondary"
              onClick={() => go(page)}
            >
              {text}
              <ArrowUpRight size={14} />
            </button>
          ))}
        </div>
        <div className="twocol">
          <div>
            <h3>Case timeline</h3>
            <Timeline current={current} />
          </div>
          <div>
            <h3>Record a decision</h3>
            {!options.length ? (
              <p className="read-only">
                <LockKeyhole size={16} /> This role has no available decisions
                in the current state.
              </p>
            ) : (
              <form className="form" onSubmit={submit}>
                <label className="field">
                  Decision
                  <select
                    value={selected}
                    onChange={(e) => {
                      setAction(e.target.value);
                      setReference("");
                    }}
                  >
                    {options.map((a) => (
                      <option key={a} value={a}>
                        {titleCase(pretty(a))}
                      </option>
                    ))}
                  </select>
                </label>
                {refs.length > 0 && (
                  <label className="field">
                    Reference
                    <select
                      value={reference}
                      onChange={(e) => setReference(e.target.value)}
                    >
                      <option value="">Select a reference</option>
                      {refs.map((ref) => (
                        <option key={ref}>{ref}</option>
                      ))}
                    </select>
                  </label>
                )}
                {selected === "attach" && (
                  <label className="field">
                    Internal document reference
                    <input
                      value={reference}
                      onChange={(e) => setReference(e.target.value)}
                      maxLength={120}
                      required
                    />
                  </label>
                )}
                <label className="field">
                  Decision rationale
                  <textarea
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    required
                    minLength={3}
                    maxLength={500}
                  />
                </label>
                <button className="button primary" disabled={busy}>
                  {busy ? "Saving…" : "Record decision"}
                </button>
                <p role="status">{result}</p>
              </form>
            )}
          </div>
        </div>
      </div>
    </Panel>
  );
}
function Analytics({ data }: { data: Dataset }) {
  const b = data.benchmark;
  return (
    <div className="stack">
      <Panel
        title="Entity-resolution benchmark"
        subtitle={
          "Synthetic candidate pairs · " +
          n(b.split_counts[2]) +
          " held-out pairs · model " +
          data.version
        }
      >
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {[
                  "Method",
                  "Precision",
                  "Recall",
                  "F1",
                  "False positive rate",
                  "False negative rate",
                  "Brier score",
                  "Abstention",
                ].map((h) => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(b.identity).map(([method, m]) => (
                <tr key={method}>
                  <td>
                    <strong>{method}</strong>
                  </td>
                  {[
                    "precision",
                    "recall",
                    "f1",
                    "false_positive_rate",
                    "false_negative_rate",
                    "brier",
                    "abstention",
                  ].map((key) => (
                    <td key={key}>
                      {key === "brier" ? m[key].toFixed(4) : pct(m[key])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="content">
          <h3>Precision–recall at model thresholds</h3>
          <RankedBars
            values={Object.fromEntries(
              b.curve.map((x) => [
                x.threshold.toFixed(2) +
                  " threshold · " +
                  pct(x.precision) +
                  " precision",
                Math.round(x.recall * 100),
              ]),
            )}
          />
          <small>
            Bars show recall in percent. Blocking and synthetic generation limit
            coverage. Identifier conflicts always require review.
          </small>
        </div>
      </Panel>
      <div className="twocol">
        <Panel
          title="Discrepancy detection"
          subtitle="Synthetic injected rule scenarios"
        >
          <RankedBars
            values={{
              "True positives": b.rules.tp,
              "False positives": b.rules.fp,
              "False negatives": b.rules.fn,
            }}
          />
        </Panel>
        <Panel
          title="Investigation simulation"
          subtitle={b.investigation.cases + " held-out cases"}
        >
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Policy</th>
                  <th>Steps</th>
                  <th>Minutes</th>
                  <th>Resolved</th>
                  <th>Unsafe</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(b.investigation.policies).map(([name, m]) => (
                  <tr key={name}>
                    <td>{name}</td>
                    <td>{m.mean_steps}</td>
                    <td>{m.mean_effort_minutes}</td>
                    <td>{m.resolved}</td>
                    <td>{m.unsafe}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="content muted">{b.investigation.assumptions}</p>
        </Panel>
      </div>
    </div>
  );
}
function Audit({ current, data }: { current: Case; data: Dataset }) {
  const [failure, setFailure] = useState("");
  async function download() {
    setFailure("");
    try {
      const response = await api("/cases/" + current.id + "/audit");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = current.id + "-audit.json";
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      setFailure((error as Error).message);
    }
  }
  return (
    <div className="stack">
      {failure && <p role="alert">{failure}</p>}
      <Panel
        title="Case audit trail"
        subtitle={current.id + " · " + current.name}
        side={
          <button className="button secondary" onClick={download}>
            <ArrowDownToLine size={16} /> Export audit report
          </button>
        }
      >
        <Timeline current={current} />
      </Panel>
      <Panel
        title="Governance and lineage"
        subtitle="Permissions and operating boundaries"
      >
        <div className="content">
          <dl className="facts">
            <div>
              <dt>Rule and model version</dt>
              <dd>{data.version}</dd>
            </div>
            <div>
              <dt>Synthetic batch</dt>
              <dd>SYN-{data.benchmark.ingestion.seed}</dd>
            </div>
            <div>
              <dt>Analyst</dt>
              <dd>Triage and investigation</dd>
            </div>
            <div>
              <dt>Senior reviewer</dt>
              <dd>Independent identity review</dd>
            </div>
            <div>
              <dt>Benefits administrator</dt>
              <dd>Administrative resolution</dd>
            </div>
            <div>
              <dt>Auditor / system administrator</dt>
              <dd>Read-only case access</dd>
            </div>
          </dl>
          <p>
            No participant outreach or payment authorization is available. This
            is synthetic operational evidence.
          </p>
        </div>
      </Panel>
    </div>
  );
}

const descriptions: Record<Page, [string, string]> = {
  overview: [
    "Retirement Operations",
    "Monitor unresolved benefits, prioritize investigations, and track case progress.",
  ],
  identity: [
    "Participant Identity Resolution",
    "Compare fragmented participant records and inspect supporting and conflicting features.",
  ],
  alerts: [
    "Benefit Discrepancies",
    "Inspect rule-based alerts and the source evidence that triggered them.",
  ],
  graph: [
    "Participant Evidence Graph",
    "Trace evidence to its source and inspect proposed and disputed relationships.",
  ],
  intelligence: [
    "Investigation Intelligence",
    "Compare eligible next steps and understand how each recommendation was ranked.",
  ],
  cases: [
    "Case Resolution Workflow",
    "Review the queue, follow case progress, and record authorized decisions.",
  ],
  analytics: [
    "Model & Operational Analytics",
    "Inspect held-out synthetic benchmarks and controlled investigation simulations.",
  ],
  audit: [
    "Audit & Governance",
    "Reconstruct case decisions and download the supporting synthetic evidence.",
  ],
};
const walkthrough: [Page, string][] = [
  [
    "overview",
    "Start with the priority queue and review your portfolio’s open investigations.",
  ],
  [
    "alerts",
    "Select an obligation without a payment record and inspect the rule evidence.",
  ],
  [
    "identity",
    "Select the Conflicting identifiers case and compare the two source records.",
  ],
  ["graph", "Follow a contradicted relationship and open its source record."],
  ["intelligence", "Compare the top recommendation against its alternatives."],
  [
    "cases",
    "Review the case timeline and the public demo’s decision-recording boundary.",
  ],
  [
    "analytics",
    "Compare held-out model performance and simulated investigation policies.",
  ],
  [
    "audit",
    "Download the synthetic audit report and review the evidence lineage.",
  ],
];

function initialPage(): Page {
  const key = location.hash.slice(1);
  return nav.find(([page]) => page === key)?.[0] ?? "overview";
}
function App() {
  const [page, setPage] = useState<Page>(initialPage);
  const [data, setData] = useState<Dataset>();
  const [failure, setFailure] = useState("");
  const [caseId, setCaseId] = useState(
    () => sessionStorage.getItem("pt.selectedCase") || "",
  );
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [status, setStatus] = useState("");
  const [mobile, setMobile] = useState(false);
  const [guide, setGuide] = useState(-1);
  const [identity, setIdentity] = useState<Session>();
  const [checking, setChecking] = useState(true);
  const [connectionAttempt, setConnectionAttempt] = useState(0);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [participant, setParticipant] = useState<Participant>();
  const [searchFailure, setSearchFailure] = useState("");
  const [limit, setLimit] = useState(20);
  const search = useRef<HTMLInputElement>(null);

  function clearSession() {
    setIdentity(undefined);
    setData(undefined);
    setParticipant(undefined);
    setParticipants([]);
    setCaseId("");
    setQuery("");
  }
  async function load() {
    try {
      const response = await api("/workspace");
      setData(await response.json());
      setFailure("");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) clearSession();
      throw error;
    }
  }
  useEffect(() => {
    async function restore() {
      setChecking(true);
      setFailure("");
      try {
        const response = await api("/session");
        setIdentity(await response.json());
        await load();
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 401)) {
          setFailure((error as Error).message);
        }
      } finally {
        setChecking(false);
      }
    }
    void restore();
  }, [connectionAttempt]);
  useEffect(() => {
    if (!identity || !searchOpen || query.trim().length < 2) return;
    const controller = new AbortController();
    const handle = window.setTimeout(async () => {
      try {
        const parameters = new URLSearchParams({ q: query.trim(), limit: "8" });
        const response = await api("/participants?" + parameters, {
          signal: controller.signal,
        });
        const found = (await response.json()) as Participant[];
        if (!controller.signal.aborted) setParticipants(found);
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 401) clearSession();
        else setSearchFailure("Participant search is temporarily unavailable.");
      }
    }, 250);
    return () => {
      window.clearTimeout(handle);
      controller.abort();
    };
  }, [identity, query, searchOpen]);
  async function signIn(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailure("");
    try {
      const response = await api("/session", post({ username, password }));
      setIdentity(await response.json());
      await load();
    } catch (error) {
      setFailure((error as Error).message);
    } finally {
      setBusy(false);
      setPassword("");
    }
  }
  async function signOut() {
    setBusy(true);
    try {
      await api("/session", { method: "DELETE" });
      clearSession();
      setFailure("");
    } catch (error) {
      setFailure((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    const sync = () => setPage(initialPage());
    const shortcut = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        search.current?.focus();
      }
      if (e.key === "Escape") {
        setSearchOpen(false);
        setMobile(false);
      }
    };
    addEventListener("hashchange", sync);
    addEventListener("keydown", shortcut);
    return () => {
      removeEventListener("hashchange", sync);
      removeEventListener("keydown", shortcut);
    };
  }, []);
  useEffect(() => {
    if (caseId) sessionStorage.setItem("pt.selectedCase", caseId);
    else sessionStorage.removeItem("pt.selectedCase");
  }, [caseId]);
  const current = data?.cases.find((c) => c.id === caseId) ?? data?.cases[0];
  function go(target: Page) {
    setPage(target);
    location.hash = target;
    setMobile(false);
    window.scrollTo(0, 0);
  }
  function open(c: Case, target: Page = "cases") {
    setCaseId(c.id);
    setParticipant(undefined);
    go(target);
    setSearchOpen(false);
    setQuery("");
  }
  function moveGuide(index: number) {
    setGuide(index);
    if (index >= 0) {
      if (index === 1 || index === 2) {
        setCaseId(
          data?.cases.find(
            (c) => c.alert.kind === (index === 1 ? "unpaid" : "identifier"),
          )?.id ?? "",
        );
      }
      go(walkthrough[index][0]);
    }
  }
  const results =
    data?.cases.filter((c) =>
      [c.id, c.person, c.name, c.alert.title]
        .join(" ")
        .toLowerCase()
        .includes(query.trim().toLowerCase()),
    ) ?? [];
  const filtered =
    data?.cases.filter((c) => !status || c.state === status) ?? [];
  const contextual = [
    "identity",
    "alerts",
    "graph",
    "intelligence",
    "cases",
    "audit",
  ].includes(page);
  const currentNav = nav.find((x) => x[0] === page)!;

  if (!identity) {
    return (
      <main className="signin-page">
        <section className="panel signin-panel" aria-labelledby="signin-title">
          <span className="brand-icon">
            <ScanLine size={23} />
          </span>
          <h1 id="signin-title">PensionTrace AI</h1>
          <p className="muted">
            Sign in to the synthetic retirement operations workspace.
          </p>
          {checking ? (
            <p role="status">
              Connecting to the workspace. An idle backend can take a minute to
              wake up.
            </p>
          ) : (
            <form className="form" onSubmit={signIn}>
              <label className="field">
                Username
                <input
                  autoComplete="username"
                  maxLength={64}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                />
              </label>
              <label className="field">
                Password
                <input
                  type="password"
                  autoComplete="current-password"
                  maxLength={256}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </label>
              <button className="button primary" disabled={busy}>
                {busy ? "Signing in…" : "Sign in"}
              </button>
            </form>
          )}
          {failure && (
            <div className="row wrap">
              <p role="alert" className="error">
                {failure}
              </p>
              <button
                type="button"
                className="button secondary"
                onClick={() => setConnectionAttempt((attempt) => attempt + 1)}
              >
                Retry connection
              </button>
            </div>
          )}
        </section>
      </main>
    );
  }

  return (
    <div className="app">
      {mobile && (
        <button
          className="scrim"
          aria-label="Close menu"
          onClick={() => setMobile(false)}
        />
      )}
      <aside className={"sidebar " + (mobile ? "show" : "")}>
        <a href="#overview" className="brand" onClick={() => go("overview")}>
          <div className="brand-icon">
            <ScanLine size={23} />
          </div>
          <div>
            <strong>
              PensionTrace <span>AI</span>
            </strong>
            <small>RETIREMENT INTELLIGENCE</small>
          </div>
        </a>
        <div className="workspace">
          <div className="workspace-icon">
            <Activity size={17} />
          </div>
          <div>
            <strong>Operations Workspace</strong>
            <small>Synthetic environment</small>
          </div>
        </div>
        <span className="section-label">WORKSPACES</span>
        <nav aria-label="Workspaces">
          {nav.map(([slug, label, Icon]) => (
            <a
              aria-current={slug === page ? "page" : undefined}
              className={slug === page ? "active" : ""}
              key={slug}
              href={"#" + slug}
              onClick={() => go(slug)}
            >
              <Icon size={17} strokeWidth={1.8} />
              <span>{label}</span>
              {slug === page && <span className="active-dot" />}
            </a>
          ))}
        </nav>
        <div className="side-bottom">
          <button
            className="guide-link"
            onClick={() => moveGuide(guide < 0 ? 0 : -1)}
          >
            <BookOpen size={17} /> Demo walkthrough <ChevronRight size={15} />
          </button>
          <div className="profile">
            <div className="avatar">
              {identity.name
                .split(" ")
                .map((part) => part[0])
                .slice(0, 2)
                .join("")}
            </div>
            <div>
              <strong>{identity.name}</strong>
              <small>
                {
                  {
                    analyst: "Analyst",
                    senior: "Senior reviewer",
                    benefits: "Benefits administrator",
                    auditor: "Auditor",
                    admin: "Administrator",
                  }[identity.role]
                }
              </small>
            </div>
            <button
              className="signout"
              disabled={busy}
              onClick={() => void signOut()}
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>
      <div className="frame">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-btn menu"
              aria-label="Open navigation"
              onClick={() => setMobile(!mobile)}
            >
              <Menu size={21} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>{currentNav[1]}</strong>
          </div>
          <div className="top-actions">
            <div className="search">
              <Search size={17} />
              <input
                ref={search}
                aria-label="Search cases and participants"
                placeholder="Search cases, participants…"
                maxLength={100}
                value={query}
                onFocus={() => setSearchOpen(true)}
                onChange={(e) => {
                  setSearchFailure("");
                  setParticipants([]);
                  setQuery(e.target.value);
                  setSearchOpen(true);
                }}
              />
              <kbd>Ctrl K</kbd>
              {searchOpen && query.trim() && (
                <div className="results" aria-label="Search results">
                  {results.slice(0, 8).map((c) => (
                    <button key={c.id} onClick={() => open(c)}>
                      <strong>
                        {c.name} · {c.id}
                      </strong>
                      <small>{c.alert.title}</small>
                    </button>
                  ))}
                  {participants
                    .filter(
                      (p) =>
                        !results.slice(0, 8).some((c) => c.id === p.case_id),
                    )
                    .map((p) => (
                      <button
                        key={p.id}
                        onClick={() => {
                          const linked = data?.cases.find(
                            (c) => c.id === p.case_id,
                          );
                          if (linked) open(linked);
                          else {
                            setParticipant(p);
                            setSearchOpen(false);
                            setQuery("");
                          }
                        }}
                      >
                        <strong>
                          {p.name} · {p.id}
                        </strong>
                        <small>Synthetic participant</small>
                      </button>
                    ))}
                  {searchFailure && <p role="status">{searchFailure}</p>}
                  {!results.length &&
                    !participants.length &&
                    !searchFailure && (
                      <p>No matching cases or participants yet.</p>
                    )}
                </div>
              )}
            </div>
            <button
              className="icon-btn help"
              aria-label="Open demo walkthrough"
              onClick={() => moveGuide(guide < 0 ? 0 : -1)}
            >
              <CircleHelp size={20} />
            </button>
          </div>
        </header>
        <main>
          {guide >= 0 && (
            <section className="walkthrough">
              <div>
                <strong>
                  Five-minute walkthrough · {guide + 1}/{walkthrough.length}
                </strong>
                <p>{walkthrough[guide][1]}</p>
              </div>
              <div className="row">
                <button
                  className="button secondary"
                  disabled={guide === 0}
                  onClick={() => moveGuide(guide - 1)}
                >
                  Back
                </button>
                <button
                  className="button primary"
                  onClick={() =>
                    moveGuide(guide === walkthrough.length - 1 ? -1 : guide + 1)
                  }
                >
                  {guide === walkthrough.length - 1 ? "Finish" : "Next"}
                </button>
                <button
                  className="icon-btn"
                  aria-label="Close walkthrough"
                  onClick={() => moveGuide(-1)}
                >
                  <X size={18} />
                </button>
              </div>
            </section>
          )}
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                <span />
                {page === "overview"
                  ? "OPERATIONS COMMAND CENTER"
                  : currentNav[1].toUpperCase()}
              </div>
              <h1>{descriptions[page][0]}</h1>
              <p>{descriptions[page][1]}</p>
            </div>
            <div className="heading-actions">
              <Badge tone="green">
                <LockKeyhole size={13} />
                Live synthetic workspace
              </Badge>
              {data && (
                <span className="date">
                  <CalendarDays size={15} />
                  {formatDate(data.as_of)}
                </span>
              )}
            </div>
          </div>
          {participant && (
            <Panel
              title={participant.name}
              subtitle={participant.id + " · Synthetic participant"}
              side={
                <button
                  className="icon-btn"
                  aria-label="Close participant"
                  onClick={() => setParticipant(undefined)}
                >
                  <X size={16} />
                </button>
              }
            >
              <p className="content">
                No investigation case is linked to this participant.
              </p>
            </Panel>
          )}
          {failure && (
            <div className="error" role="alert">
              {failure}
              <button
                className="button secondary"
                onClick={() => void load().catch((e) => setFailure(e.message))}
              >
                Retry
              </button>
            </div>
          )}
          {!data && !failure && (
            <p role="status">
              Loading workspace. If the backend was idle, this may take a
              minute.
            </p>
          )}
          {data && page === "overview" && (
            <Overview data={data} onCase={open} go={go} />
          )}
          {data && page === "analytics" && <Analytics data={data} />}
          {data && contextual && current && (
            <div className="stack">
              <div className="context">
                <div className="row">
                  <FileSearch size={18} />
                  <strong>Case context</strong>
                </div>
                <label className="sr-only" htmlFor="case">
                  Select case
                </label>
                <select
                  id="case"
                  value={current.id}
                  onChange={(e) => setCaseId(e.target.value)}
                >
                  {data.cases.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.id} · {c.name} · {c.alert.title}
                    </option>
                  ))}
                </select>
              </div>
              {page === "identity" && (
                <MatchView key={current.id} data={data} current={current} />
              )}
              {page === "alerts" && (
                <>
                  <AlertDetails
                    alert={current.alert}
                    onGo={() => go("graph")}
                  />
                  <Panel
                    title="Discrepancy queue"
                    subtitle="Open a case to review the associated workflow."
                  >
                    <Table items={data.cases.slice(0, limit)} onCase={open} />
                    {data.cases.length > limit && (
                      <button
                        className="button secondary more"
                        onClick={() => setLimit(limit + 20)}
                      >
                        Show more cases
                      </button>
                    )}
                  </Panel>
                </>
              )}
              {page === "graph" && (
                <Graph key={current.id} data={data} current={current} />
              )}
              {page === "intelligence" && <Intelligence current={current} />}
              {page === "cases" && (
                <>
                  <Workflow
                    key={current.id}
                    current={current}
                    data={data}
                    go={go}
                    role={identity.role}
                    expired={clearSession}
                    reload={() => load()}
                  />
                  <Panel
                    title="Investigation queue"
                    subtitle={n(filtered.length) + " accessible cases"}
                    side={
                      <label className="field">
                        <span className="sr-only">Filter by status</span>
                        <select
                          value={status}
                          onChange={(e) => {
                            setStatus(e.target.value);
                            setLimit(20);
                          }}
                        >
                          <option value="">All statuses</option>
                          {Array.from(new Set(data.cases.map((c) => c.state)))
                            .sort()
                            .map((s) => (
                              <option key={s}>{s}</option>
                            ))}
                        </select>
                      </label>
                    }
                  >
                    <Table items={filtered.slice(0, limit)} onCase={open} />
                    {filtered.length > limit && (
                      <button
                        className="button secondary more"
                        onClick={() => setLimit(limit + 20)}
                      >
                        Show more cases
                      </button>
                    )}
                  </Panel>
                </>
              )}
              {page === "audit" && <Audit current={current} data={data} />}
            </div>
          )}
          <footer>
            <ShieldCheck size={15} /> Synthetic retirement records only. No
            participant contact or payment authorization.
          </footer>
        </main>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
