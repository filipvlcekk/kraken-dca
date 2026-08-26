# Order History Import Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a web flow where an authenticated user pastes Kraken order IDs, previews valid closed orders for configured DCA pairs, and imports selected rows into local CSV order history.

**Architecture:** Keep CSV history as the source of truth. Add a focused backend import module that fetches Kraken `QueryOrders` data, classifies requested IDs, converts supported orders into the exact existing CSV schema, and performs locked append-only writes with duplicate re-checking. Expose authenticated CSRF-protected FastAPI endpoints and add a compact Vue import panel wired into the current history dashboard.

**Tech Stack:** Python 3.12, FastAPI, httpx, pytest, Vue 3, TypeScript, Vitest, GitNexus.

---

Spec: `docs/superpowers/specs/2026-08-25-order-history-import-design.md`

## Chunk 1: Backend Import Core And API

### File Structure

- Create: `krakendca/order_history_import.py`
  - Own txid parsing, Kraken order classification, CSV row conversion, duplicate detection, path resolution, and append-only import.
- Modify: `krakendca/kraken_client.py`
  - Add `query_orders(txids: list[str]) -> dict`.
- Modify: `krakendca/web/routes_history.py`
  - Add preview/import endpoints and serialization helpers.
- Modify: `krakendca/web/app.py`
  - Add shared file-lock state if the import service needs process-local locks from app state.
- Test: `tests/test_order_history_import.py`
  - Unit tests for parser, classifier, row conversion, duplicate handling, and locked import.
- Test: `tests/test_kraken_client.py`
  - Verify `QueryOrders` payload.
- Test: `tests/test_web_api.py`
  - Auth, CSRF, preview, import, and history refresh contract tests.

### Task 1: Add Kraken QueryOrders Wrapper

**Files:**
- Modify: `krakendca/kraken_client.py`
- Test: `tests/test_kraken_client.py`

- [ ] **Step 1: Run impact analysis**

Run:

```bash
mcp__gitnexus.impact({ repo: "kraken-dca", target: "KrakenClient", direction: "upstream", relationTypes: ["CALLS", "IMPORTS"], includeTests: true })
```

Expected: Review direct callers. Warn before editing if risk is HIGH or CRITICAL.

- [ ] **Step 2: Write failing client test**

Add to `tests/test_kraken_client.py`:

```python
def test_query_orders_uses_txid_payload() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "error": [],
                "result": {
                    "OCYS4K-OILOE-36HPAE": {
                        "status": "closed",
                        "descr": {
                            "pair": "XETHZEUR",
                            "type": "buy",
                            "ordertype": "limit",
                            "price": "2083.16",
                            "order": "buy 0.01 XETHZEUR @ limit 2083.16",
                        },
                        "opentm": 1720000000.0,
                        "closetm": 1720000060.0,
                        "vol_exec": "0.01",
                        "cost": "20.8316",
                        "fee": "0.0542",
                        "oflags": "fciq",
                    }
                },
            },
        )

    client = KrakenClient(
        "public-key",
        "kQH5HW/8p1uGOVjbgWA7FunAmGO8lsSUXNsu3eow76sz84Q18fWxnyRzBHCd3"
        "pd5nE9qa99HAZtuZuj6F1huXg==",
        transport=httpx.MockTransport(handler),
    )

    result = client.query_orders(["OCYS4K-OILOE-36HPAE"])

    body = requests[0].content.decode()
    assert result["OCYS4K-OILOE-36HPAE"]["status"] == "closed"
    assert "txid=OCYS4K-OILOE-36HPAE" in body
```

- [ ] **Step 3: Verify failure**

Run:

```bash
pytest tests/test_kraken_client.py::test_query_orders_uses_txid_payload -q
```

Expected: FAIL because `query_orders` does not exist.

- [ ] **Step 4: Implement wrapper**

Add method to `KrakenClient`:

```python
def query_orders(self, txids: list[str]) -> dict:
    """Get orders keyed by txid."""
    return self._private("QueryOrders", {"txid": ",".join(txids)})
```

- [ ] **Step 5: Verify pass and commit**

Run:

```bash
pytest tests/test_kraken_client.py::test_query_orders_uses_txid_payload -q
mcp__gitnexus.detect_changes({ repo: "kraken-dca", scope: "unstaged" })
git add krakendca/kraken_client.py tests/test_kraken_client.py
git commit -m "feat: query Kraken orders by txid"
```

Expected: Test passes. GitNexus shows expected impact around `KrakenClient`.

### Task 2: Build Import Core

**Files:**
- Create: `krakendca/order_history_import.py`
- Test: `tests/test_order_history_import.py`

- [ ] **Step 1: Write txid parsing tests**

Create `tests/test_order_history_import.py` with:

