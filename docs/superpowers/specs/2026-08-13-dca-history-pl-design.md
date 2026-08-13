# DCA History And P/L Dashboard Design

## Goal

Add a household-readable DCA pair status, completed order history, and estimated P/L view to the authenticated web dashboard.

## Audience

The dashboard should be understandable to a non-technical household or team member. Labels should explain what happened in plain terms: money spent, coins bought, average buy price, current estimated value, and estimated gain/loss. Avoid making the user understand accounting terms before they can read the screen.

## P/L Model

Completed CSV orders are the source of truth for buying history. They can show what the bot has actually done: completed buys, fees, total cash spent, coins accumulated, average buy price, and the time of the latest buy.

Live Kraken prices are required for current estimated P/L. Estimated P/L is calculated as current Kraken price multiplied by accumulated volume, minus total spent. This is not realized profit, tax reporting, or a promise of executable sale value. The UI must label it as an estimate and continue to work when live price fetching is unavailable.

## Scope

- Add backend parsing and aggregation for the configured orders CSV.
- Add authenticated web API output for order entries, per-pair summaries, portfolio totals, chart points, and live valuation status.
- Add a frontend history store and dashboard components for pair status, P/L chart, and order history.
- Preserve existing config editing, scheduler controls, auth behavior, and manual-run behavior.
- Do not expose unauthenticated filesystem paths or raw private config data.

## Backend Design

Create a focused history module that reads order CSV rows into typed records and aggregates them by pair. Missing files return empty history. Malformed headers or invalid numeric rows should return a clear API error or row-level warning, depending on whether the file can still be safely interpreted.

History path resolution should use the same configuration ownership model as the runner: the configured `orders_filepath` is a relative CSV filename and should resolve from the active config file directory. Pair-level `orders_filepath` overrides the top-level file when present.

The history API should be read-only and authenticated. It should avoid placing market data calls on the critical dashboard path in a way that can break the whole page. If Kraken live prices fail, the API returns CSV-derived history with `valuation.status = "unavailable"` and a short message.

## Frontend Design

Use Hallmark as a Stat-Led dashboard addition inside the existing dark modern design system. The first dashboard screen should lead with a compact money snapshot:

- You spent
- You bought
- Worth now
- Estimated gain/loss

Below that, show pair-level rows or tiles that explain whether each DCA pair is active, paused, running, or waiting for the next scheduled buy. Each pair should expose last buy, next run, buys completed, average buy price, and estimated gain/loss when live price is available.

The P/L chart should default to an easy comparison: money spent versus estimated current value. When live price is unavailable, it should fall back to a buying-history chart so the user can still understand accumulation over time.

The history table should show newest completed orders first, with expandable details for exact fee, txid, timestamp, and price. Use dark table rows, plain column labels, and restrained green/red money indicators.

## Hallmark Direction

- Macrostructure: Stat-Led
- Genre: modern-minimal operational dashboard
- Theme: existing project dark technical tokens
- Enrichment: data visualization only
- Copy rule: no invented metrics; use API values or explicit empty states
- Tone: calm, precise, readable to non-technical users

## Risks And Constraints

Live estimated P/L depends on current Kraken pricing and pair metadata. The implementation should make this optional at the API-response level so dashboard history is not blocked by market data errors.

CSV order history may contain only buy orders from the bot. The dashboard should not claim whole-account portfolio value unless it can prove the data includes sells, transfers, and balances. The first release should describe the data as "from completed bot orders."

GitNexus impact analysis is required before editing existing functions, classes, methods, Vue component methods, or API route handlers.

## Verification

- Backend parser and aggregation tests.
- Authenticated history API tests.
- Frontend API/store/component tests.
- Full Python test suite for touched backend areas.
- Full frontend Vitest run and production build.
- GitNexus change detection before any commit or final handoff.
