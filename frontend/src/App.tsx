import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  CalibrationStats,
  Catalyst,
  DeskSettings,
  Holiday,
  Me,
  PreopenWatch,
  ReportDetail,
  ReportSummary,
  api,
} from "./api";
import { cronToDays, cronToTime, buildScheduleCron, describeSchedule, formatNextRun } from "./schedule";

type Tab = "desk" | "preopen" | "calibration" | "holidays" | "settings";
type DeskFilter =
  | "priority"
  | "verified_gap"
  | "bullish"
  | "bearish"
  | "fade"
  | "unverified"
  | "carryover"
  | "all";

function biasClass(bias: string) {
  const b = (bias || "").toLowerCase();
  if (b.includes("bull")) return "bias-bull";
  if (b.includes("bear")) return "bias-bear";
  return "bias-mixed";
}

function stars(n: number) {
  const s = Math.max(0, Math.min(5, n || 0));
  return "★".repeat(s) + "☆".repeat(5 - s);
}

function formatWhen(iso: string) {
  try {
    const d = iso.endsWith("Z") || iso.includes("+") ? new Date(iso) : new Date(iso + "Z");
    return d.toLocaleString("en-IN", { timeZone: "Asia/Kolkata" });
  } catch {
    return iso;
  }
}

export default function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [booting, setBooting] = useState(true);
  const [tab, setTab] = useState<Tab>("desk");
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .me()
      .then(setMe)
      .catch(() => setMe(null))
      .finally(() => setBooting(false));
  }, []);

  if (booting) {
    return (
      <div className="login-wrap">
        <p className="muted">Loading desk…</p>
      </div>
    );
  }

  if (!me) {
    return (
      <Login
        onLogin={(u) => {
          setMe(u);
          setError("");
        }}
      />
    );
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <div className="brand">
            Premarket <span>Desk</span>
          </div>
          <div className="muted" style={{ fontSize: "0.9rem" }}>
            NSE catalyst note · signed in as {me.username}
          </div>
        </div>
        <nav className="nav">
          <button className={tab === "desk" ? "active" : ""} onClick={() => setTab("desk")}>
            Desk
          </button>
          <button className={tab === "preopen" ? "active" : ""} onClick={() => setTab("preopen")}>
            Pre-open
          </button>
          <button className={tab === "calibration" ? "active" : ""} onClick={() => setTab("calibration")}>
            Calibration
          </button>
          <button className={tab === "holidays" ? "active" : ""} onClick={() => setTab("holidays")}>
            Holidays
          </button>
          <button className={tab === "settings" ? "active" : ""} onClick={() => setTab("settings")}>
            Settings
          </button>
          <button
            className="btn ghost"
            onClick={async () => {
              await api.logout();
              setMe(null);
            }}
          >
            Log out
          </button>
        </nav>
      </header>

      {error && (
        <div className="banner error-banner">
          {error}
          <button className="btn ghost" onClick={() => setError("")}>
            Dismiss
          </button>
        </div>
      )}

      {tab === "desk" && <DeskView onError={setError} />}
      {tab === "preopen" && <PreopenView onError={setError} />}
      {tab === "calibration" && <CalibrationView onError={setError} />}
      {tab === "holidays" && <HolidaysView onError={setError} />}
      {tab === "settings" && <SettingsView onError={setError} />}
    </div>
  );
}

function Login({ onLogin }: { onLogin: (me: Me) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      onLogin(await api.login(username, password));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <h1>Premarket Desk</h1>
        <p>Password-gated India pre-market catalyst research.</p>
        <div className="field">
          <label>Username</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        </div>
        <div className="field">
          <label>Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </div>
        {error && <p className="error">{error}</p>}
        <button className="btn primary" disabled={loading} style={{ width: "100%" }}>
          {loading ? "Signing in…" : "Enter desk"}
        </button>
      </form>
    </div>
  );
}

function parseProgress(raw: string): { step: string; detail: string } {
  const m = raw.match(/^step:([a-z]+)\|(.+)$/i);
  if (m) return { step: m[1].toLowerCase(), detail: m[2] };
  return { step: "", detail: raw || "Working…" };
}

const PIPELINE = [
  { id: "window", label: "Resolve news window", hint: "Previous NSE close → cutoff" },
  { id: "fetch", label: "Fetch market news", hint: "Groww feed since last close" },
  { id: "classify", label: "Classify catalysts", hint: "Filter noise, dedupe, score" },
  { id: "enrich", label: "Enrich top names", hint: "AI notes on strongest names" },
  { id: "view", label: "Build market view", hint: "Bias, risks, opportunities" },
  { id: "compose", label: "Compose research note", hint: "Desk note + PDF layout" },
  { id: "email", label: "Deliver", hint: "Email PDF to your inbox" },
  { id: "done", label: "Ready", hint: "Note available on desk" },
] as const;