```python
from krakendca.order_history_import import parse_txids


def test_parse_txids_accepts_lines_commas_and_deduplicates() -> None:
    result = parse_txids(
        "OCYS4K-OILOE-36HPAE\nO4OHPN-MU47M-3FUXEV, OCYS4K-OILOE-36HPAE"
    )

    assert result.txids == ["OCYS4K-OILOE-36HPAE", "O4OHPN-MU47M-3FUXEV"]
    assert result.errors == {}


def test_parse_txids_rejects_malformed_ids() -> None:
    result = parse_txids("not-an-order")
    assert result.errors == {"not-an-order": "Invalid Kraken order ID."}
```

Use the final shape that fits the implementation, but preserve both behaviors.

- [ ] **Step 2: Verify failure**

Run:

```bash
pytest tests/test_order_history_import.py::test_parse_txids_accepts_lines_commas_and_deduplicates tests/test_order_history_import.py::test_parse_txids_rejects_malformed_ids -q
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement parser**

Implement:

```python
ORDER_TXID_PATTERN = re.compile(r"^[A-Z0-9]{6}-[A-Z0-9]{5}-[A-Z0-9]{6}$")
MAX_IMPORT_TXIDS = 50
```

Return a small parse result object with normalized unique IDs in input order plus validation errors. Enforce non-empty and max-count validation in the API layer.

- [ ] **Step 4: Add classification and conversion tests**

Cover:

- Closed buy limit order for configured pair becomes `ready`.
- Existing `txid` becomes `already_imported`.
- Closed sell order becomes `unsupported`.
- Closed buy order for unconfigured pair becomes `unsupported`.
- Missing `cost`, `fee`, `vol_exec`, or description fields becomes `unsupported`.
- Output row field names and ordering exactly equal:

```python
[
    "date",
    "pair",
    "type",
    "order_type",
    "o_flags",
    "pair_price",
    "volume",
    "price",
    "fee",
    "total_price",
    "txid",
    "description",
]
```

- Formula-like string fields are sanitized the same way as `Order.save_order_csv`.

- [ ] **Step 5: Implement classification and conversion**

Create small dataclasses:

```python
@dataclass(frozen=True)
class ImportPreviewItem:
    txid: str
    status: str
    message: str | None
    row: dict[str, str] | None = None
    target_path: Path | None = None
```

Core functions:

```python
def preview_order_import(
    txids: list[str],
    kraken_orders: dict,
    config: dict,
    config_path: str,
) -> list[ImportPreviewItem]:
    ...

def import_order_history_rows(
    items: list[ImportPreviewItem],
    selected_txids: set[str],
    locks: MutableMapping[Path, threading.Lock],
) -> ImportResult:
    ...
```

Keep implementation independent from FastAPI. Derive target paths from config and current pair-level `orders_filepath` rules.

- [ ] **Step 6: Add locked append tests**

Test that import:

- Creates a missing CSV with the exact header.
- Appends to an existing CSV with the exact header.
- Rejects an existing CSV with unexpected columns.
- Re-checks duplicates immediately before write.
- Writes nothing if any target file is unwritable or malformed.

- [ ] **Step 7: Implement locked append**

Use one lock per target path. Under the lock:

1. Read current header and `txid` values.
2. Validate exact header if file exists and is non-empty.
3. Skip rows whose `txid` now exists.
4. Append rows using the exact field order.

- [ ] **Step 8: Verify and commit**

Run:

```bash
pytest tests/test_order_history_import.py -q
mcp__gitnexus.detect_changes({ repo: "kraken-dca", scope: "unstaged" })
git add krakendca/order_history_import.py tests/test_order_history_import.py
git commit -m "feat: add order history import core"
```

Expected: Import core tests pass. GitNexus should show only new symbols or low-risk documentable impact.

### Task 3: Add History Import API Routes

**Files:**
- Modify: `krakendca/web/routes_history.py`
- Modify: `krakendca/web/app.py`
- Test: `tests/test_web_api.py`

- [ ] **Step 1: Run impact analysis**

Run:

```bash
mcp__gitnexus.impact({ repo: "kraken-dca", target: "get_history", direction: "upstream", relationTypes: ["CALLS", "IMPORTS"], includeTests: true })
mcp__gitnexus.impact({ repo: "kraken-dca", target: "create_app", direction: "upstream", relationTypes: ["CALLS", "IMPORTS"], includeTests: true })
```

Expected: Review blast radius. Warn before editing if risk is HIGH or CRITICAL.

- [ ] **Step 2: Write failing API tests**

Add tests to `tests/test_web_api.py`:

- Unauthenticated preview returns auth error.
- Preview and import without CSRF return CSRF errors.
- Preview returns ready/already/import unsupported classifications.
- Import appends one selected ready row and returns counts.
- Import reuses env-backed Kraken credentials when config omits file credentials.
- Import refresh is observable by calling `/api/history` after import.

Use monkeypatch to replace `krakendca.web.routes_history.KrakenClient` with a fake exposing `query_orders`.

- [ ] **Step 3: Verify failure**

Run:

```bash
pytest tests/test_web_api.py::test_history_import_preview_requires_authentication tests/test_web_api.py::test_history_import_requires_csrf -q
```

Expected: FAIL because routes do not exist.

- [ ] **Step 4: Implement route helpers**

In `routes_history.py`, add:

```python
@router.post("/api/history/import/preview")
async def preview_history_import(payload: HistoryImportRequest, request: Request):
    auth.require_csrf(request)
    ...


