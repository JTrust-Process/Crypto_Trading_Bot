# crypto_bot/data/market_data.py
#
# Fetches price data from Public API.
#
# Note: Public's API returns last-traded price quotes, not OHLC bars.
# get_candles() builds a synthetic candle list from the spot price so the
# strategy layer (which expects candles) works without changes. When Public
# adds a proper OHLC endpoint, swap in the real data here — engine.py and
# signal.py stay untouched.

from crypto_bot.exchange.public_api import get_crypto_prices


def get_price(symbol: str) -> float:
    """
    Returns the latest price for a single symbol (e.g. "BTC").
    Raises ValueError if the price is missing or zero.
    """
    prices = get_crypto_prices([symbol])
    price = prices.get(symbol + "USD")
    if not price:
        raise ValueError(f"No price returned for {symbol}USD")
    return price


def get_candles(symbol: str, limit: int = 50) -> list[dict]:
    """
    Returns a list of `limit` candle dicts using the current spot price.

    Each candle: {"close": float, "high": float, "low": float, "volume": float}

    This is a flat list (all candles identical) until Public exposes OHLC bars.
    The EMA-based strategy still works correctly — it just won't detect breakouts
    or volume spikes until real historical candles are available.
    """
    price = get_price(symbol)
    candle = {"close": price, "high": price, "low": price, "volume": 1.0}
    return [candle] * limit