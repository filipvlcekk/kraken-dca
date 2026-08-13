# DCA History And P/L Dashboard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a household-readable DCA pair status, completed order history, and estimated P/L dashboard.

**Architecture:** Add a backend history module that parses completed CSV orders, aggregates them by configured DCA pair, and optionally enriches summaries with live Kraken ticker prices. Expose the data through authenticated FastAPI routes, then add Vue store and dashboard components that render pair status, chart points, and order history using the existing dark Hallmark token system.

**Tech Stack:** Python, FastAPI, pytest, Vue 3, TypeScript, Vitest, native SVG charting, existing Kraken client and scheduler APIs.

---

## Chunk 1: Backend History Model

### Task 1: Add CSV History Parser

**Files:**
- Create: `krakendca/order_history.py`
- Test: `tests/test_order_history.py`

- [ ] **Step 1: Run GitNexus impact analysis**

Run `gitnexus_impact({target: "Order", direction: "upstream"})`.
Expected: low or medium risk from read-only reuse of existing order field names. Warn the user before proceeding if the result is high or critical.

- [ ] **Step 2: Write failing parser test**

Create `tests/test_order_history.py` with a test that writes a valid orders CSV and asserts entries are sorted newest first with parsed `pair`, `date`, `volume`, `price`, `fee`, `total_price`, and `txid`.

Run: `.venv/bin/python -m pytest tests/test_order_history.py::test_load_order_history_returns_entries_newest_first -v`
Expected: FAIL because `krakendca.order_history` does not exist.

- [ ] **Step 3: Implement parser dataclasses and loader**

Create `OrderHistoryEntry` and `load_order_history(path: Path) -> list[OrderHistoryEntry]`. Return an empty list when the file does not exist.

- [ ] **Step 4: Verify parser test passes**

Run: `.venv/bin/python -m pytest tests/test_order_history.py::test_load_order_history_returns_entries_newest_first -v`
Expected: PASS.

### Task 2: Add Per-Pair Aggregation

**Files:**
- Modify: `krakendca/order_history.py`
- Modify: `tests/test_order_history.py`

- [ ] **Step 1: Write failing aggregation test**

Add a test that loads multiple buys across two pairs and asserts each pair summary contains trade count, total volume, total spent, total fees, average buy price, and last trade date.

Run: `.venv/bin/python -m pytest tests/test_order_history.py::test_summarize_order_history_groups_by_pair -v`
Expected: FAIL because summary code does not exist.

- [ ] **Step 2: Implement aggregation**

Add `OrderHistorySummary`, `PortfolioHistorySummary`, and `summarize_order_history(entries)` using `Decimal` for money and volume math.

- [ ] **Step 3: Verify aggregation test passes**

Run: `.venv/bin/python -m pytest tests/test_order_history.py::test_summarize_order_history_groups_by_pair -v`
Expected: PASS.

### Task 3: Add Chart Point Builder

**Files:**
- Modify: `krakendca/order_history.py`
- Modify: `tests/test_order_history.py`

- [ ] **Step 1: Write failing chart test**

Add a test that asserts chart points accumulate spent cash and coin volume over chronological order dates.

Run: `.venv/bin/python -m pytest tests/test_order_history.py::test_build_history_chart_accumulates_completed_buys -v`
Expected: FAIL because chart builder code does not exist.

- [ ] **Step 2: Implement chart builder**

Add `build_history_chart(entries)` returning chronological points with date, cumulative spent, cumulative volume, and pair.

- [ ] **Step 3: Verify chart test passes**

Run: `.venv/bin/python -m pytest tests/test_order_history.py::test_build_history_chart_accumulates_completed_buys -v`
Expected: PASS.

## Chunk 2: Authenticated History API

### Task 4: Add Web Route

**Files:**
- Create: `krakendca/web/routes_history.py`
- Modify: `krakendca/web/app.py`
- Modify: `krakendca/web/schemas.py`
- Modify: `tests/test_web_api.py`

- [ ] **Step 1: Run GitNexus impact analysis**

Run upstream impact checks for `create_app`, `ok`, and any serializer function modified in `krakendca/web/schemas.py`.
Expected: low to medium risk; warn the user before proceeding if any result is high or critical.

- [ ] **Step 2: Write failing auth/API test**

Add a test proving `GET /api/history` requires authentication and an authenticated request returns empty entries when the CSV file is missing.

Run: `.venv/bin/python -m pytest tests/test_web_api.py::test_history_requires_authentication tests/test_web_api.py::test_history_returns_empty_state_for_missing_orders_file -v`
Expected: FAIL because the route does not exist.

- [ ] **Step 3: Implement route and wire router**

