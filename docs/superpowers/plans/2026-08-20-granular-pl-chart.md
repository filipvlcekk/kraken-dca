# Granular P/L Chart Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Chart.js-based time P/L curve that shows trade-level estimated P/L over time and keeps the history API ready for future historical Kraken OHLC pricing.

**Architecture:** The backend keeps CSV order history as the source of truth and enriches chart points after live prices are fetched. The frontend replaces the custom SVG with a focused Chart.js canvas component, range controls, accessible textual summary, and unavailable-live-price fallback.

**Tech Stack:** Python, FastAPI, Decimal, Vue 3, TypeScript, Chart.js, Vitest, pytest, GitNexus.

---

## Chunk 1: Backend Contract And Frontend Chart

### File Structure

- Modify `krakendca/order_history.py`
  - Responsibility: parse and aggregate completed CSV orders; add chart-point valuation data without fetching prices.
- Modify `krakendca/web/routes_history.py`
  - Responsibility: fetch live prices, enrich chart points, and serialize the expanded API contract.
- Modify `tests/test_order_history.py`
  - Responsibility: unit coverage for valuation-enriched chart points.
- Modify `tests/test_web_api.py`
  - Responsibility: API contract coverage for new chart fields and live-price failure fallback.
- Modify `frontend/package.json`
  - Responsibility: declare `chart.js`.
- Modify `frontend/package-lock.json`
  - Responsibility: lock installed `chart.js` dependency.
- Modify `frontend/src/api.ts`
  - Responsibility: expose the expanded `HistoryChartPoint` frontend type.
- Modify `frontend/src/components/ProfitLossChart.vue`
  - Responsibility: own Chart.js rendering, range state, display formatting, fallback chart mode, and accessibility summary for history P/L.
- Modify `frontend/src/__tests__/profitLossChart.test.ts`
  - Responsibility: component behavior coverage with Chart.js mocked.

### Task 1: Prepare GitNexus And Backend Impact Analysis

**Files:**
- Read: `docs/superpowers/specs/2026-08-20-granular-pl-chart-design.md`
- Analyze: `krakendca/order_history.py`
- Analyze: `krakendca/web/routes_history.py`

- [ ] **Step 1: Refresh GitNexus if needed**

Run:

```bash
npx gitnexus analyze
```

Expected: the `kraken-dca` index is refreshed successfully. If GitNexus tooling reports the index is already current, record that and continue.

- [ ] **Step 2: Run backend impact analysis before editing symbols**

Run GitNexus impact analysis for each symbol that will be edited:

```text
mcp__gitnexus.impact({ repo: "kraken-dca", target: "HistoryChartPoint", direction: "upstream", relationTypes: ["CALLS", "IMPORTS", "ACCESSES"], includeTests: true })
mcp__gitnexus.impact({ repo: "kraken-dca", target: "build_history_chart", direction: "upstream", relationTypes: ["CALLS", "IMPORTS"], includeTests: true })
mcp__gitnexus.impact({ repo: "kraken-dca", target: "get_history", direction: "upstream", relationTypes: ["CALLS", "IMPORTS"], includeTests: true })
mcp__gitnexus.impact({ repo: "kraken-dca", target: "_serialize_chart_point", direction: "upstream", relationTypes: ["CALLS", "IMPORTS"], includeTests: true })
```

Expected: report direct callers, affected processes, and risk level to the user. If any result is HIGH or CRITICAL, stop and warn the user before editing.

### Task 2: Add Backend Tests For Chart Valuation Fields

**Files:**
- Modify: `tests/test_order_history.py`
- Modify: `tests/test_web_api.py`

- [ ] **Step 1: Add unit test for live-price chart enrichment**

In `tests/test_order_history.py`, add tests near `test_apply_live_prices_calculates_estimated_pl`:

```python
def test_apply_live_prices_enriches_history_chart_points(tmp_path) -> None:
    history_path = tmp_path / "orders.csv"
    _write_orders(
        history_path,
        [
            _order_row(
                date="2026-07-20 10:00:00",
                pair="XETHZEUR",
                volume="0.01",
                price="20",
                fee="0.05",
                total_price="20.05",
                txid="FIRST",
            ),
            _order_row(
                date="2026-07-21 10:00:00",
                pair="XETHZEUR",
                volume="0.02",
                price="40",
                fee="0.10",
                total_price="40.10",
                txid="SECOND",
            ),
        ],
    )
    points = build_history_chart(load_order_history(history_path))

    enriched = apply_live_prices_to_chart(
        points,
        {"XETHZEUR": Decimal("2500")},
    )

    assert enriched[0].current_price == Decimal("2500")
    assert enriched[0].estimated_value == Decimal("25.00")
    assert enriched[0].estimated_pl == Decimal("4.95")
    assert enriched[0].historical_price is None
    assert enriched[0].historical_value is None
    assert enriched[0].historical_pl is None
    assert enriched[1].estimated_value == Decimal("75.00")
    assert enriched[1].estimated_pl == Decimal("14.85")


def test_apply_live_prices_to_chart_values_portfolio_across_pairs(
    tmp_path,
) -> None:
    history_path = tmp_path / "orders.csv"
    _write_orders(
        history_path,
        [
            _order_row(
                date="2026-07-20 10:00:00",
                pair="XETHZEUR",
                volume="0.01",
                price="20",
                fee="0.05",
                total_price="20.05",
                txid="ETH",
            ),
            _order_row(
                date="2026-07-21 10:00:00",
                pair="XXBTZEUR",
                volume="0.001",
                price="30",
                fee="0.08",
                total_price="30.08",
                txid="BTC",
            ),
        ],
    )
    points = build_history_chart(load_order_history(history_path))

    enriched = apply_live_prices_to_chart(
        points,
        {
            "XETHZEUR": Decimal("2500"),
            "XXBTZEUR": Decimal("40000"),
        },
    )

    assert enriched[0].current_price == Decimal("2500")
    assert enriched[0].estimated_value == Decimal("25.00")
    assert enriched[0].estimated_pl == Decimal("4.95")
    assert enriched[1].current_price == Decimal("40000")
    assert enriched[1].estimated_value == Decimal("65.000")
    assert enriched[1].estimated_pl == Decimal("14.870")
```

Also update imports to include `apply_live_prices_to_chart`.

- [ ] **Step 2: Add API contract assertions**

In `tests/test_web_api.py`, extend `test_history_returns_completed_order_summary` after the existing chart assertion:

```python
    last_point = data["chart"][-1]
    assert last_point["current_price"] == "2500.0"
    assert last_point["estimated_value"] == "75.000"
    assert last_point["estimated_pl"] == "14.850"
    assert last_point["historical_price"] is None
    assert last_point["historical_value"] is None
    assert last_point["historical_pl"] is None
```

Extend `test_history_keeps_csv_data_when_live_prices_fail`:

```python
    point = data["chart"][0]
    assert point["current_price"] is None
    assert point["estimated_value"] is None
    assert point["estimated_pl"] is None
    assert point["historical_price"] is None
    assert point["historical_value"] is None
    assert point["historical_pl"] is None
```

- [ ] **Step 3: Run backend tests and verify failure**

Run:

```bash
pytest tests/test_order_history.py::test_apply_live_prices_enriches_history_chart_points tests/test_order_history.py::test_apply_live_prices_to_chart_values_portfolio_across_pairs tests/test_web_api.py::test_history_returns_completed_order_summary tests/test_web_api.py::test_history_keeps_csv_data_when_live_prices_fail -q
```

Expected: FAIL because `apply_live_prices_to_chart` and the serialized chart fields do not exist yet.

### Task 3: Implement Backend Chart Point Enrichment

**Files:**
- Modify: `krakendca/order_history.py`
- Modify: `krakendca/web/routes_history.py`

- [ ] **Step 1: Extend chart point dataclass**

In `krakendca/order_history.py`, extend `HistoryChartPoint`:

```python
@dataclass(frozen=True)
class HistoryChartPoint:
    date: datetime
    pair: str
    txid: str
    spent: Decimal
    volume: Decimal
    cumulative_spent: Decimal
    cumulative_volume: Decimal
    current_price: Decimal | None = None
    estimated_value: Decimal | None = None
    estimated_pl: Decimal | None = None
    historical_price: Decimal | None = None
    historical_value: Decimal | None = None
    historical_pl: Decimal | None = None
```

- [ ] **Step 2: Add focused enrichment helper**

In `krakendca/order_history.py`, below `apply_live_prices`, add:

```python
def apply_live_prices_to_chart(
    points: list[HistoryChartPoint],
    prices: dict[str, Decimal],
) -> list[HistoryChartPoint]:
    """Return chart points enriched with current-price portfolio valuation."""
    enriched = []
    holdings_by_pair: dict[str, Decimal] = {}
    for point in points:
        holdings_by_pair[point.pair] = (
            holdings_by_pair.get(point.pair, Decimal("0")) + point.volume
        )
        current_price = prices.get(point.pair)
        priced_values = [
            volume * prices[pair]
            for pair, volume in holdings_by_pair.items()
            if pair in prices
        ]
        estimated_value = None
        estimated_pl = None
        if len(priced_values) == len(holdings_by_pair):
            estimated_value = sum(priced_values, Decimal("0"))
            estimated_pl = estimated_value - point.cumulative_spent
        enriched.append(
            HistoryChartPoint(
                **{
                    **point.__dict__,
                    "current_price": current_price,
                    "estimated_value": estimated_value,
                    "estimated_pl": estimated_pl,
                }
            )
        )
    return enriched
```

`estimated_value` and `estimated_pl` are portfolio-level values at that chart point. `current_price` is the current price for the point's trade pair and exists mainly for tooltip detail. If any held pair lacks a live price at a point, set that point's estimated portfolio fields to `None` rather than mixing partial portfolio values.

- [ ] **Step 3: Use helper in history route**

In `krakendca/web/routes_history.py`, import `apply_live_prices_to_chart`. In `get_history`, after successful `_fetch_pair_prices`, update both summary and chart:

```python
            if prices:
                summary = apply_live_prices(summary, prices)
                chart = apply_live_prices_to_chart(chart, prices)
                valuation = {"status": "live", "message": None}
```

- [ ] **Step 4: Serialize new fields**

In `_serialize_chart_point`, add:

```python
        "current_price": _optional_decimal(point.current_price),
        "estimated_value": _optional_decimal(point.estimated_value),
        "estimated_pl": _optional_decimal(point.estimated_pl),
        "historical_price": _optional_decimal(point.historical_price),
        "historical_value": _optional_decimal(point.historical_value),
        "historical_pl": _optional_decimal(point.historical_pl),
```

- [ ] **Step 5: Run backend tests and verify pass**

Run:

```bash
pytest tests/test_order_history.py tests/test_web_api.py::test_history_returns_empty_state_for_missing_orders_file tests/test_web_api.py::test_history_returns_completed_order_summary tests/test_web_api.py::test_history_keeps_csv_data_when_live_prices_fail tests/test_web_api.py::test_history_uses_pair_level_orders_filepath -q
```

Expected: PASS.

- [ ] **Step 6: Commit backend contract**

Before committing, run:

```text
mcp__gitnexus.detect_changes({ repo: "kraken-dca", scope: "all" })
```

Expected: changed symbols are limited to order history/chart serialization work with low or medium risk. Then commit only touched backend files and tests:

```bash
git add krakendca/order_history.py krakendca/web/routes_history.py tests/test_order_history.py tests/test_web_api.py
git commit -m "feat: enrich history chart points"
```

### Task 4: Add Chart.js And Frontend Impact Analysis

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Analyze: `frontend/src/api.ts`
- Analyze: `frontend/src/components/ProfitLossChart.vue`

- [ ] **Step 1: Install Chart.js**