function AiPipelineProgress({
  pct,
  message,
  includeEmail = true,
}: {
  pct: number;
  message: string;
  includeEmail?: boolean;
}) {
  const { step, detail } = parseProgress(message);
  const steps = includeEmail ? [...PIPELINE] : PIPELINE.filter((s) => s.id !== "email");

  const order = steps.map((s) => s.id);
  let activeIdx = order.indexOf(step as (typeof order)[number]);
  if (activeIdx < 0) {
    if (pct >= 100) activeIdx = order.length - 1;
    else if (pct >= 90) activeIdx = order.indexOf("email");
    else if (pct >= 82) activeIdx = order.indexOf("compose");
    else if (pct >= 70) activeIdx = order.indexOf("view");
    else if (pct >= 60) activeIdx = order.indexOf("enrich");
    else if (pct >= 45) activeIdx = order.indexOf("classify");
    else if (pct >= 15) activeIdx = order.indexOf("fetch");
    else activeIdx = 0;
  }
  if (step === "error") activeIdx = Math.max(0, activeIdx);

  return (
    <div className="ai-pipeline">
      <div className="ai-pipeline-head">
        <div className="ai-pulse" aria-hidden />
        <div>
          <div className="ai-title">Desk is thinking</div>
          <div className="muted ai-sub">{detail}</div>
        </div>
        <div className="ai-pct">{Math.round(pct)}%</div>
      </div>

      <div className="ai-track">
        <div className="progress-fill" style={{ width: `${Math.max(3, pct)}%` }} />
      </div>

      <ol className="ai-steps">
        {steps.map((s, i) => {
          const state = i < activeIdx ? "done" : i === activeIdx ? (step === "error" ? "error" : "active") : "todo";
          return (
            <li key={s.id} className={`ai-step ${state}`}>
              <span className="ai-dot" aria-hidden>
                {state === "done" ? "✓" : state === "active" ? "" : ""}
              </span>
              <div className="ai-step-body">
                <div className="ai-step-label">
                  {s.label}
                  {state === "active" && <span className="ai-typing">…</span>}
                </div>
                <div className="ai-step-hint">{state === "active" ? detail : s.hint}</div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function DeskView({ onError }: { onError: (s: string) => void }) {
  const [latest, setLatest] = useState<ReportDetail | null>(null);
  const [history, setHistory] = useState<ReportSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState({ pct: 0, message: "" });
  const [msg, setMsg] = useState("");
  const [filter, setFilter] = useState<DeskFilter>("priority");
  const [showRaw, setShowRaw] = useState(false);

  async function refreshHistory() {
    const list = await api.reports();
    setHistory(list);
    return list;
  }

  useEffect(() => {
    (async () => {
      try {
        const list = await refreshHistory();
        const active = await api.activeRun();
        if (active && active.status === "running") {
          setRunning(true);
          setSelectedId(active.id);
          setLatest(active);
          setProgress({ pct: active.progress_pct || 0, message: active.progress_message || "Running…" });
          return;
        }
        const ok = list.find((r) => r.status === "ok");
        if (ok) {
          const full = await api.getReport(ok.id);
          setLatest(full);
          setSelectedId(ok.id);
        }
      } catch (err) {
        onError(err instanceof Error ? err.message : "Failed to load");
      }
    })();
  }, []);

  // Poll while running
  useEffect(() => {
    if (!running || !selectedId) return;
    const t = setInterval(async () => {
      try {
        const row = await api.getReport(selectedId);
        setLatest(row);
        setProgress({ pct: row.progress_pct || 0, message: row.progress_message || "" });
        if (row.status !== "running") {
          setRunning(false);
          setMsg(
            row.status === "ok"
              ? `Done #${row.id}${row.emailed ? " · emailed" : ""}`
              : `Failed #${row.id}: ${row.progress_message || "error"}`
          );
          await refreshHistory();
        }
      } catch {
        /* keep polling */
      }
    }, 900);
    return () => clearInterval(t);
  }, [running, selectedId]);

  useEffect(() => {
    if (!selectedId || running) return;
    if (latest && latest.id === selectedId && latest.status !== "running") return;
    api
      .getReport(selectedId)
      .then(setLatest)
      .catch((err) => onError(err instanceof Error ? err.message : "Load failed"));
  }, [selectedId]);

  async function runNow(sendEmail: boolean) {
    setMsg("");
    onError("");
    try {
      const report = await api.runReport({ send_email: sendEmail });
      setLatest(report);
      setSelectedId(report.id);
      setProgress({ pct: report.progress_pct || 5, message: report.progress_message || "Starting…" });
      setRunning(true);
      await refreshHistory();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Run failed");
      setRunning(false);
    }
  }

  const catalysts = (latest?.payload?.catalysts || []) as Catalyst[];
  const view = latest?.payload?.market_view;
  const tape = latest?.payload?.market_tape;
  const globalTape = latest?.payload?.global_tape;
  const precision = latest?.payload?.precision;

  const filtered = useMemo(() => {
    const byPriority = (a: Catalyst, b: Catalyst) =>
      (b.priority_rank || 0) - (a.priority_rank || 0) ||
      (b.conviction || 0) - (a.conviction || 0) ||
      b.strength - a.strength;

    let list = [...catalysts];
    if (filter === "priority") {
      list = list.filter((c) => c.strength >= 2 || (c.priority_rank || 0) >= 50);
    } else if (filter === "verified_gap") {
      list = list.filter(
        (c) =>
          c.priority_tier === "verified_gap" ||
          (c.filing_status === "verified" && /gap/i.test(c.opening_impact || "")),
      );
    } else if (filter === "fade") {
      list = list.filter((c) => /fade/i.test(c.opening_impact || "") || c.priority_tier === "fade");
    } else if (filter === "unverified") {
      list = list.filter((c) => c.filing_status === "unverified" || c.priority_tier === "unverified");
    } else if (filter === "carryover") {
      list = list.filter((c) => c.carryover);
    } else if (filter === "bullish" || filter === "bearish") {
      list = list.filter((c) => c.bias === filter && c.strength >= 2);
    } else {
      list = list.filter((c) => c.strength >= 2);
    }
    return list.sort(byPriority).slice(0, filter === "all" ? 30 : 20);
  }, [catalysts, filter]);

  return (
    <div className="desk-layout">
      <section className="panel main-panel">
        <div className="manual-bar">
          <div>
            <h2>Manual fetch</h2>
            <p className="muted">Pull news since last NSE close, score catalysts, email when ready.</p>
          </div>
          <div className="row">
            <button className="btn primary" disabled={running} onClick={() => runNow(true)}>
              {running ? "Working…" : "Fetch & email"}
            </button>
            <button className="btn" disabled={running} onClick={() => runNow(false)}>
              Fetch only
            </button>
            {latest?.status === "ok" && (
              <>
                <button
                  className="btn"
                  disabled={running}
                  onClick={async () => {
                    try {
                      await api.downloadPdf(latest.id);
                      setMsg(`PDF downloaded (#${latest.id})`);
                    } catch (err) {
                      onError(err instanceof Error ? err.message : "PDF failed");
                    }
                  }}
                >
                  Download PDF
                </button>
                <button
                  className="btn"
                  disabled={running}
                  onClick={async () => {
                    try {
                      setMsg((await api.emailReport(latest.id)).message);
                    } catch (err) {
                      onError(err instanceof Error ? err.message : "Email failed");
                    }
                  }}
                >
                  Email PDF
                </button>
              </>
            )}
          </div>
        </div>

        {running && (
          <AiPipelineProgress pct={progress.pct} message={progress.message} includeEmail />
        )}

        {msg && !running && <p className="success">{msg}</p>}

        {!latest ? (
          <div className="empty-state">
            <h3>No note yet</h3>
            <p className="muted">Hit Fetch & email to build today’s pre-market desk note.</p>
          </div>
        ) : latest.status === "running" ? null : latest.status === "error" ? (
          <div className="empty-state">
            <h3>Run failed</h3>
            <p className="error">{latest.progress_message || latest.markdown}</p>
          </div>
        ) : (
          <>
            <div className="stats">
              <div className="stat">
                <div className="label">Bias</div>
                <div className={`value ${biasClass(view?.bias || latest.bias)}`}>
                  {view?.bias || latest.bias}
                </div>
              </div>
              <div className="stat">
                <div className="label">Confidence</div>
                <div className="value">{view?.confidence ?? latest.confidence}/10</div>
              </div>
              <div className="stat">
                <div className="label">Articles</div>
                <div className="value">{latest.articles_in_window}</div>
              </div>
              <div className="stat">
                <div className="label">Stocks</div>
                <div className="value">{latest.unique_stocks}</div>
              </div>
            </div>

            <div className="meta-line muted">
              #{latest.id} · cutoff {latest.cutoff_iso} · {latest.emailed ? "emailed" : "not emailed"}
              {latest.used_llm ? " · LLM" : " · heuristic"} · {formatWhen(latest.created_at)}
            </div>

            {globalTape?.gift_nifty?.last != null && (
              <div className="tape-panel gift-panel">
                <h3>GIFT Nifty · global open</h3>
                <div className="tape-grid">
                  <div className="tape-stat">
                    <span className="label">GIFT Nifty</span>
                    <span>
                      {globalTape.gift_nifty!.last!.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
                    </span>
                  </div>
                  <div className="tape-stat">
                    <span className="label">vs cash / chg</span>
                    <span
                      className={
                        (globalTape.gift_nifty!.implied_gap_vs_nifty_pct ??
                          globalTape.gift_nifty!.change_pct ??
                          0) >= 0
                          ? "pos"
                          : "neg"
                      }
                    >
                      {(
                        globalTape.gift_nifty!.implied_gap_vs_nifty_pct ??
                        globalTape.gift_nifty!.change_pct ??
                        0
                      ) >= 0
                        ? "+"
                        : ""}
                      {(
                        globalTape.gift_nifty!.implied_gap_vs_nifty_pct ??
                        globalTape.gift_nifty!.change_pct ??
                        0
                      ).toFixed(2)}
                      %
                    </span>
                  </div>
                  <div className="tape-stat">
                    <span className="label">Open bias</span>
                    <span>{globalTape.gift_nifty!.open_bias || "—"}</span>
                  </div>
                  <div className="tape-stat">
                    <span className="label">Risk</span>
                    <span>{globalTape.composite_risk || "—"}</span>
                  </div>
                </div>
                <div className="cue-strip muted">
                  {(globalTape.cues || [])
                    .filter((c) => c.change_pct != null)
                    .slice(0, 6)
                    .map((c) => (
                      <span key={c.symbol} className={(c.change_pct ?? 0) >= 0 ? "pos" : "neg"}>
                        {c.name.replace(" Futures", "").replace(" Index", "")}{" "}
                        {(c.change_pct ?? 0) >= 0 ? "+" : ""}
                        {(c.change_pct ?? 0).toFixed(2)}%
                      </span>
                    ))}
                </div>
                <p className="muted tape-note">{globalTape.interpretation?.[0] || ""}</p>
              </div>
            )}

            {tape?.flows?.fii_net_cr != null && (
              <div className="tape-panel">
                <h3>Market tape</h3>
                <div className="tape-grid">
                  <div className="tape-stat">
                    <span className="label">FII net</span>
                    <span className={tape.flows!.fii_net_cr! >= 0 ? "pos" : "neg"}>
                      {tape.flows!.fii_net_cr! >= 0 ? "+" : ""}
                      {tape.flows!.fii_net_cr!.toLocaleString("en-IN")} Cr
                    </span>
                  </div>
                  <div className="tape-stat">
                    <span className="label">DII net</span>
                    <span className={(tape.flows?.dii_net_cr ?? 0) >= 0 ? "pos" : "neg"}>
                      {(tape.flows?.dii_net_cr ?? 0) >= 0 ? "+" : ""}
                      {(tape.flows?.dii_net_cr ?? 0).toLocaleString("en-IN")} Cr
                    </span>
                  </div>
                  {tape.nifty?.change_pct != null && (
                    <div className="tape-stat">
                      <span className="label">Nifty</span>
                      <span className={tape.nifty.change_pct >= 0 ? "pos" : "neg"}>
                        {tape.nifty.change_pct >= 0 ? "+" : ""}
                        {tape.nifty.change_pct.toFixed(2)}%
                      </span>
                    </div>
                  )}
                  {tape.india_vix?.last != null && (
                    <div className="tape-stat">
                      <span className="label">VIX</span>
                      <span>
                        {tape.india_vix.last.toFixed(2)}
                        {tape.volatility_regime ? ` · ${tape.volatility_regime}` : ""}
                      </span>
                    </div>
                  )}
                </div>
                <p className="muted tape-note">
                  {tape.flow_bias}
                  {tape.interpretation?.[0] ? ` — ${tape.interpretation[0]}` : ""}
                </p>
              </div>
            )}

            {precision && (
              <div className="tape-panel">
                <h3>Precision layer</h3>
                <div className="tape-grid">
                  <div className="tape-stat">
                    <span className="label">Filings verified</span>
                    <span>
                      {precision.filings_verified ?? 0}
                      <span className="muted"> / {precision.filings_scanned ?? 0} scanned</span>
                    </span>
                  </div>
                  <div className="tape-stat">
                    <span className="label">Secondary wire</span>
                    <span>
                      {precision.secondary?.confirmed ?? 0}/{precision.secondary?.top_checked ?? 0}
                    </span>
                  </div>
                  <div className="tape-stat">
                    <span className="label">India ADRs</span>
                    <span
                      className={(precision.adr_tape?.composite_pct ?? 0) >= 0 ? "pos" : "neg"}
                    >
                      {precision.adr_tape?.composite_pct != null
                        ? `${precision.adr_tape.composite_pct >= 0 ? "+" : ""}${precision.adr_tape.composite_pct}%`
                        : "—"}
                    </span>
                  </div>
                  <div className="tape-stat">
                    <span className="label">Event / FO</span>
                    <span>
                      {precision.event_context?.regime || "—"}
                      {precision.fo_overlay?.fo_bias ? ` · ${precision.fo_overlay.fo_bias}` : ""}
                    </span>
                  </div>
                </div>
                {(precision.fo_flow?.interpretation?.[0] || precision.deals?.bulk_count != null) && (
                  <p className="muted tape-note">
                    {precision.fo_flow?.interpretation?.[0] || ""}
                    {precision.deals?.bulk_count != null
                      ? ` · Deals: ${precision.deals.bulk_count} bulk / ${precision.deals.block_count ?? 0} block`
                      : ""}
                  </p>
                )}
              </div>
            )}

            {(view?.reasons?.length || view?.opportunity || view?.risk) && (
              <div className="insight-row">
                <div className="insight">
                  <h3>Why this tape</h3>
                  <ul>
                    {(view?.reasons || []).slice(0, 4).map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                </div>
                <div className="insight">
                  <h3>Focus</h3>
                  <p>
                    <span className="bias-bull">Opp:</span> {view?.opportunity || "—"}
                  </p>
                  <p>
                    <span className="bias-bear">Risk:</span> {view?.risk || "—"}
                  </p>
                </div>
              </div>
            )}

            <div className="filter-row">
              {(
                [
                  ["priority", "Best first"],
                  ["verified_gap", "Verified gaps"],
                  ["bullish", "Bullish"],
                  ["bearish", "Bearish"],
                  ["fade", "Fade risk"],
                  ["unverified", "Unverified"],
                  ["carryover", "Carryover"],
                  ["all", "All"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  className={`chip ${filter === key ? "active" : ""}`}
                  onClick={() => setFilter(key)}
                >
                  {label}
                </button>
              ))}
              <button className="chip ghost" onClick={() => setShowRaw((v) => !v)}>
                {showRaw ? "Hide raw note" : "Raw markdown"}
              </button>
            </div>

            <div className="card-grid">
              {filtered.length === 0 && <p className="muted">No names in this filter.</p>}
              {filtered.map((c) => (
                <article key={`${c.symbol}-${c.event_type}`} className={`cat-card ${c.bias}`}>
                  <header>
                    <div>
                      <div className="sym">{c.symbol}</div>
                      <div className="name">{c.name}</div>
                    </div>
                    <div className="badge">{c.opening_impact}</div>
                  </header>
                  <div className="stars">{stars(c.strength)}</div>
                  <div className="event">{c.event_type.replace(/_/g, " ")}</div>
                  {(c.conviction != null && c.conviction > 0) && (
                    <div className="conviction-row">
                      <span className="conv">{c.conviction}/100</span>
                      <span className="size">{c.size_hint || ""}</span>
                      {c.priority_tier && (
                        <span className={`tag ${c.priority_tier === "verified_gap" ? "ok" : c.priority_tier === "unverified" || c.priority_tier === "fade" ? "warn" : ""}`}>
                          {c.priority_tier.replace(/_/g, " ")}
                        </span>
                      )}
                      {c.filing_status === "verified" && <span className="tag ok">Filing ✓</span>}
                      {c.filing_status === "unverified" && <span className="tag warn">Unverified</span>}
                      {c.secondary_confirmed && <span className="tag">2nd wire</span>}
                      {c.oi_change_pct != null && (
                        <span className="tag">OI {c.oi_change_pct >= 0 ? "+" : ""}{c.oi_change_pct.toFixed(0)}%</span>
                      )}
                      {c.deal_summary && <span className="tag warn">{c.deal_summary}</span>}
                    </div>
                  )}
                  {c.filing_url && (
                    <p className="muted" style={{ margin: "0.35rem 0 0" }}>
                      <a href={c.filing_url} target="_blank" rel="noreferrer">
                        NSE filing PDF
                      </a>
                      {c.filing_note ? ` · ${c.filing_note}` : ""}
                    </p>
                  )}
                  {(c.cap_tier || c.prev_day_chg_pct != null || c.sector) && (
                    <div className="mkt-tags muted">
                      {c.cap_tier && <span>{c.cap_tier}</span>}
                      {c.market_cap_cr != null && (
                        <span>₹{Math.round(c.market_cap_cr).toLocaleString("en-IN")} Cr</span>
                      )}
                      {c.prev_day_chg_pct != null && (
                        <span className={c.prev_day_chg_pct >= 0 ? "pos" : "neg"}>
                          prior {c.prev_day_chg_pct >= 0 ? "+" : ""}
                          {c.prev_day_chg_pct}%
                        </span>
                      )}
                      {c.liquidity_tier && <span>liq {c.liquidity_tier}</span>}
                      {c.sector && <span>{c.sector}</span>}
                    </div>
                  )}
                  <p className="why">{c.why}</p>
                  {c.headlines?.length > 0 && (
                    <ul className="heads">
                      {c.headlines.slice(0, 3).map((h) => (
                        <li key={h}>{h}</li>
                      ))}
                    </ul>
                  )}
                  <footer>
                    <span className="muted">{(c.sources || []).slice(0, 3).join(" · ") || "—"}</span>
                    {c.carryover && <span className="tag">Carryover</span>}
                  </footer>
                  {c.risks && <div className="risk">Risk: {c.risks}</div>}
                </article>
              ))}
            </div>

            {showRaw && <pre className="markdown">{latest.markdown}</pre>}
          </>
        )}
      </section>

      <aside className="panel side-panel">
        <h2>History</h2>
        <p className="muted side-hint">Select a past run to review.</p>
        {history.length === 0 && <p className="muted">Empty.</p>}
        {history.map((r) => (
          <button
            key={r.id}
            className={`list-btn ${selectedId === r.id ? "active" : ""}`}
            onClick={() => {
              setSelectedId(r.id);
              if (r.status === "running") {
                setRunning(true);
                setProgress({ pct: r.progress_pct, message: r.progress_message });
              } else {
                setRunning(false);
              }
            }}
          >
            <div className="list-top">
              <strong>#{r.id}</strong>
              <span className={biasClass(r.bias)}>{r.status === "running" ? "Running" : r.bias}</span>
            </div>
            <div className="muted" style={{ fontSize: "0.82rem" }}>
              {formatWhen(r.created_at)} · {r.articles_in_window} arts
              {r.emailed ? " · ✉" : ""}
            </div>
            {r.status === "running" && (
              <div className="mini-track">
                <div className="progress-fill" style={{ width: `${r.progress_pct || 5}%` }} />
              </div>
            )}
          </button>
        ))}
      </aside>
    </div>
  );
}

function PreopenView({ onError }: { onError: (s: string) => void }) {
  const [data, setData] = useState<PreopenWatch | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setBusy(true);
    try {
      setData(await api.preopen());
    } catch (err) {
      onError(err instanceof Error ? err.message : "Pre-open fetch failed");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 20000);
    return () => clearInterval(t);
  }, []);

  const po = data?.preopen;

  return (
    <div className="panel main-panel">
      <div className="manual-bar">
        <div>
          <h2>Pre-open auction</h2>
          <p className="muted">
            Live NSE indicative board (best at 9:00–9:08 IST). Compares against your latest desk note —
            hold, size down, or cancel.
          </p>
        </div>
        <button className="btn primary" disabled={busy} onClick={load}>
          {busy ? "Refreshing…" : "Refresh"}
        </button>
      </div>
      <div className="stats">
        <div className="stat">
          <div className="label">Phase</div>
          <div className="value">{po?.auction_phase || "—"}</div>
        </div>
        <div className="stat">
          <div className="label">GIFT</div>
          <div className={`value ${(po?.gift_change_pct ?? 0) >= 0 ? "pos" : "neg"}`}>
            {po?.gift_last != null ? po.gift_last.toLocaleString("en-IN") : "—"}
            {po?.gift_change_pct != null
              ? ` (${po.gift_change_pct >= 0 ? "+" : ""}${po.gift_change_pct}%)`
              : ""}
          </div>
        </div>
        <div className="stat">
          <div className="label">Adv / Dec</div>
          <div className="value">
            {po?.advances ?? "—"} / {po?.declines ?? "—"}
          </div>
        </div>
        <div className="stat">
          <div className="label">vs report</div>
          <div className="value">#{data?.report_id ?? "—"}</div>
        </div>
      </div>
      {po?.interpretation?.[0] && <p className="muted">{po.interpretation[0]}</p>}
      <h3>Actions vs desk note</h3>
      <table className="data-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Predicted</th>
            <th>Indicative</th>
            <th>Action</th>
            <th>Size</th>
          </tr>
        </thead>
        <tbody>
          {(data?.actions || []).length === 0 && (
            <tr>
              <td colSpan={5} className="muted">
                No matches yet — run a desk fetch first, then refresh here during auction.
              </td>
            </tr>
          )}
          {(data?.actions || []).map((a) => (
            <tr key={a.symbol}>
              <td>{a.symbol}</td>
              <td>{a.predicted}</td>
              <td className={a.indicative_pct >= 0 ? "pos" : "neg"}>
                {a.indicative_pct >= 0 ? "+" : ""}
                {a.indicative_pct.toFixed(2)}%
              </td>
              <td>{a.action}</td>
              <td>{a.size_hint || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {(po?.rows || []).length > 0 && (
        <>
          <h3 style={{ marginTop: "1.2rem" }}>Largest indicative movers</h3>
          <div className="cue-strip">
            {(po?.rows || []).slice(0, 10).map((r) => (
              <span key={r.symbol} className={(r.change_pct ?? 0) >= 0 ? "pos" : "neg"}>
                {r.symbol} {(r.change_pct ?? 0) >= 0 ? "+" : ""}
                {(r.change_pct ?? 0).toFixed(1)}%
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function CalibrationView({ onError }: { onError: (s: string) => void }) {
  const [stats, setStats] = useState<CalibrationStats | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setStats(await api.calibration());
    } catch (err) {
      onError(err instanceof Error ? err.message : "Calibration load failed");
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="panel main-panel">
      <div className="manual-bar">
        <div>
          <h2>Open calibration</h2>
          <p className="muted">
            Each desk run logs predicted opening labels. After ~09:25 IST they settle vs actual open gaps
            so the desk measures its own accuracy.
          </p>
        </div>
        <div className="row">
          <button className="btn" disabled={busy} onClick={() => load()}>
            Refresh
          </button>
          <button
            className="btn primary"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                setMsg((await api.settleCalibration()).message);
                await load();
              } catch (err) {
                onError(err instanceof Error ? err.message : "Settle failed");
              } finally {
                setBusy(false);
              }
            }}
          >
            Settle now
          </button>
        </div>
      </div>
      {msg && <p className="success">{msg}</p>}
      <div className="stats">
        <div className="stat">
          <div className="label">Settled</div>
          <div className="value">{stats?.settled ?? 0}</div>
        </div>
        <div className="stat">
          <div className="label">Hit rate</div>
          <div className="value">
            {stats?.hit_rate != null ? `${Math.round(stats.hit_rate * 100)}%` : "—"}
          </div>
        </div>
        <div className="stat">
          <div className="label">Hits</div>
          <div className="value">{stats?.hits ?? 0}</div>
        </div>
        <div className="stat">
          <div className="label">Avg |open gap|</div>
          <div className="value">{stats?.avg_abs_error_pct != null ? `${stats.avg_abs_error_pct}%` : "—"}</div>
        </div>
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Predicted</th>
            <th>Actual gap</th>
            <th>Hit</th>
            <th>Conviction</th>
            <th>Filing</th>
          </tr>
        </thead>
        <tbody>
          {(stats?.recent || []).length === 0 && (
            <tr>
              <td colSpan={6} className="muted">
                No settled rows yet — run a desk fetch, then settle after the open.
              </td>
            </tr>
          )}
          {(stats?.recent || []).map((r) => (
            <tr key={r.id}>
              <td>{r.symbol}</td>
              <td>{r.predicted}</td>
              <td className={Number(r.actual_gap_pct) >= 0 ? "pos" : "neg"}>
                {r.actual_gap_pct ? `${Number(r.actual_gap_pct) >= 0 ? "+" : ""}${r.actual_gap_pct}%` : "—"}
              </td>
              <td>{r.hit ? "✓" : "✗"}</td>
              <td>{r.conviction || "—"}</td>
              <td>{r.filing_status || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HolidaysView({ onError }: { onError: (s: string) => void }) {
  const [rows, setRows] = useState<Holiday[]>([]);
  const [date, setDate] = useState("");
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [msg, setMsg] = useState("");

  async function load() {
    try {
      setRows(await api.holidays());
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load holidays");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function add(e: FormEvent) {
    e.preventDefault();
    try {
      await api.addHoliday(date, name, notes);
      setDate("");
      setName("");
      setNotes("");
      setMsg("Holiday added");
      await load();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Add failed");
    }
  }

  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>NSE holidays</h2>
        <button
          className="btn"
          onClick={async () => {
            try {
              setMsg((await api.seedHolidays()).message);
              await load();
            } catch (err) {
              onError(err instanceof Error ? err.message : "Seed failed");
            }
          }}
        >
          Seed NSE 2026
        </button>
      </div>
      <p className="muted">Drives previous market close (3:30 PM IST). Weekends always closed.</p>
      {msg && <p className="success">{msg}</p>}
      <form className="row" onSubmit={add} style={{ margin: "1rem 0" }}>
        <input type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
        <input placeholder="Holiday name" required value={name} onChange={(e) => setName(e.target.value)} />
        <input placeholder="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
        <button className="btn primary" type="submit">
          Add
        </button>
      </form>
      <table className="table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Name</th>
            <th>Source</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((h) => (
            <tr key={h.id}>
              <td>{h.holiday_date}</td>
              <td>
                {h.name}
                {h.notes ? <div className="muted">{h.notes}</div> : null}
              </td>
              <td>{h.source}</td>
              <td>
                <button className="btn danger" onClick={async () => { await api.deleteHoliday(h.id); await load(); }}>
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SettingsView({ onError }: { onError: (s: string) => void }) {
  const [settings, setSettings] = useState<DeskSettings | null>(null);
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api
      .getSettings()
      .then(setSettings)
      .catch((err) => onError(err instanceof Error ? err.message : "Settings failed"));
  }, []);

  if (!settings) return <p className="muted">Loading settings…</p>;
  const email = settings.email;

  return (
    <div className="grid-2">
      <section className="panel">
        <h2>Email delivery</h2>
        <label className="check">
          <input
            type="checkbox"
            checked={email.email_enabled}
            onChange={(e) => setSettings({ ...settings, email: { ...email, email_enabled: e.target.checked } })}
          />
          Enable email
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={email.email_on_run}
            onChange={(e) => setSettings({ ...settings, email: { ...email, email_on_run: e.target.checked } })}
          />
          Email after each run (manual + scheduled)
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={settings.use_llm}
            onChange={(e) => setSettings({ ...settings, use_llm: e.target.checked })}
          />
          Use LLM enrichment (Ollama / Groq / Gemini — free keys in .env)
        </label>
        <p className="hint" style={{ marginTop: "-0.5rem", opacity: 0.75, fontSize: "0.85rem" }}>
          Provider is chosen automatically from env. See docs/LLM_DEPLOY.md
        </p>
        <div className="field">
          <label>Recipients</label>
          <input
            value={email.email_to}
            onChange={(e) => setSettings({ ...settings, email: { ...email, email_to: e.target.value } })}
            placeholder="you@gmail.com, partner@gmail.com"
          />
        </div>
        <div className="field">
          <label>SMTP host</label>
          <input
            value={email.smtp_host}
            onChange={(e) => setSettings({ ...settings, email: { ...email, smtp_host: e.target.value } })}
          />
        </div>
        <div className="row">
          <div className="field" style={{ flex: 1 }}>
            <label>Port</label>
            <input
              type="number"
              value={email.smtp_port}
              onChange={(e) =>
                setSettings({ ...settings, email: { ...email, smtp_port: Number(e.target.value || 587) } })
              }
            />
          </div>
          <label className="check" style={{ marginTop: "1.4rem" }}>
            <input
              type="checkbox"
              checked={email.smtp_use_tls}
              onChange={(e) => setSettings({ ...settings, email: { ...email, smtp_use_tls: e.target.checked } })}
            />
            STARTTLS
          </label>
        </div>
        <div className="field">
          <label>SMTP user</label>
          <input
            value={email.smtp_user}
            onChange={(e) => setSettings({ ...settings, email: { ...email, smtp_user: e.target.value } })}
          />
        </div>
        <div className="field">
          <label>SMTP password (blank = keep)</label>
          <input
            type="password"
            value={email.smtp_password}
            onChange={(e) => setSettings({ ...settings, email: { ...email, smtp_password: e.target.value } })}
          />
        </div>
        <div className="field">
          <label>From</label>
          <input
            value={email.smtp_from}
            onChange={(e) => setSettings({ ...settings, email: { ...email, smtp_from: e.target.value } })}
          />
        </div>
        <div className="row">
          <button
            className="btn primary"
            onClick={async () => {
              try {
                const saved = await api.saveSettings(settings);
                setSettings({ ...saved, email: { ...saved.email, smtp_password: "" } });
                const next = formatNextRun(saved.next_run_at);
                setMsg(
                  saved.schedule_enabled
                    ? `Saved · ${describeSchedule(saved.schedule_cron)} · next: ${next}`
                    : "Saved · auto-run off"
                );
              } catch (err) {
                onError(err instanceof Error ? err.message : "Save failed");
              }
            }}
          >
            Save
          </button>
          <button
            className="btn"
            onClick={async () => {
              try {
                setMsg((await api.testEmail()).message);
              } catch (err) {
                onError(err instanceof Error ? err.message : "Test failed");
              }
            }}
          >
            Test email
          </button>
        </div>
        {msg && <p className="success">{msg}</p>}
      </section>

      <section className="panel">
        <h2>Fetch schedule (cron)</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          Auto-fetch Groww news, score catalysts, and email the note on a timer (Asia/Kolkata).
        </p>
        <label className="check">
          <input
            type="checkbox"
            checked={settings.schedule_enabled}
            onChange={(e) => setSettings({ ...settings, schedule_enabled: e.target.checked })}
          />
          Auto-run enabled
        </label>
        <div className={`schedule-box ${settings.schedule_enabled ? "" : "dimmed"}`}>
          <div className="field" style={{ marginBottom: "0.55rem" }}>
            <label>Run time (IST)</label>
            <input
              type="time"
              disabled={!settings.schedule_enabled}
              value={cronToTime(settings.schedule_cron)}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  schedule_cron: buildScheduleCron(e.target.value, cronToDays(settings.schedule_cron)),
                })
              }
            />
          </div>
          <div className="field" style={{ marginBottom: "0.55rem" }}>
            <label>Days</label>
            <div className="day-pills">
              {(
                [
                  ["mon-fri", "Mon–Fri"],
                  ["mon-sat", "Mon–Sat"],
                  ["*", "Every day"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  disabled={!settings.schedule_enabled}
                  className={`chip ${cronToDays(settings.schedule_cron) === key ? "active" : ""}`}
                  onClick={() =>
                    setSettings({
                      ...settings,
                      schedule_cron: buildScheduleCron(cronToTime(settings.schedule_cron), key),
                    })
                  }
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <p className="muted schedule-hint">{describeSchedule(settings.schedule_cron)}</p>
          <p className="schedule-next">
            <strong>Next run:</strong>{" "}
            {settings.schedule_enabled ? formatNextRun(settings.next_run_at) : "— (disabled)"}
          </p>
          <p className="muted" style={{ fontSize: "0.8rem", marginBottom: 0 }}>
            Holidays in the Holidays tab still skip the news window correctly; the job itself fires on these days.
            Click <strong>Save</strong> on the left to apply.
          </p>
        </div>
        <h2 style={{ marginTop: "1.4rem" }}>Security</h2>
        <div className="field">
          <label>Current password</label>
          <input type="password" value={currentPw} onChange={(e) => setCurrentPw(e.target.value)} />
        </div>
        <div className="field">
          <label>New password</label>
          <input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} />
        </div>
        <button
          className="btn"
          onClick={async () => {
            try {
              await api.changePassword(currentPw, newPw);
              setCurrentPw("");
              setNewPw("");
              setMsg("Password updated");
            } catch (err) {
              onError(err instanceof Error ? err.message : "Failed");
            }
          }}
        >
          Update password
        </button>
      </section>
    </div>
  );
}
