# Order History Import Design

## Goal

Let an authenticated user paste Kraken order IDs into the web UI, preview the matching closed Kraken orders, and import selected valid orders into the local CSV order history.

## User Experience

Add an `Import orders` action to the completed order history area. The action opens a focused import panel with a multiline input for Kraken order IDs. Users can paste one ID per line or comma-separated IDs.

The first action is `Preview import`. Preview calls Kraken and returns a grouped result:

- Ready to import: valid closed buy limit orders for currently configured DCA pairs.
- Already imported: matching `txid` already exists in configured CSV history.
- Not found: Kraken did not return the requested order ID.
- Not closed: the order exists but is not a closed order.
- Unsupported: the order is not a buy limit order for a currently configured DCA pair, or does not provide the fields needed for CSV history.

The preview table shows pair, close date, volume, price before fee, fee, total spent, txid, and target CSV file. The user then chooses `Import selected`. After a successful import, the app refreshes `/api/history`.

## Scope

- Import only explicit Kraken order IDs supplied by the user.
- Import only orders for currently configured `dca_pairs`.
- Preserve existing CSV order history as the source of truth.
- Skip duplicate `txid` values instead of overwriting or appending duplicates.
- Resolve target CSV files the same way current history loading does: pair-level `orders_filepath` overrides top-level `orders_filepath`, both relative to the active config directory.
- Keep the feature authenticated and CSRF-protected.

Do not add date-range account backfill in this release. It is too easy to mix bot orders with manual trades without a stronger order marker.

## Backend Design

Add a focused import service that accepts normalized config, current CSV history paths, and a Kraken client. It fetches the requested IDs from Kraken, converts supported closed orders to CSV rows using the exact field names and order produced by `Order.save_order_csv`, and classifies every requested ID.

The CSV writer must preserve this exact schema:

```text
date,pair,type,order_type,o_flags,pair_price,volume,price,fee,total_price,txid,description
```

Use Kraken order details rather than current market data. CSV fields should be derived from the returned order:

- `date`: close time when available, otherwise open time only if Kraken marks the order closed.
- `pair`: configured DCA pair name matching the Kraken order pair or its alt name.
- `type`: Kraken order description type, expected `buy`.
- `order_type`: Kraken order description order type, expected `limit`.
- `o_flags`: Kraken order flags when available, expected to include or equal the bot's fee-in-quote behavior when Kraken provides it.
- `pair_price`: limit price from order description.
- `volume`: executed volume.
- `price`: executed cost before fee.
- `fee`: Kraken fee.
- `total_price`: cost plus fee.
- `txid`: Kraken order ID.
- `description`: Kraken order description string.

If Kraken omits fields needed to reconstruct the CSV row, classify the item as unsupported and explain the missing field in the API response.

Kraken-derived string fields must use the same CSV-injection protection as normal order writes. Values that begin with formula-like characters after optional whitespace must be prefixed before they are written.

Credential resolution must match scheduler/runtime behavior. Import should use the effective Kraken credentials from config plus environment-backed credentials, not only raw values present in `config.yaml`.

## API Design

Add:

```text
POST /api/history/import/preview
POST /api/history/import
```

Preview request:

```json
{
  "txids": ["OCYS4K-OILOE-36HPAE", "O4OHPN-MU47M-3FUXEV"]
}
```

Import request:

```json
{
  "txids": ["OCYS4K-OILOE-36HPAE", "O4OHPN-MU47M-3FUXEV"],
  "selected_txids": ["OCYS4K-OILOE-36HPAE"]
}
```

Both endpoints return the same classification shape. The import endpoint also returns counts for imported and skipped rows. The import endpoint must re-fetch or re-validate Kraken data instead of trusting preview data from the client.

The Kraken client should add a private `QueryOrders` wrapper for explicit order IDs. Use that for preview/import so the API can distinguish `not found` from `not closed`. If `QueryOrders` is unavailable or incomplete for a response, fall back to checking closed/open order data only when the classification remains accurate.

## Frontend Design

Add a compact import panel component near `OrderHistoryTable`. Keep the main dashboard dense and operational: the import flow should not become a separate wizard unless the panel grows more complex.

States:

- Idle input state with textarea and disabled preview button until at least one syntactically valid ID is present.
- Loading state while Kraken is queried.
- Preview state with grouped rows and selectable ready rows.
- Importing state with disabled controls.
- Success state showing how many rows were written and how many were skipped.
- Error state for Kraken/API failures without clearing existing dashboard history.

## Error Handling

Return validation errors for empty input, too many IDs, malformed IDs, missing Kraken credentials, unreadable CSV history, and unwritable target CSV. Duplicate IDs in the request should be collapsed and reported once.

Kraken API failures should not modify CSV files. CSV writes should be append-only. If multiple target CSV files are involved, validate every target file is writable before writing any imported row.

CSV import writes must use a per-file lock. Immediately before appending, re-read existing `txid` values under that lock and skip any row that became a duplicate since preview. This prevents a scheduler run or another browser session from racing the import into duplicate history rows.

## Testing

- Unit tests for txid parsing and de-duplication.
- Unit tests for converting Kraken order payloads into CSV-compatible rows.
- Unit tests for exact CSV field ordering and CSV-injection sanitization.
- Unit tests for duplicate re-checking under the CSV write path.
- Backend API tests for authentication, CSRF, preview classification, duplicate skipping, unsupported order handling, and append-only import.
- Frontend tests for input parsing, preview rendering, import submission, and dashboard history refresh after success.
- GitNexus impact analysis before editing existing symbols and GitNexus change detection before committing implementation work.