Run:

```bash
cd frontend && npm install chart.js
```

Expected: `frontend/package.json` and `frontend/package-lock.json` include `chart.js`.

- [ ] **Step 2: Run frontend impact analysis before editing symbols**

Run GitNexus impact analysis:

```text
mcp__gitnexus.impact({ repo: "kraken-dca", target: "HistoryChartPoint", direction: "upstream", relationTypes: ["CALLS", "IMPORTS", "ACCESSES"], includeTests: true })
mcp__gitnexus.impact({ repo: "kraken-dca", target: "ProfitLossChart", direction: "upstream", relationTypes: ["CALLS", "IMPORTS"], includeTests: true })
```

Expected: report direct callers, affected processes, and risk level to the user. If any result is HIGH or CRITICAL, stop and warn the user before editing.

### Task 5: Add Frontend Tests For Chart UI

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/__tests__/profitLossChart.test.ts`

- [ ] **Step 1: Extend frontend API type**

In `frontend/src/api.ts`, add these fields to `HistoryChartPoint`:

```ts
  current_price: string | null
  estimated_value: string | null
  estimated_pl: string | null
  historical_price: string | null
  historical_value: string | null
  historical_pl: string | null
```

- [ ] **Step 2: Mock Chart.js in the component test**

In `frontend/src/__tests__/profitLossChart.test.ts`, add above the `describe` block:

```ts
import { beforeEach, vi } from 'vitest'

const chartMock = vi.hoisted(() => {
  const destroy = vi.fn()
  const update = vi.fn()
  const register = vi.fn()
  const constructor = vi.fn().mockImplementation(() => ({
    destroy,
    update,
  }))
  return {
    constructor,
    destroy,
    register,
    update,
  }
})

vi.mock('chart.js', () => ({
  Chart: Object.assign(chartMock.constructor, {
    register: chartMock.register,
  }),
  registerables: [],
}))

beforeEach(() => {
  chartMock.constructor.mockClear()
  chartMock.destroy.mockClear()
  chartMock.register.mockClear()
  chartMock.update.mockClear()
})
```

Adjust the existing Vitest import to include `beforeEach` and `vi`. Use `chartMock.constructor.mock.calls.at(-1)?.[1]` in assertions to inspect the most recent Chart.js configuration.

- [ ] **Step 3: Update existing test fixtures**

Every `HistoryChartPoint` fixture in frontend tests must include:

```ts
current_price: '2500',
estimated_value: '75.00',
estimated_pl: '14.85',
historical_price: null,
historical_value: null,
historical_pl: null,
```

For empty or unavailable fixtures, use `null` for all six new fields.

- [ ] **Step 4: Add Chart.js render test**

Replace the SVG expectation with:

```ts
expect(wrapper.find('canvas[aria-label="Estimated P/L over time"]').exists()).toBe(true)
expect(chartMock.constructor).toHaveBeenCalledTimes(1)
expect(wrapper.text()).toContain('P/L')
expect(wrapper.text()).toContain('+14.85')
expect(wrapper.text()).toContain('+24.69%')
expect(wrapper.text()).toContain('Trades')
expect(wrapper.text()).toContain('1D')
expect(wrapper.text()).toContain('7D')
expect(wrapper.text()).toContain('1M')
expect(wrapper.text()).toContain('All')

