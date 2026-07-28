# Institutional Pre-Market Desk — Research Framework

This document explains **what professional desks look at beyond headlines**, how Indian markets behave around the open, and how this app layers real data on top of news catalysts.

---

## 1. What the desk already does (news layer)

| Step | What happens |
|------|----------------|
| **Window** | News since **previous NSE cash close** (3:30 PM IST), not calendar midnight |
| **Ingest** | Groww public feed, paginated (`size=25`) until cutoff |
| **Filter** | Drops technical picks, dividend reminders, pure price recaps |
| **Classify** | Earnings beat/miss, order wins, regulatory, M&A, broker notes |
| **Dedupe** | One catalyst per symbol; peer spillover handled separately |
| **Score** | 1–5 strength + opening impact (Gap Up Likely → Watch for Fade) |
| **Sell-the-news** | Late prints, mixed-quality beats, already-moved headlines |

**Limitation:** News alone cannot tell you if a stock **already ran 12%** yesterday or if **FII sold ₹2,000 Cr** into the close.

---

## 2. Market tape layer (now integrated)

Fetched each run from **live NSE APIs** + **Yahoo Finance** for stock metadata.

### 2.1 FII / DII cash flows (`nseindia.com/api/fiidiiTradeReact`)

- **FII net** — foreign institutional cash-market buy minus sell (₹ Cr)
- **DII net** — domestic institutions (mutual funds, insurers, etc.)

**How desks read it (India-specific):**

| Pattern | Typical interpretation |
|---------|------------------------|
| FII +, DII − | Foreign buying; domestic profit-booking — **risk-on if sustained** |
| FII −, DII + | Classic support bid when foreigners sell — **index may hold, breadth mixed** |
| Both + | Strong risk appetite — **gap-ups more likely to hold** |
| Both − | Risk-off — **fade aggressive long gaps** |

*Example (21 Jul 2026 session):* FII net **+1,650 Cr**, DII net **−656 Cr** → FII buying / DII booking.

### 2.2 Index context (`/api/allIndices`)

- **Nifty 50** — broad market tone for the next open
- **Bank Nifty** — financials often set opening sentiment (rate path, credit)
- **Sector indices** — which themes already moved (align catalysts with tape)

Prior close **−0.79%** on Nifty means bullish **stock-specific** gaps face **index headwind**.

### 2.3 India VIX

- **< 12** — complacent; gaps can extend but reversals are sharp when they come
- **12–16** — normal regime
- **> 16 or rising fast** — elevated fear; **mid/small-cap gap-ups fade more often**

*Example:* VIX **13.29** (+5.5% d/d) → normal-to-elevating; size down on thin names.

## 2.4 GIFT Nifty + global cues (Phase B — integrated)

**GIFT Nifty** (NSE International Exchange index futures, near month) is the single best free official guide to the cash open while NSE is closed.

| Source | What we pull |
|--------|----------------|
| `nseix.com/api/niccl-graph-headers` | Near-month GIFT last, prev close, OHLC, % |
| Yahoo Finance | ES/NQ/YM futures, Nikkei, Hang Seng, WTI, Gold, USDINR, DXY |

**How the desk uses it**

| GIFT vs cash Nifty | Typical open |
|--------------------|--------------|
| ≥ +0.7% | Strong gap up |
| +0.25% to +0.7% | Gap up |
| −0.25% to +0.25% | Flat |
| ≤ −0.25% | Gap down / strong gap down |

**Accuracy rules wired into scoring**

1. GIFT risk-off + bullish mid/small catalyst → downgrade Gap Up → Mild Positive  
2. GIFT risk-on + bearish large-cap → soften Gap Down Risk  
3. Crude ±2% → energy vs airlines/paint sector flags  
4. USDINR move → IT/exporter vs importer notes  
5. Confidence rises when **news bias and GIFT align**; falls when they conflict  

**Composite risk** blends GIFT gap with US futures, Asia, and FX into: Risk-On / Mild Risk-On / Neutral / Mild Risk-Off / Risk-Off.

---

## 2.5 GIFT Nifty (legacy note)

Pre-open **6:30 AM–3:40 PM** and evening session on NSE IX. Strong correlation with cash open.  
**Status:** ✅ Wired via NSE IX public APIs (not Yahoo proxies).

## 3. Stock-level factors (now on each catalyst card)

| Field | Source | Why it matters |
|-------|--------|----------------|
| **Market cap tier** | Yahoo `marketCap` | Large caps gap more cleanly; micro-caps gap and reverse violently |
| **Prior day %** | Yahoo daily history | **Sell-the-news:** +8% into an earnings headline → fade risk |
| **Avg volume** | Yahoo | Liquidity = can you get out at 9:15–9:30? |
| **Sector / industry** | Yahoo | Sector already hot/cold on index tape |

**Cap tiers (approximate):**

- Large: > ₹1,00,000 Cr  
- Mid: ₹20,000–1,00,000 Cr  
- Small: ₹5,000–20,000 Cr  
- Micro: < ₹5,000 Cr  

**Liquidity tiers (avg daily volume):**

- High: > 1M shares  
- Medium: 250K–1M  
- Low: 75K–250K  
- Thin: < 75K  

---

## 4. Behavioural patterns (research-backed heuristics)