@router.post("/api/history/import")
async def import_history(payload: HistoryImportCommitRequest, request: Request):
    auth.require_csrf(request)
    ...
```

Use existing `_load_normalized_config`. Add effective key helper that matches scheduler behavior or extract/reuse a common helper if that is cleaner. Store process-local locks on `app.state` from `create_app` if needed.

- [ ] **Step 5: Serialize stable response shape**

Return:

```json
{
  "items": [
    {
      "txid": "OCYS4K-OILOE-36HPAE",
      "status": "ready",
      "message": null,
      "row": {
        "date": "2024-07-03T12:01:00",
        "pair": "XETHZEUR",
        "type": "buy",
        "order_type": "limit",
        "o_flags": "fciq",
        "pair_price": "2083.16",
        "volume": "0.01",
        "price": "20.8316",
        "fee": "0.0542",
        "total_price": "20.8858",
        "txid": "OCYS4K-OILOE-36HPAE",
        "description": "buy 0.01 XETHZEUR @ limit 2083.16"
      },
      "target_file": "orders.csv"
    }
  ],
  "imported_count": 0,
  "skipped_count": 0
}
```

Never serialize absolute filesystem paths to the browser.

- [ ] **Step 6: Verify and commit**

Run:

```bash
pytest tests/test_order_history_import.py tests/test_web_api.py::test_history_import_preview_requires_authentication tests/test_web_api.py::test_history_import_requires_csrf tests/test_web_api.py::test_history_import_preview_classifies_orders tests/test_web_api.py::test_history_import_appends_selected_orders -q
mcp__gitnexus.detect_changes({ repo: "kraken-dca", scope: "unstaged" })
git add krakendca/web/routes_history.py krakendca/web/app.py tests/test_web_api.py
git commit -m "feat: expose order history import api"
```

Expected: Focused backend tests pass. GitNexus impact matches history API and app initialization.

## Chunk 2: Frontend Import Panel And Verification

### File Structure

- Modify: `frontend/src/api.ts`
  - Add import request/response types and functions.
- Create: `frontend/src/components/OrderHistoryImportPanel.vue`
  - Own input, preview, selection, import submission, and local status rendering.
- Modify: `frontend/src/App.vue`
  - Render import panel near order history and reload history after success.
- Test: `frontend/src/__tests__/api.test.ts`
  - Verify endpoints and CSRF usage.
- Test: `frontend/src/__tests__/orderHistoryImportPanel.test.ts`
  - Verify input parsing, preview rendering, selection, import submit.
- Modify: `frontend/src/__tests__/app.test.ts`
  - Verify history refresh after import success.

### Task 4: Add Frontend API Client

**Files:**
- Modify: `frontend/src/api.ts`
- Test: `frontend/src/__tests__/api.test.ts`

- [ ] **Step 1: Run impact analysis**

Run:

```bash
mcp__gitnexus.impact({ repo: "kraken-dca", target: "loadHistory", direction: "upstream", relationTypes: ["CALLS", "IMPORTS"], includeTests: true })
```

Expected: Review frontend API consumers.

- [ ] **Step 2: Write failing API tests**

Add tests proving:

- `previewHistoryImport(txids, csrfToken)` POSTs to `/api/history/import/preview` with CSRF.
- `importHistoryOrders(txids, selectedTxids, csrfToken)` POSTs to `/api/history/import` with CSRF.

- [ ] **Step 3: Implement types and functions**

Add types:

```ts
export type HistoryImportStatus =
  | 'ready'
  | 'already_imported'
  | 'not_found'
  | 'not_closed'
  | 'unsupported'

export type HistoryImportItem = {
  txid: string
  status: HistoryImportStatus
  message: string | null
  row: HistoryEntry | null
  target_file: string | null
}

export type HistoryImportResponse = {
  items: HistoryImportItem[]
  imported_count: number
  skipped_count: number
}
```

Add functions:

```ts
export function previewHistoryImport(
  txids: string[],
  csrfToken: string,
): Promise<ApiResponse<HistoryImportResponse>> { ... }

