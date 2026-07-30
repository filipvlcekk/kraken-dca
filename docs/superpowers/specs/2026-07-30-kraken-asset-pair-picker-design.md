# Kraken Asset Pair Picker Design

## Goal

Let users search Kraken asset pairs by canonical key, altname, wsname, or common BTC/XBT aliases, then save the canonical Kraken key required by the DCA backend.

## Approach

Add backend pair resolution around Kraken `AssetPairs` metadata. The resolver returns compact pair suggestions and canonicalizes accepted inputs such as `BTC/EUR`, `XBT/EUR`, `XBTEUR`, `BTCEUR`, and `XXBTZEUR` to `XXBTZEUR`.

Expose the resolver through a web API endpoint used by the Vue pair editor. The editor remains editable, but it fetches matching suggestions as the user types and writes the selected canonical key into config.

## Data Flow

1. User types into the pair field.
2. Frontend calls `GET /api/asset-pairs?q=<query>`.
3. Backend fetches Kraken `AssetPairs`, filters locally, and returns compact suggestions.
4. User selects a suggestion.
5. Frontend stores `suggestion.pair`, for example `XXBTZEUR`.
6. Existing config save and scheduler reload behavior continues unchanged.

## Error Handling

If Kraken lookup fails, the endpoint returns a web API error without mutating config. Manual YAML/API entries are still accepted by syntax validation, but execution-time pair lookup can resolve common aliases before building the DCA pair.

## Testing

Backend tests cover alias matching and canonicalization. Web API tests cover the new endpoint. Frontend tests cover searching, scrollable suggestions, and selecting `XBTEUR` as canonical `XXBTZEUR`.
