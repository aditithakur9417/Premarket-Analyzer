export type Catalyst = {
  symbol: string;
  name: string;
  bias: string;
  event_type: string;
  strength: number;
  opening_impact: string;
  why: string;
  risks: string;
  carryover: boolean;
  sources: string[];
  headlines: string[];
  market_cap_cr?: number | null;
  sector?: string;
  industry?: string;
  prev_day_chg_pct?: number | null;
  cap_tier?: string;
  liquidity_tier?: string;
  tradeability?: string;
  filing_verified?: boolean;
  filing_status?: string;
  filing_note?: string;
  secondary_confirmed?: boolean;
  conviction?: number;
  size_hint?: string;
  conviction_factors?: string[];
  oi_change_pct?: number | null;
  deal_summary?: string;
  filing_url?: string;
  priority_tier?: string;
  priority_rank?: number;
};

export type MarketTape = {
  fetched_at?: string;
  flows?: {
    date?: string;
    fii_net_cr?: number;
    dii_net_cr?: number;
  };
  nifty?: { last?: number; change_pct?: number };
  bank_nifty?: { change_pct?: number };
  india_vix?: { last?: number; change_pct?: number };
  flow_bias?: string;
  volatility_regime?: string;
  interpretation?: string[];
  sector_leaders?: { index?: string; change_pct?: number }[];
};

export type GlobalTape = {
  fetched_at?: string;
  gift_nifty?: {
    last?: number;
    change_pct?: number;
    previous_close?: number;
    implied_gap_vs_nifty_pct?: number | null;
    open_bias?: string;
    expiry?: string;
  };
  cues?: { symbol: string; name: string; last?: number; change_pct?: number | null }[];
  us_futures_bias?: string;
  asia_bias?: string;
  fx_bias?: string;
  commodity_bias?: string;
  composite_risk?: string;
  implied_nifty_open_pct?: number | null;
  interpretation?: string[];
};

export type ReportPayload = {
  generated_at?: string;
  cutoff?: string;
  feed_stats?: Record<string, unknown>;
  ignored_count?: number;
  market_tape?: MarketTape;
  global_tape?: GlobalTape;
  precision?: {
    filings_scanned?: number;
    filings_verified?: number;
    secondary?: { confirmed?: number; top_checked?: number; source?: string };
    adr_tape?: { composite_pct?: number; it_bias?: string; banks_bias?: string; interpretation?: string[] };
    event_context?: { regime?: string; interpretation?: string[] };
    fo_overlay?: { fo_bias?: string; interpretation?: string[] };
    fo_flow?: { nifty_oi_chg_pct?: number; fo_bias?: string; interpretation?: string[] };
    deals?: { bulk_count?: number; block_count?: number; as_on?: string };
    preopen?: { auction_phase?: string; gift_last?: number };
  };
  market_view?: {
    bias?: string;
    confidence?: number;
    reasons?: string[];
    opportunity?: string;
    risk?: string;
  };
  catalysts?: Catalyst[];
};

const API = "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  if (!text || text === "null") return null as T;
  return JSON.parse(text) as T;
}

export type Me = { ok: boolean; username: string; is_admin: boolean };
export type Holiday = {
  id: number;
  holiday_date: string;
  name: string;
  source: string;
  notes: string;
};
export type ReportSummary = {
  id: number;
  created_at: string;
  cutoff_iso: string;
  bias: string;
  confidence: number;
  articles_in_window: number;
  unique_stocks: number;
  emailed: boolean;
  used_llm: boolean;
  status: string;
  progress_pct: number;
  progress_message: string;
};
export type ReportDetail = ReportSummary & {
  markdown: string;
  payload: ReportPayload;
};
export type DeskSettings = {
  use_llm: boolean;
  schedule_enabled: boolean;
  schedule_cron: string;
  next_run_at?: string | null;
  email: {
    smtp_host: string;
    smtp_port: number;
    smtp_user: string;
    smtp_password: string;
    smtp_from: string;
    smtp_use_tls: boolean;
    email_to: string;
    email_enabled: boolean;
    email_on_run: boolean;
  };
};

export const api = {
  me: () => request<Me>("/api/auth/me"),
  login: (username: string, password: string) =>
    request<Me>("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  logout: () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST", body: "{}" }),
  changePassword: (current_password: string, new_password: string) =>
    request("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
    }),
  holidays: () => request<Holiday[]>("/api/holidays"),
  addHoliday: (holiday_date: string, name: string, notes = "") =>
    request<Holiday>("/api/holidays", {
      method: "POST",
      body: JSON.stringify({ holiday_date, name, notes }),
    }),
  deleteHoliday: (id: number) => request(`/api/holidays/${id}`, { method: "DELETE" }),
  seedHolidays: () => request<{ message: string }>("/api/holidays/seed-nse-2026", { method: "POST", body: "{}" }),
  reports: () => request<ReportSummary[]>("/api/reports"),
  latestReport: () => request<ReportDetail>("/api/reports/latest"),
  activeRun: () => request<ReportDetail | null>("/api/reports/active"),
  getReport: (id: number) => request<ReportDetail>(`/api/reports/${id}`),
  runReport: (opts?: { use_llm?: boolean; send_email?: boolean }) =>
    request<ReportDetail>("/api/reports/run", { method: "POST", body: JSON.stringify(opts || {}) }),
  emailReport: (id: number) =>
    request<{ message: string }>(`/api/reports/${id}/email`, { method: "POST", body: "{}" }),
  downloadPdf: async (id: number) => {
    const res = await fetch(`/api/reports/${id}/pdf`, { credentials: "include" });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail || detail;
      } catch {
        /* ignore */
      }
      throw new Error(typeof detail === "string" ? detail : "PDF download failed");
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `premarket-desk-${id}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
  getSettings: () => request<DeskSettings>("/api/settings"),
  saveSettings: (body: DeskSettings) =>
    request<DeskSettings>("/api/settings", { method: "PUT", body: JSON.stringify(body) }),
  testEmail: () => request<{ message: string }>("/api/settings/test-email", { method: "POST", body: "{}" }),
  calibration: () => request<CalibrationStats>("/api/calibration"),
  settleCalibration: () =>
    request<{ message: string }>("/api/calibration/settle", { method: "POST", body: "{}" }),
  preopen: () => request<PreopenWatch>("/api/preopen"),
};

export type PreopenWatch = {
  report_id?: number | null;
  preopen?: {
    auction_phase?: string;
    market_status?: string;
    gift_last?: number;
    gift_change_pct?: number;
    advances?: number;
    declines?: number;
    unchanged?: number;
    interpretation?: string[];
    matched?: { symbol: string; change_pct?: number; iep?: number }[];
    rows?: { symbol: string; change_pct?: number; iep?: number }[];
  };
  actions?: {
    symbol: string;
    predicted: string;
    indicative_pct: number;
    iep?: number;
    action: string;
    conviction?: number;
    size_hint?: string;
  }[];
};

export type CalibrationStats = {
  settled?: number;
  hits?: number;
  hit_rate?: number | null;
  avg_abs_error_pct?: number | null;
  by_label?: Record<string, { n: number; hits: number }>;
  recent?: {
    id: number;
    symbol: string;
    predicted: string;
    actual_gap_pct: string;
    actual_label: string;
    hit: boolean;
    conviction: number;
    filing_status: string;
    created_at: string;
  }[];
};