export function importHistoryOrders(
  txids: string[],
  selectedTxids: string[],
  csrfToken: string,
): Promise<ApiResponse<HistoryImportResponse>> { ... }
```

- [ ] **Step 4: Verify and commit**

Run:

```bash
cd frontend
npm test -- --run src/__tests__/api.test.ts
cd ..
mcp__gitnexus.detect_changes({ repo: "kraken-dca", scope: "unstaged" })
git add frontend/src/api.ts frontend/src/__tests__/api.test.ts
git commit -m "feat: add history import api client"
```

Expected: API tests pass.

### Task 5: Build Import Panel Component

**Files:**
- Create: `frontend/src/components/OrderHistoryImportPanel.vue`
- Test: `frontend/src/__tests__/orderHistoryImportPanel.test.ts`

- [ ] **Step 1: Write failing component tests**

Test:

- Preview button disabled until a valid-looking txid is entered.
- Newlines and commas are parsed into unique IDs.
- Preview results are grouped by status.
- Ready rows are selected by default.
- Import button submits selected txids with all preview txids.
- Preview and import requests include the `csrfToken` prop.
- API errors are displayed without clearing preview data.

- [ ] **Step 2: Verify failure**

Run:

```bash
cd frontend
npm test -- --run src/__tests__/orderHistoryImportPanel.test.ts
```

Expected: FAIL because component does not exist.

- [ ] **Step 3: Implement component**

Use a compact section with:

- `Import orders` toggle button.
- Textarea for IDs.
- `Preview import` button.
- Grouped preview table.
- Checkboxes only for `ready` rows.
- `Import selected` button.
- Small success/error line.

Props:

```ts
defineProps<{
  csrfToken: string
}>()
```

Emit:

```ts
const emit = defineEmits<{
  imported: []
}>()
```

Call `emit('imported')` after successful import so the parent refreshes history.

- [ ] **Step 4: Verify and commit**

Run:

```bash
cd frontend
npm test -- --run src/__tests__/orderHistoryImportPanel.test.ts
cd ..
mcp__gitnexus.detect_changes({ repo: "kraken-dca", scope: "unstaged" })
git add frontend/src/components/OrderHistoryImportPanel.vue frontend/src/__tests__/orderHistoryImportPanel.test.ts
git commit -m "feat: add order history import panel"
```

Expected: Component tests pass.

### Task 6: Wire Import Panel Into Dashboard

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/__tests__/app.test.ts`

- [ ] **Step 1: Run impact analysis**

Run:

```bash
mcp__gitnexus.impact({ repo: "kraken-dca", target: "App", direction: "upstream", relationTypes: ["CALLS", "IMPORTS"], includeTests: true })
```

Expected: Review dashboard blast radius.

- [ ] **Step 2: Write failing app test**

Extend `frontend/src/__tests__/app.test.ts` to verify that after the import panel emits `imported`, the app calls `/api/history` again and renders refreshed history.

- [ ] **Step 3: Implement wiring**

In `frontend/src/App.vue`:

- Import `OrderHistoryImportPanel`.
- Render it near `OrderHistoryTable` only when authenticated and history is available.
- Pass current CSRF token.
- On `imported`, call `history.load()`.

- [ ] **Step 4: Verify and commit**

Run:

```bash
cd frontend
npm test -- --run src/__tests__/app.test.ts src/__tests__/api.test.ts src/__tests__/orderHistoryImportPanel.test.ts
cd ..
mcp__gitnexus.detect_changes({ repo: "kraken-dca", scope: "unstaged" })
git add frontend/src/App.vue frontend/src/__tests__/app.test.ts
git commit -m "feat: wire history import into dashboard"
```

Expected: App and import tests pass.

### Task 7: Final Verification

**Files:**
- All touched backend/frontend files.

- [ ] **Step 1: Run backend tests**

Run:

```bash
pytest tests/test_order_history_import.py tests/test_kraken_client.py tests/test_web_api.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend tests and build**

Run:

```bash
cd frontend
npm test -- --run
npm run build
cd ..
```

Expected: PASS.

- [ ] **Step 3: Run GitNexus change detection**

Run:

```bash
mcp__gitnexus.detect_changes({ repo: "kraken-dca", scope: "all" })
```

Expected: Changed symbols and affected processes are limited to Kraken client, order history import, history API, and dashboard import UI.

- [ ] **Step 4: Manual smoke test**

Start the local web app using the repo's standard development command. Log in, open the dashboard, paste known fake/test txids against a mocked or test Kraken client if available, preview, import, and confirm the order appears in completed history without duplicating an existing `txid`.

- [ ] **Step 5: Final commit if needed**

If verification required cleanup changes:

```bash
git add <touched-files>
git commit -m "test: verify order history import"
```

Expected: Working tree contains only intentional user changes or is clean for this feature.
