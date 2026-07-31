# Accuracy upgrades (Jul 2026)

Priority-ordered improvements shipped for the institutional desk.

## P0 — Recall & trust
- **NSE filings → catalysts** when Groww misses the story (`discover_catalysts_from_filings`)
- **Semantic filing verify** — subject must match event type (no more fake Filing ✓)
- **Unverified needs_filing** always haircut (not only top-N)
- **LLM lock** — cannot restore Gap Up/Down on unverified filings
- **False-positive cuts** — bare “approval/clears” removed; soft-close noise without hard catalyst dropped
- **Carryover fixed** — only 14:30–15:30; post-close news is fresh overnight
- **Calibration honesty** — Gap Up hit needs ≥+1.5%; MAE vs expected midpoint
- **Holiday skip** — Actions + local scheduler + `manual_run` (use `--force` to override)

## P1 — Ranking & direction
- **Best-first priority tiers**: `verified_gap` → `verified_strong` → `high_move` → `watch` → `fade` / `unverified`
- Desk UI chips: **Best first**, Verified gaps, Fade risk, Unverified
- **Fundraising direction** — discount / OFS / rights → bearish or neutral, not always long
- **Entity map** expanded (SML Mahindra, BEL, HAL, etc.)
- **Secondary wire** tighter name match (≥2 tokens)
- **1.0R size** requires verified filing + liquidity
- **NSE filing PDF** link on cards

## Ops
- Morning GitHub Action skips weekends/NSE holidays
- Push this branch so Actions picks up the new logic