const config = chartMock.constructor.mock.calls[0][1]
expect(config.options.scales.y.suggestedMin).toBeLessThanOrEqual(0)
expect(config.options.scales.y.suggestedMax).toBeGreaterThanOrEqual(0)
expect(config.data.datasets[0].pointRadius).toBeGreaterThan(0)
```

- [ ] **Step 5: Add range filtering and accessibility summary tests**

Add a fixture with one old point and one recent point. Click `1D`, then assert the latest Chart.js config only includes the recent label:

```ts
it('filters points when a date range is selected', async () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-07-22T12:00:00Z'))
  try {
    const wrapper = mount(ProfitLossChart, {
      props: {
        points: [
          {
            date: '2026-07-19T10:00:00Z',
            pair: 'XETHZEUR',
            txid: 'OLD',
            spent: '20.05',
            volume: '0.01',
            cumulative_spent: '20.05',
            cumulative_volume: '0.01',
            current_price: '2500',
            estimated_value: '25.00',
            estimated_pl: '4.95',
            historical_price: null,
            historical_value: null,
            historical_pl: null,
          },
          {
            date: '2026-07-22T10:00:00Z',
            pair: 'XETHZEUR',
            txid: 'RECENT',
            spent: '40.10',
            volume: '0.02',
            cumulative_spent: '60.15',
            cumulative_volume: '0.03',
            current_price: '2500',
            estimated_value: '75.00',
            estimated_pl: '14.85',
            historical_price: null,
            historical_value: null,
            historical_pl: null,
          },
        ],
        estimatedValue: '75.00',
      },
    })

    await wrapper.find('button[data-range="1D"]').trigger('click')

    const latestConfig = chartMock.constructor.mock.calls.at(-1)?.[1]
    expect(latestConfig.data.labels).toHaveLength(1)
    expect(latestConfig.data.datasets[0].data).toEqual([14.85])
    expect(wrapper.text()).toContain('Latest trade')
    expect(wrapper.text()).toContain('RECENT')
  } finally {
    vi.useRealTimers()
  }
})
```

- [ ] **Step 6: Add unavailable fallback test**

Add:

```ts
it('falls back to accumulation copy when live P/L is unavailable', () => {
  const wrapper = mount(ProfitLossChart, {
    props: {
      points: [
        {
          date: '2026-07-20T10:00:00',
          pair: 'XETHZEUR',
          txid: 'A',
          spent: '20.05',
          volume: '0.01',
          cumulative_spent: '20.05',
          cumulative_volume: '0.01',
          current_price: null,
          estimated_value: null,
          estimated_pl: null,
          historical_price: null,
          historical_value: null,
          historical_pl: null,
        },
      ],
      estimatedValue: null,
    },
  })

  expect(wrapper.text()).toContain('Live P/L unavailable')
  expect(wrapper.text()).toContain('Money spent')
})
```

Also add a fallback test where `estimatedValue` is present but point-level P/L is unavailable:

```ts
it('keeps the worth-now line when point-level P/L is unavailable', () => {
  mount(ProfitLossChart, {
    props: {
      points: [
        {
          date: '2026-07-20T10:00:00',
          pair: 'XETHZEUR',
          txid: 'A',
          spent: '20.05',
          volume: '0.01',
          cumulative_spent: '20.05',
          cumulative_volume: '0.01',
          current_price: null,
          estimated_value: null,
          estimated_pl: null,
          historical_price: null,
          historical_value: null,
          historical_pl: null,
        },
      ],
      estimatedValue: '25.00',
    },
  })

  const config = chartMock.constructor.mock.calls.at(-1)?.[1]
  expect(config.data.datasets.map((dataset) => dataset.label)).toEqual(
    expect.arrayContaining(['Money spent', 'Worth now']),
  )
})
```

- [ ] **Step 7: Add tooltip callback assertion**

In the Chart.js render test, inspect the tooltip callback from the captured config and call it with the first raw point:

```ts
const tooltip = config.options.plugins.tooltip.callbacks
expect(tooltip.title([{ raw: config.data.datasets[0].rawPoints[0] }])).toContain('XETHZEUR')
expect(tooltip.label({ raw: config.data.datasets[0].rawPoints[0] })).toEqual(
  expect.arrayContaining([
    expect.stringContaining('Trade spend'),
    expect.stringContaining('Cumulative spent'),
    expect.stringContaining('Estimated P/L'),
  ]),
)
```

If storing `rawPoints` directly on the dataset conflicts with Chart.js types, use a closure-backed local array in the component and assert the callback against whatever typed shape the implementation chooses. The test must verify the tooltip includes pair/date, spend, cumulative spend, cumulative volume, estimated value, and P/L.

- [ ] **Step 8: Run frontend component test and verify failure**

Run:

```bash
cd frontend && npm test -- --run src/__tests__/profitLossChart.test.ts
```

Expected: FAIL because `ProfitLossChart.vue` still renders SVG and does not instantiate Chart.js.

### Task 6: Implement Chart.js ProfitLossChart

**Files:**
- Modify: `frontend/src/components/ProfitLossChart.vue`

- [ ] **Step 1: Replace SVG lifecycle with Chart.js lifecycle**

Use Vue lifecycle hooks and Chart.js imports:

```ts
import {
  Chart,
  type ChartConfiguration,
  registerables,
} from 'chart.js'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

