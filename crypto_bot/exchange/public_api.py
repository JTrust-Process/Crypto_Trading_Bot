# crypto_bot/exchange/public_api.py
#
# URLs taken directly from the working stock bot.
# Crypto symbols use bare format: "BTC", "ETH" with type="CRYPTO"

import uuid
import requests
from crypto_bot.config.settings import get_public_api_key
from crypto_bot.utils.retry import retry

AUTH_URL        = "https://api.public.com/userapiauthservice/personal/access-tokens"
ACCOUNT_URL     = "https://api.public.com/userapigateway/trading/account"
QUOTES_URL_TMPL = "https://api.public.com/userapigateway/marketdata/{accountId}/quotes"
ORDER_URL_TMPL  = "https://api.public.com/userapigateway/trading/{accountId}/order"

INSTRUMENT_TYPE = "CRYPTO"

_access_token: str | None = None


def _raise_with_body(resp: requests.Response) -> None:
    if resp.status_code >= 400:
        raise RuntimeError(
            f"HTTP {resp.status_code} from {resp.url}\n"
            f"Response body: {resp.text[:500]}"
        )


# ── Auth ──────────────────────────────────────────────────────────────────────

@retry(max_attempts=3, delay=2)
def get_access_token(validity_minutes: int = 60) -> str:
    """Exchange secret key for a temporary access token. Cached per process."""
    global _access_token
    if _access_token is not None:
        return _access_token
    resp = requests.post(
        AUTH_URL,
        headers={"Content-Type": "application/json"},
        json={"secret": get_public_api_key(), "validityInMinutes": validity_minutes},
        timeout=30,
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
    resp = requests.get(ACCOUNT_URL, headers=_headers(), timeout=30)
    _raise_with_body(resp)
    return resp.json()


def get_primary_account_id() -> str:
    data = get_accounts()
    accounts = data.get("accounts", [])
    if accounts:
        return accounts[0]["accountId"]
    raise RuntimeError(f"No accounts found. Full response: {data}")


# ── Market data ───────────────────────────────────────────────────────────────

@retry(max_attempts=3, delay=2)
def get_quotes(account_id: str, symbols: list[str]) -> list[dict]:
    """
    POST /userapigateway/marketdata/{accountId}/quotes
    symbols = ["BTC", "ETH"] — bare format confirmed working.
    """
    url = QUOTES_URL_TMPL.format(accountId=account_id)
    body = {
        "instruments": [
            {"symbol": s, "type": INSTRUMENT_TYPE} for s in symbols
        ]
    }
    resp = requests.post(url, headers=_headers(), json=body, timeout=30)
    _raise_with_body(resp)
    return resp.json().get("quotes", [])


def get_crypto_prices(symbols: list[str]) -> dict[str, float]:
    """
    Returns {"BTC": 67000.0, "ETH": 2300.5}
    symbols = ["BTC", "ETH"]
    """
    acct_id = get_primary_account_id()
    quotes = get_quotes(acct_id, symbols)

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
    amount: float,
    order_type: str = "MARKET",
) -> dict:
    """
    POST /userapigateway/trading/{accountId}/order

    Args:
        account_id: from get_primary_account_id()
        symbol:     bare crypto symbol e.g. "BTC", "ETH"
        side:       "BUY" or "SELL"
        amount:     notional USD value e.g. 10.00
        order_type: "MARKET" (default)

    Returns:
        { "orderId": "uuid...", "_clientOrderId": "uuid..." }
        Order placement is async — use get_order() to poll for fill status.
    """
    url = ORDER_URL_TMPL.format(accountId=account_id)
    order_id = str(uuid.uuid4())
    body = {
        "orderId": order_id,
        "instrument": {"symbol": symbol, "type": INSTRUMENT_TYPE},
        "orderSide": side.upper(),
        "orderType": order_type.upper(),
        "expiration": {"timeInForce": "DAY"},
        "amount": str(round(amount, 2)),
    }
    resp = requests.post(url, headers=_headers(), json=body, timeout=30)
    _raise_with_body(resp)
    result = resp.json()
    result["_clientOrderId"] = order_id
    return result


@retry(max_attempts=3, delay=2)
def get_order(account_id: str, order_id: str) -> dict:
    """Poll for order fill status after place_order()."""
    url = f"https://api.public.com/userapigateway/trading/{account_id}/order/{order_id}"
    resp = requests.get(url, headers=_headers(), timeout=30)
    _raise_with_body(resp)
    return resp.json()