Add `create_history_router(config_path: str)` or equivalent local pattern. Load normalized config, resolve configured order CSV filenames relative to the config file directory, call history helpers, and serialize a response:

```json
{
  "entries": [],
  "pairs": [],
  "portfolio": {},
  "chart": [],
  "valuation": {"status": "not_configured"}
}
```

- [ ] **Step 4: Verify auth/API tests pass**

Run: `.venv/bin/python -m pytest tests/test_web_api.py::test_history_requires_authentication tests/test_web_api.py::test_history_returns_empty_state_for_missing_orders_file -v`
Expected: PASS.

### Task 5: Add API Data Test

**Files:**
- Modify: `tests/test_web_api.py`
- Modify: `krakendca/web/routes_history.py`
- Modify: `krakendca/web/schemas.py`

- [ ] **Step 1: Write failing populated-history test**

Add a test that writes a config and CSV, logs in, calls `/api/history`, and asserts pair summary, portfolio totals, entries, and chart points are present.

Run: `.venv/bin/python -m pytest tests/test_web_api.py::test_history_returns_completed_order_summary -v`
Expected: FAIL until serialization matches the contract.

- [ ] **Step 2: Complete serialization**

Return JSON-safe strings for `Decimal` values and ISO timestamps for dates. Keep labels in frontend, not backend.

- [ ] **Step 3: Verify populated-history test passes**

Run: `.venv/bin/python -m pytest tests/test_web_api.py::test_history_returns_completed_order_summary -v`
Expected: PASS.

## Chunk 3: Live Valuation

### Task 6: Add Optional Kraken Price Enrichment

**Files:**
- Modify: `krakendca/order_history.py`
- Modify: `krakendca/web/routes_history.py`
- Modify: `tests/test_order_history.py`
- Modify: `tests/test_web_api.py`

- [ ] **Step 1: Run GitNexus impact analysis**

Run upstream impact checks for any existing Kraken client method used for ticker prices, likely `get_ticker_info`.
Expected: low or medium risk because usage is additive and read-only.

- [ ] **Step 2: Write failing valuation test**

Add a unit test that passes summaries plus mocked current prices and asserts estimated value and estimated gain/loss are calculated correctly.

Run: `.venv/bin/python -m pytest tests/test_order_history.py::test_apply_live_prices_calculates_estimated_pl -v`
Expected: FAIL because valuation code does not exist.

- [ ] **Step 3: Implement valuation helper**

Add a pure helper such as `apply_live_prices(summaries, prices)` that computes current value and estimated P/L without making network calls.

- [ ] **Step 4: Verify pure valuation test passes**

Run: `.venv/bin/python -m pytest tests/test_order_history.py::test_apply_live_prices_calculates_estimated_pl -v`
Expected: PASS.

- [ ] **Step 5: Add route-level fallback test**

Add a web API test using a fake price provider that raises an error and assert history still returns with `valuation.status = "unavailable"`.

Run: `.venv/bin/python -m pytest tests/test_web_api.py::test_history_keeps_csv_data_when_live_prices_fail -v`
Expected: FAIL until route handles fallback.

- [ ] **Step 6: Implement route fallback**

Fetch current pair prices only after CSV summaries are built. Catch client errors and return the CSV response with valuation unavailable.

- [ ] **Step 7: Verify route fallback test passes**

Run: `.venv/bin/python -m pytest tests/test_web_api.py::test_history_keeps_csv_data_when_live_prices_fail -v`
Expected: PASS.

## Chunk 4: Frontend Data Layer

### Task 7: Add History API Client And Store

**Files:**
- Modify: `frontend/src/api.ts`
- Create: `frontend/src/historyStore.ts`
- Test: `frontend/src/__tests__/api.test.ts`
- Create: `frontend/src/__tests__/historyStore.test.ts`

- [ ] **Step 1: Run GitNexus impact analysis**

Run upstream impact checks for `apiRequest` and any exported frontend API helpers modified.
Expected: low risk if only additive types and helper are added.

- [ ] **Step 2: Write failing API helper test**

Add a test proving `loadHistory()` fetches `/api/history` and returns typed data.

Run: `npm test -- --run src/__tests__/api.test.ts` from `frontend/`.
Expected: FAIL because `loadHistory` does not exist.

- [ ] **Step 3: Implement API types and helper**

Add `HistoryEntry`, `PairHistorySummary`, `PortfolioHistorySummary`, `HistoryChartPoint`, `HistoryResponse`, and `loadHistory()`.

- [ ] **Step 4: Verify API helper test passes**

Run: `npm test -- --run src/__tests__/api.test.ts` from `frontend/`.
Expected: PASS.

