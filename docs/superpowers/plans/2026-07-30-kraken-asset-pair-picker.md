# Kraken Asset Pair Picker Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build searchable Kraken pair selection that saves canonical backend pair keys.

**Architecture:** Backend owns Kraken pair metadata resolution and exposes compact suggestions through a new authenticated API route. Frontend `PairEditor` consumes that endpoint with a lightweight combobox and stores the selected canonical pair string.

**Tech Stack:** Python, FastAPI, pytest, Vue 3, TypeScript, Vitest.

---

## Chunk 1: Backend Resolver And API

### Task 1: Pair Metadata Resolver

**Files:**
- Modify: `krakendca/pair.py`
- Test: `tests/test_pair.py`

- [ ] Add failing unit tests proving `BTC/EUR`, `XBT/EUR`, `XBTEUR`, `BTCEUR`, and `XXBTZEUR` resolve to `XXBTZEUR`.
- [ ] Implement pair normalization helpers that match canonical key, `altname`, and `wsname` without needing network access beyond existing `asset_pairs`.
- [ ] Run `pytest tests/test_pair.py -q`.

### Task 2: Asset Pair Search Endpoint

**Files:**
- Create: `krakendca/web/routes_asset_pairs.py`
- Modify: `krakendca/web/app.py`
- Test: `tests/test_web_api.py`

- [ ] Add failing API tests for `GET /api/asset-pairs?q=XBTEUR`.
- [ ] Implement authenticated route returning compact suggestions.
- [ ] Wire the router into the FastAPI app.
- [ ] Run `pytest tests/test_web_api.py -q`.

## Chunk 2: Frontend Combobox

### Task 3: API Client

**Files:**
- Modify: `frontend/src/api.ts`
- Test: `frontend/src/__tests__/api.test.ts`

- [ ] Add failing test for `searchAssetPairs('XBTEUR')`.
- [ ] Add `AssetPairSuggestion` type and client function.
- [ ] Run `npm test -- --run src/__tests__/api.test.ts` from `frontend`.

### Task 4: Pair Editor Dropdown

**Files:**
- Modify: `frontend/src/components/PairEditor.vue`
- Test: `frontend/src/__tests__/pairEditor.test.ts`

- [ ] Add failing test that typing `XBTEUR` fetches suggestions and selecting `XBT/EUR` emits `pair: "XXBTZEUR"`.
- [ ] Implement searchable scrollable suggestion list.
- [ ] Run `npm test -- --run src/__tests__/pairEditor.test.ts` from `frontend`.

## Chunk 3: Verification

### Task 5: Regression Verification

**Files:**
- No production edits expected.

- [ ] Run backend focused tests: `pytest tests/test_pair.py tests/test_web_api.py -q`.
- [ ] Run frontend focused tests: `npm test -- --run src/__tests__/api.test.ts src/__tests__/pairEditor.test.ts`.
- [ ] Run broader relevant suites if focused tests reveal shared contract changes.