### 4.1 Opening auction (9:00–9:08 IST)

- Price discovery from **limit orders**; no continuous trading  
- **Large gaps** on illiquid names often **partially fill** in first 15 minutes  
- Catalyst strength ≠ opening print if stock already moved in prior session

### 4.2 Sell-the-news

Common when:

1. Headline says “stock surges X%” **in the same window** as the catalyst  
2. Earnings beat but **geo/margin hedges** in body copy  
3. **Carryover** from 14:30–15:30 prior day — institutions already positioned  

→ Desk label: **Watch for Fade** (not “avoid”, but **smaller size / wait for base**)

### 4.3 Gap-and-go vs gap-and-fade

| Favours follow-through | Favours fade |
|------------------------|--------------|
| Fresh catalyst after 6 PM | Prior session already +5–10% |
| FII net buying day | Elevated VIX |
| Large cap + high liquidity | Thin mid-cap + broker note only |
| Order win / regulatory | Mixed-quality earnings beat |

### 4.4 Sector rotation

If **Defence / PSU Banks** led prior session and your catalyst is **same sector**, move may be **crowded**.  
If catalyst is **contrarian sector** on a weak tape, gap may be **muted** even with good news.

### 4.5 Event calendar (not yet in app)

- **RBI policy**, **US CPI/Fed**, **Budget**, **expiry week** (monthly F&O)  
- On event days, **stock-specific gaps mean less** — macro dominates first 30 min

---

## 5. What institutional desks add that we don’t (yet)

| Factor | Status | Priority |
|--------|--------|----------|
| GIFT Nifty / SGX implied open | ✅ Phase B | — |
| US futures / Asia / crude / USDINR | ✅ Phase B | — |
| NSE/BSE **exchange filings** (Tier-A) | Planned | High |
| **F&O** OI, PCR, max pain | Not started | High for F&O names |
| **Delivery %** / bulk-block with identity | Partial (news only) | Medium |
| **Promoter pledge** / shareholding | Not started | Medium |
| **Peer relative performance** (vs sector ETF) | Not started | Medium |
| **Backtest** predicted vs actual open | Not started | High for calibration |
| **Global cues** (US futures, crude, USDINR) | Not started | Medium |
| **Nexus / Groww live quote** at 8:15 | Optional integration | Medium |

---

## 6. How scoring is adjusted with real data

After news scoring, `apply_market_overlay()`:

1. **Prior day +6%** on bullish name → downgrade Gap Up → **Watch for Fade**  
2. **Thin liquidity** → strength −1, slippage warning  
3. **Micro-cap** → strength −1  
4. **Elevated VIX** → mid/small Gap Up → **Mild Positive**  

`adjust_market_view()` blends index + flows into **confidence** and **reasons**.

---

## 7. Data sources & reliability

| Source | Endpoint / tool | Notes |
|--------|-----------------|-------|
| Groww | `feed/public?publisherId=stocknewssummary` | Primary news; no date filter |
| NSE | `fiidiiTradeReact`, `allIndices` | Requires session cookie; prior session |
| Yahoo | `yfinance` `.NS` tickers | EOD cap/volume; 30s batch latency |
| Local LLM | Ollama `qwen2.5:7b` | Optional narrative polish |

**Always verify** material events on [NSE announcements](https://www.nseindia.com/companies-listing/corporate-filings-announcements) before sizing.

---

## 8. Suggested morning workflow

1. **08:00** — Check GIFT Nifty, USDINR, crude (manual for now)  
2. **08:15** — Run Premarket Desk (this app)  
3. Read **Market tape** → sets index bias  
4. Scan **bullish cards** with **prior %** and **liquidity**  
5. Cross-check top 3 names on **exchange filings**  
6. **09:00** — Place auction limits; avoid market orders on thin names  
7. **09:20** — Re-evaluate: gap held or fading?  

---

## 9. Calibration examples (22 Jul 2026)

| Symbol | News signal | Real tape | Desk outcome |
|--------|-------------|-----------|--------------|
| **M&MFIN** | Bullish, upgrade + earnings | Prior **+8.1%**, mid-cap | Gap likely **already partly priced** — trail stops |
| **INDHOTEL** | Beat but hedges | Prior **−0.9%**, large cap | **Watch for Fade** — mixed quality |
| **DATAPATTNS** | Order / defence theme | Prior **+12.7%** | **Sell-the-news** unless fresh filing after close |

---

## 10. Roadmap

1. **Phase A** ✅ — FII/DII, indices, VIX, cap/liquidity/prior move  
2. **Phase B** ✅ — GIFT Nifty (NSE IX) + global futures strip in report/scoring  
3. **Phase C** ✅ — NSE filing cross-check + secondary Moneycontrol wire  
4. **Phase D** ✅ — Open calibration (log predictions, settle vs actual open, hit rate UI)  
5. **Also shipped** — India ADRs, event regime, FO/VIX fear overlay, conviction 0–100 + size hints  
6. **Auction / FO flow** ✅ — Pre-open watch tab, Nifty OI spurts, named bulk/block deals  
7. **Phase E** — Nexus Market OS bridge for live quotes   

---

*This is a research assistant, not investment advice. Past behaviour does not guarantee future opens.*