Chart.register(...registerables)
```

Create refs:

```ts
const canvas = ref<HTMLCanvasElement | null>(null)
const chart = ref<Chart | null>(null)
const selectedRange = ref<RangeKey>('Trades')
```

- [ ] **Step 2: Add local chart helpers**

Keep helpers inside the component unless they become too large:

```ts
type RangeKey = 'Trades' | '1D' | '7D' | '1M' | 'All'
const rangeOptions: RangeKey[] = ['Trades', '1D', '7D', '1M', 'All']

function money(value: number): string {
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}`
}

function numberValue(value: string | null | undefined): number | null {
  if (value === null || value === undefined) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function percent(pl: number, spent: number): string | null {
  if (spent === 0) return null
  const value = (pl / spent) * 100
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}
```

Implement filtered points with date filtering for `1D`, `7D`, and `1M`; `Trades` and `All` both show all points for this first iteration, with `Trades` communicating point-per-order mode.

- [ ] **Step 3: Build datasets**

Use `historical_pl` when present, otherwise `estimated_pl`:

```ts
type ChartPointWithValue = {
  x: number
  y: number
  point: HistoryChartPoint
}

function hasYValue(
  point: ChartPointWithValue | { y: number | null },
): point is ChartPointWithValue {
  return point.y !== null
}

const plPoints = computed<ChartPointWithValue[]>(() => filteredPoints.value.map((point) => ({
  x: new Date(point.date).getTime(),
  y: numberValue(point.historical_pl) ?? numberValue(point.estimated_pl),
  point,
})).filter(hasYValue))
```

For unavailable live P/L, build a `cumulative_spent` dataset instead.

If `props.estimatedValue` is present while point-level P/L is unavailable, add a second dataset labeled `Worth now` with the same value repeated for each visible label. This preserves the existing current-value reference line.

Compute headline values from the latest visible point with P/L data:

```ts
const headlinePl = computed(() => {
  const latest = latestPlPoint.value
  return latest === null ? 'Live P/L unavailable' : money(latest.y)
})

const headlinePercent = computed(() => {
  const latest = latestPlPoint.value
  const spent = numberValue(latest?.point.cumulative_spent)
  return latest === null || spent === null ? null : percent(latest.y, spent)
})
```

- [ ] **Step 4: Render chart**

Create a `renderChart()` function that destroys the previous chart and instantiates a new one with:

- `type: 'line'`
- instantiate Chart.js with the canvas element directly, `new Chart(canvas.value, config)`, to avoid jsdom `getContext()` issues in mocked tests
- responsive true
- no animation in tests/user dashboard for stable rendering
- `scales.x.type = 'category'` unless adding a time adapter; labels should be formatted dates
- `scales.y.suggestedMin <= 0` and `scales.y.suggestedMax >= 0` so the zero axis is always visible even when all P/L values are positive or all are negative
- `scales.y.grid.color` returns a stronger zero-line color when `context.tick.value === 0`, and a muted grid color otherwise
- tooltip callbacks reading the original point data and returning pair/date, trade spend, cumulative spent, cumulative volume, estimated value, and P/L
- segment colors green/red based on P/L sign
- visible trade markers using non-zero `pointRadius`, hover radius, and point colors based on P/L sign
- a typed way to retain raw point metadata for tooltip callbacks, for example a local `visiblePointMetadata` array keyed by data index or a dataset extension type