- [ ] **Step 5: Write failing store test**

Create a test for a history store composable that loads data, tracks loading/error state, and exposes a refresh method.

Run: `npm test -- --run src/__tests__/historyStore.test.ts` from `frontend/`.
Expected: FAIL because `historyStore.ts` does not exist.

- [ ] **Step 6: Implement history store**

Add `createHistoryStore()` following existing `schedulerStore.ts` patterns.

- [ ] **Step 7: Verify store test passes**

Run: `npm test -- --run src/__tests__/historyStore.test.ts` from `frontend/`.
Expected: PASS.

## Chunk 5: Frontend Components

### Task 8: Add Snapshot, Pair Status, Chart, And Table Components

**Files:**
- Create: `frontend/src/components/PortfolioSnapshot.vue`
- Create: `frontend/src/components/PairStatusPanel.vue`
- Create: `frontend/src/components/ProfitLossChart.vue`
- Create: `frontend/src/components/OrderHistoryTable.vue`
- Create: component tests under `frontend/src/__tests__/`

- [ ] **Step 1: Write failing snapshot test**

Test that plain labels render: "You spent", "You bought", "Worth now", and "Estimated gain/loss".

Run: `npm test -- --run src/__tests__/portfolioSnapshot.test.ts` from `frontend/`.
Expected: FAIL because component does not exist.

- [ ] **Step 2: Implement snapshot component**

Render compact stat cells using existing dark tokens and empty-state handling for unavailable valuation.

- [ ] **Step 3: Write failing pair status test**

Test active, paused, running, and next-run labels using scheduler job plus history summary props.

Run: `npm test -- --run src/__tests__/pairStatusPanel.test.ts` from `frontend/`.
Expected: FAIL because component does not exist.

- [ ] **Step 4: Implement pair status component**

Render pair rows with buys completed, last buy, average buy price, next run, and estimated gain/loss.

- [ ] **Step 5: Write failing chart test**

Test that the chart renders an SVG, accessible title, and fallback copy when there are no chart points.

Run: `npm test -- --run src/__tests__/profitLossChart.test.ts` from `frontend/`.
Expected: FAIL because component does not exist.

- [ ] **Step 6: Implement chart component**

Use native SVG paths for money spent and estimated value. Use stable dimensions and responsive constraints.

- [ ] **Step 7: Write failing table test**

Test newest-first rows, exact order detail expansion, and empty state.

Run: `npm test -- --run src/__tests__/orderHistoryTable.test.ts` from `frontend/`.
Expected: FAIL because component does not exist.

- [ ] **Step 8: Implement table component**

Render dense dark rows, accessible expand buttons, and detail rows for txid, fee, price, and timestamp.

## Chunk 6: Dashboard Integration

### Task 9: Wire History Into Dashboard

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/__tests__/app.test.ts`
- Possibly modify: `frontend/src/components/SchedulerStatus.vue`

- [ ] **Step 1: Run GitNexus impact analysis**

Run upstream impact checks for edited `App.vue` methods such as `loadDashboard`, `handleLogin`, `saveConfig`, `reloadScheduler`, and `runPairNow`.
Expected: low UI-local risk.

- [ ] **Step 2: Write failing integration test**

Extend the app test so an authenticated dashboard loads `/api/history` and renders snapshot/history areas.

Run: `npm test -- --run src/__tests__/app.test.ts` from `frontend/`.
Expected: FAIL because dashboard does not load or render history yet.

- [ ] **Step 3: Integrate store and components**

Load history alongside config and scheduler after login. Refresh history after manual runs, config saves, and scheduler reloads.

- [ ] **Step 4: Verify integration test passes**

Run: `npm test -- --run src/__tests__/app.test.ts` from `frontend/`.
Expected: PASS.

## Chunk 7: Verification And Review

### Task 10: Full Verification

**Files:**
- No additional edits expected.

- [ ] **Step 1: Run backend tests**

Run: `.venv/bin/python -m pytest tests/test_order_history.py tests/test_web_api.py -v`
Expected: PASS.

- [ ] **Step 2: Run frontend tests**

Run: `npm test -- --run` from `frontend/`.
Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run: `npm run build` from `frontend/`.
Expected: PASS.

- [ ] **Step 4: Run GitNexus change detection**

Run `gitnexus_detect_changes({scope: "all"})`.
Expected: affected scope is limited to order history, web API, and dashboard UI flows.

- [ ] **Step 5: Manual preview**

Open the authenticated dashboard and confirm the first screen uses household-readable labels and the history/chart states remain legible in the dark Hallmark design at desktop and mobile widths.
