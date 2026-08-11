"""Internal Kraken REST client tests."""

import httpx
import pytest

from krakendca.kraken_client import KrakenClient


@pytest.fixture(autouse=True)
def clear_kraken_nonce_state():
    nonce_state = getattr(KrakenClient, "_last_nonce_by_key", None)
    if nonce_state is not None:
        nonce_state.clear()
    yield
    nonce_state = getattr(KrakenClient, "_last_nonce_by_key", None)
    if nonce_state is not None:
        nonce_state.clear()


def test_kraken_client_close_closes_httpx_client() -> None:
    client = KrakenClient()

    client.close()

    assert client._client.is_closed


def test_kraken_client_context_manager_closes_httpx_client() -> None:
    with KrakenClient() as client:
        assert not client._client.is_closed

    assert client._client.is_closed


def test_nonce_is_unique_across_clients_for_same_api_key(monkeypatch) -> None:
    monkeypatch.setattr("krakendca.kraken_client.time.time", lambda: 1234.567)
    first = KrakenClient("same-public-key", "")
    second = KrakenClient("same-public-key", "")

    assert first._nonce() == "1234567"
    assert second._nonce() == "1234568"


def test_nonce_state_is_keyed_by_api_key(monkeypatch) -> None:
    monkeypatch.setattr("krakendca.kraken_client.time.time", lambda: 1234.567)
    first = KrakenClient("first-key", "")
    second = KrakenClient("second-key", "")

    assert first._nonce() == "1234567"
    assert second._nonce() == "1234567"


def test_create_api_signature_matches_kraken_documentation_example() -> None:
    client = KrakenClient(
        "",
        "kQH5HW/8p1uGOVjbgWA7FunAmGO8lsSUXNsu3eow76sz84Q18fWxnyRzBHCd3"
        "pd5nE9qa99HAZtuZuj6F1huXg==",
    )
    payload = {
        "nonce": "1616492376594",
        "ordertype": "limit",
        "pair": "XBTUSD",
        "price": 37500,
        "type": "buy",
        "volume": 1.25,
    }

    signature = client.create_api_signature(
        "/0/private/AddOrder",
        payload,
    )

    assert signature == (
        "4/dpxb3iT4tp/ZCVEwSnEsLxx0bqyhLpdfOpc6fn7OR8+UClSV5n9E6aSS8"
        "MPtnRfp32bAb0nmbRn6H8ndwLUQ=="
    )


def test_create_api_signature_rejects_malformed_private_key() -> None:
    client = KrakenClient("", "not a base64 key")

    with pytest.raises(ValueError) as exc_info:
        client.create_api_signature("/0/private/Balance", {"nonce": "1"})

    assert str(exc_info.value) == "Incorrect Kraken API private key."


def test_public_request_returns_result_and_sets_user_agent() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"error": [], "result": {"unixtime": 123}},
        )

    client = KrakenClient(
        "",
        "",
        transport=httpx.MockTransport(handler),
    )

    assert client.get_time() == 123
    assert requests[0].url.path == "/0/public/Time"
    assert requests[0].headers["User-Agent"].startswith("kraken-dca/")


def test_request_error_raises_connection_error_without_secret() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    private_key = (
        "kQH5HW/8p1uGOVjbgWA7FunAmGO8lsSUXNsu3eow76sz84Q18fWxnyRzBHCd3"
        "pd5nE9qa99HAZtuZuj6F1huXg=="
    )
    client = KrakenClient(
        "public-key",
        private_key,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ConnectionError) as exc_info:
        client.get_balance()

    assert str(exc_info.value) == (
        "Kraken API request failed -> network down"
    )
    assert private_key not in str(exc_info.value)


def test_private_request_signs_payload_without_leaking_secret() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"error": [], "result": {"ZUSD": "10.0"}},
        )

    client = KrakenClient(
        "public-key",
        "kQH5HW/8p1uGOVjbgWA7FunAmGO8lsSUXNsu3eow76sz84Q18fWxnyRzBHCd3"
        "pd5nE9qa99HAZtuZuj6F1huXg==",
        transport=httpx.MockTransport(handler),
    )

    assert client.get_balance() == {"ZUSD": "10.0"}
    request = requests[0]
    assert request.url.path == "/0/private/Balance"
    assert request.headers["API-Key"] == "public-key"
    assert request.headers["API-Sign"]
    assert "API private" not in request.content.decode()


def test_kraken_error_field_raises_value_error() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"error": ["EQuery:Unknown asset pair"]},
        )

    client = KrakenClient(
        "",
        "",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ValueError) as exc_info:
        client.get_pair_ticker("XETHZEUR")

    assert str(exc_info.value) == (
        "Kraken API error -> EQuery:Unknown asset pair"
    )
    assert requests[0].method == "POST"
    assert requests[0].content.decode() == "pair=XETHZEUR"


@pytest.mark.parametrize(
    "response_json",
    [
        {"error": []},
        ["unexpected-list"],
    ],
)
def test_malformed_kraken_response_raises_value_error(response_json) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=response_json,
        )

    client = KrakenClient(
        "",
        "",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ValueError) as exc_info:
        client.get_time()

    assert str(exc_info.value) == (
        "Response received from API was wrongly formatted."
    )


def test_create_order_uses_add_order_payload_names() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "error": [],
                "result": {
                    "txid": ["ORDER-TXID"],
                    "descr": {"order": "buy 1.0 XBTUSD @ limit 100"},
                },
            },
        )

    client = KrakenClient(
        "public-key",
        "kQH5HW/8p1uGOVjbgWA7FunAmGO8lsSUXNsu3eow76sz84Q18fWxnyRzBHCd3"
        "pd5nE9qa99HAZtuZuj6F1huXg==",
        transport=httpx.MockTransport(handler),
    )

    result = client.create_order(
        "XBTUSD",
        "buy",
        "limit",
        100.0,
        1.0,
        "fciq",
    )

    body = requests[0].content.decode()
    assert result["txid"] == ["ORDER-TXID"]
    assert "pair=XBTUSD" in body
    assert "type=buy" in body
    assert "ordertype=limit" in body
    assert "price=100.0" in body
    assert "volume=1.0" in body
    assert "oflags=fciq" in body
