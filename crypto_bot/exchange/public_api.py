# crypto_bot/exchange/public_api.py
#
# Built directly from Public API docs:
#   Auth:    POST /userapiauthservice/personal/access-tokens
#   Account: GET  /userapigateway/trading/v1/accounts
#   Quotes:  POST /userapigateway/marketdata/{accountId}/quotes
#   Order:   POST /userapigateway/trading/{accountId}/order  (no trailing s)
#
# Auth flow (two-step, runs once per process):
#   1. POST secret key → get temporary accessToken
#   2. Use accessToken as Bearer on all subsequent requests

import uuid
import requests
from crypto_bot.config.settings import get_public_api_key, get_public_base_url
from crypto_bot.utils.retry import retry

_access_token: str | None = None


def _base() -> str:
    return get_public_base_url()


def _raise_with_body(resp: requests.Response) -> None:
    """raise_for_status() with the response body included so errors are readable."""
    if resp.status_code >= 400:
        raise RuntimeError(
            f"HTTP {resp.status_code} from {resp.url}\n"
            f"Response body: {resp.text[:500]}"
        )


# ── Auth ──────────────────────────────────────────────────────────────────────

@retry(max_attempts=3, delay=2)
def get_access_token(validity_minutes: int = 60) -> str:
    """
    Exchange secret key for a temporary access token.
    Cached for the lifetime of the process (one GHA run = one process).

    POST /userapiauthservice/personal/access-tokens
    { "secret": "...", "validityInMinutes": 60 }
    → { "accessToken": "..." }
    """
    global _access_token
    if _access_token is not None:
        return _access_token

    url = f"{_base()}/userapiauthservice/personal/access-tokens"
    resp = requests.post(
        url,
        json={"secret": get_public_api_key(), "validityInMinutes": validity_minutes},
        timeout=10,
    )
    _raise_with_body(resp)

    token = resp.json().get("accessToken")
    if not token:
        raise RuntimeError(f"No accessToken in response: {resp.text[:300]}")

    _access_token = token
    return _access_token


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json",
    }


# ── Account ───────────────────────────────────────────────────────────────────

@retry(max_attempts=3, delay=2)
def get_accounts() -> dict:
    """
    GET /userapigateway/trading/v1/accounts
    Returns account list including accountId needed for all other calls.
    """
    url = f"{_base()}/userapigateway/trading/v1/accounts"
    resp = requests.get(url, headers=_headers(), timeout=10)
    _raise_with_body(resp)
    return resp.json()


def get_primary_account_id() -> str:
    data = get_accounts()
    accounts = data.get("accounts", [])
    if accounts:
        return accounts[0]["accountId"]
    raise RuntimeError(
        f"No accounts found. Full response: {data}"
    )


# ── Market data ───────────────────────────────────────────────────────────────

@retry(max_attempts=3, delay=2)
def get_quotes(account_id: str, symbols: list[str]) -> list[dict]:
    """
    POST /userapigateway/marketdata/{accountId}/quotes
    Body: { "instruments": [{ "symbol": "BTCUSD", "type": "CRYPTO" }] }
    Returns list of quote objects with "last", "bid", "ask" etc.
    """
    url = f"{_base()}/userapigateway/marketdata/{account_id}/quotes"
    body = {
        "instruments": [
            {"symbol": sym, "type": "CRYPTO"} for sym in symbols
        ]
    }
    resp = requests.post(url, headers=_headers(), json=body, timeout=10)
    _raise_with_body(resp)
    return resp.json().get("quotes", [])


def get_crypto_prices(symbols: list[str]) -> dict[str, float]:
    """
    Returns {"BTCUSD": 67000.0, "ETHUSD": 2300.5}
    Pass symbols without USD suffix e.g. ["BTC", "ETH"].
    """
    acct_id = get_primary_account_id()
    pairs = [s + "USD" for s in symbols]
    quotes = get_quotes(acct_id, pairs)

    prices = {}
    for q in quotes:
        sym = q.get("instrument", {}).get("symbol")
        last = q.get("last")
        if sym and last:
            try:
                prices[sym] = float(last)
            except (ValueError, TypeError):
                pass

    return prices


# ── Order placement ───────────────────────────────────────────────────────────

@retry(max_attempts=3, delay=2)
def place_order(
    account_id: str,
    symbol: str,
    side: str,
    amount: float,               # notional USD amount to buy/sell
    order_type: str = "MARKET",
) -> dict:
    """
    POST /userapigateway/trading/{accountId}/order

    Args:
        account_id: from get_primary_account_id()
        symbol:     e.g. "BTCUSD"
        side:       "BUY" or "SELL"
        amount:     notional USD value of the order (e.g. 10.00 = $10 of BTC)
        order_type: "MARKET" (default)

    Returns:
        { "orderId": "uuid..." } — submission confirmed, not execution.
        Use get_order(orderId) to poll for fill status.

    Notes:
        - orderId is a UUID we generate — serves as dedup key.
          If the same orderId is resubmitted (e.g. after a read timeout),
          Public treats it as idempotent and won't double-fill.
        - expiration DAY = order expires at end of trading day (standard for market orders).
    """
    url = f"{_base()}/userapigateway/trading/{account_id}/order"
    order_id = str(uuid.uuid4())
    body = {
        "orderId": order_id,
        "instrument": {
            "symbol": symbol,
            "type": "CRYPTO",
        },
        "orderSide": side.upper(),       # "BUY" or "SELL"
        "orderType": order_type.upper(), # "MARKET"
        "expiration": {
            "type": "DAY",
        },
        "amount": str(round(amount, 2)), # notional USD as string
    }
    resp = requests.post(url, headers=_headers(), json=body, timeout=10)
    _raise_with_body(resp)
    result = resp.json()
    result["_clientOrderId"] = order_id  # attach so caller can log it
    return result


@retry(max_attempts=3, delay=2)
def get_order(account_id: str, order_id: str) -> dict:
    """
    GET /userapigateway/trading/{accountId}/order/{orderId}
    Poll for order status after place_order() returns.
    """
    url = f"{_base()}/userapigateway/trading/{account_id}/order/{order_id}"
    resp = requests.get(url, headers=_headers(), timeout=10)
    _raise_with_body(resp)
    return resp.json()