Wire lifecycle explicitly:

```ts
async function scheduleRender(): Promise<void> {
  await nextTick()
  renderChart()
}

onMounted(() => {
  void scheduleRender()
})

watch(
  [() => props.points, () => props.estimatedValue, selectedRange],
  () => {
    void scheduleRender()
  },
  { deep: true },
)

onBeforeUnmount(() => {
  chart.value?.destroy()
  chart.value = null
})
```

`renderChart()` must destroy any previous chart before creating the next one so range changes do not leak Chart.js instances.

- [ ] **Step 5: Add template controls and summary**

Template should include:

```vue
<section class="chart-panel" aria-label="P/L chart">
  <div class="panel-heading chart-heading">
    <div>
      <p class="eyebrow">P/L chart</p>
      <h2>Current-price estimated P/L over time</h2>
    </div>
    <div class="pl-headline">
      <span>P/L</span>
      <strong>{{ headlinePl }}</strong>
      <em v-if="headlinePercent !== null">{{ headlinePercent }}</em>
    </div>
  </div>

  <p v-if="points.length === 0" class="empty-state">No completed orders yet.</p>

  <div v-else class="chart-wrap">
    <div class="range-controls" aria-label="Chart range">
      <button
        v-for="range in rangeOptions"
        :key="range"
        type="button"
        :data-range="range"
        :class="{ active: selectedRange === range }"
        @click="selectedRange = range"
      >
        {{ range }}
      </button>
    </div>
    <p v-if="!hasPlData" class="chart-note">Live P/L unavailable. Showing completed buy accumulation.</p>
    <p class="chart-summary">
      Latest trade {{ latestPoint?.txid }}. Cumulative spent {{ latestSpent }}.
      Cumulative volume {{ latestVolume }}. Estimated value {{ latestValue }}.
    </p>
    <canvas ref="canvas" aria-label="Estimated P/L over time"></canvas>
    <div class="legend">
      <span><i class="profit-key"></i>Profit</span>
      <span><i class="loss-key"></i>Loss</span>
      <span v-if="!hasPlData"><i class="spent-key"></i>Money spent</span>
      <span v-if="!hasPlData && estimatedValue !== null"><i class="estimate-key"></i>Worth now</span>
    </div>
  </div>
</section>
```

- [ ] **Step 6: Style to match existing dashboard**

Keep within existing tokens in `frontend/src/tokens.css`. Use a compact panel, stable canvas height, segmented range buttons, and green/red token colors. Avoid nested cards and oversized headings.

- [ ] **Step 7: Run frontend component test**

Run:

```bash
cd frontend && npm test -- --run src/__tests__/profitLossChart.test.ts
```

Expected: PASS.

- [ ] **Step 8: Commit frontend chart**

Before committing, run:

```text
mcp__gitnexus.detect_changes({ repo: "kraken-dca", scope: "all" })
```

Expected: changed symbols are limited to `HistoryChartPoint` type and `ProfitLossChart` UI. Then commit:

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/api.ts frontend/src/components/ProfitLossChart.vue frontend/src/__tests__/profitLossChart.test.ts
git commit -m "feat: add granular pl chart"
```

### Task 7: Full Verification

**Files:**
- Verify: all touched backend and frontend files

- [ ] **Step 1: Run backend test suite**

Run:

```bash
pytest -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend test suite**

Run:

```bash
cd frontend && npm test -- --run
```

Expected: PASS.

- [ ] **Step 3: Run frontend production build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 4: Run final GitNexus change detection**

Run:

```text
mcp__gitnexus.detect_changes({ repo: "kraken-dca", scope: "all" })
```

Expected: affected symbols and flows are limited to the planned history chart contract and frontend chart UI.

- [ ] **Step 5: Final status**

Report:

- commits created,
- tests run and their results,
- any remaining unrelated local changes that were not touched,
- whether `chart.js` installation required network approval.
