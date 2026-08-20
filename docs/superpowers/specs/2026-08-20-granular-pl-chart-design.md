# Granular P/L Chart Design

## Goal

Replace the current simple SVG buying-history chart with a more granular time-based P/L chart similar to Kraken's rule history view. The first implementation should use Chart.js, show trade-level P/L over time, and leave the API contract ready for a later historically accurate Kraken OHLC-based P/L curve.

## Chosen Approach

Use current live Kraken price data to enrich every history chart point with estimated value and estimated P/L:

`estimated_pl = cumulative_volume * current_price - cumulative_spent`

This answers: "What would the P/L have been after each completed buy if today's price applied at that point?" It is useful for understanding accumulation and cost basis without adding historical market-data fetching, caching, and rate-limit handling in the first pass.

The chart must label this as estimated current-price P/L, not historically exact P/L.

## Future-Compatible Chart Contract

Extend `HistoryChartPoint` in backend and frontend types with valuation fields:

```ts
type HistoryChartPoint = {
  date: string
  pair: string
  txid: string
  spent: string
  volume: string
  cumulative_spent: string
  cumulative_volume: string
  current_price: string | null
  estimated_value: string | null
  estimated_pl: string | null
  historical_price: string | null
  historical_value: string | null
  historical_pl: string | null
}
```

For this iteration, `historical_*` fields are always `null`. A future Kraken OHLC implementation can populate them without replacing the frontend component contract.

## Backend Design

Keep completed CSV orders as the source of truth. `build_history_chart()` continues to produce chronological accumulation points. After live pair prices are fetched, the history route enriches those points with the current price, estimated value, and estimated P/L.

If live prices are unavailable, the chart points still return with their accumulation fields and all valuation fields set to `null`. The route keeps the existing `valuation.status = "unavailable"` behavior so the frontend can fall back gracefully.

Historical fields should be serialized as `null` placeholders. They are intentionally present in the contract so a later OHLC feature can be additive.

## Frontend Design

Replace the hand-drawn SVG in `ProfitLossChart.vue` with a Chart.js canvas chart.

The chart should default to `Trades`, showing one point per completed order. Range controls should include `Trades`, `1D`, `7D`, `1M`, and `All`. In this first iteration, ranges filter by date; bucketing and daily/weekly aggregation can follow later if real histories become too dense.

The primary display should include:

- P/L amount and percentage relative to cumulative spent.
- A zero axis.
- Green positive P/L and red negative P/L styling.
- Trade markers.
- Tooltip fields: pair, date/time, trade spend, cumulative spent, cumulative volume, estimated value, and estimated P/L.
- A text summary outside the canvas for accessibility and testability.

When no live valuation is available, the component should fall back to the existing accumulation view: completed buys over time and current-value line only when available. It should clearly show that live P/L is unavailable.

## Dependencies

Add `chart.js` to the frontend dependencies. Avoid additional chart wrapper libraries unless the integration becomes noisy; Vue's lifecycle hooks are enough for a focused component.

## Testing

Backend tests:

- Chart points retain chronological cumulative spend and volume.
- Live prices enrich chart points with `current_price`, `estimated_value`, and `estimated_pl`.
- Missing or failed live prices serialize valuation fields as `null`.

API tests:

- `/api/history` returns the new chart fields.
- Existing valuation failure behavior remains unchanged.

Frontend tests:

- `ProfitLossChart` renders a canvas chart when P/L points are available.
- The component renders range controls and the headline P/L value.
- The unavailable-live-price fallback remains readable.
- Empty state remains unchanged.

## Safety Notes

Before editing existing functions, classes, methods, Vue component logic, or route handlers, run GitNexus impact analysis for each edited symbol and report the blast radius. If GitNexus reports a stale index, run `npx gitnexus analyze` before proceeding.

Before committing or final handoff, run GitNexus change detection and verify affected symbols and flows match this chart work.
