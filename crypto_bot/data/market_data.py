# crypto_bot/data/market_data.py

from crypto_bot.exchange.public_api import get_crypto_prices


def get_price(symbol: str) -> float:
    """Returns latest price for a single symbol e.g. "BTC"."""
    prices = get_crypto_prices([symbol])
    price = prices.get(symbol)
    if not price:
        raise ValueError(f"No price returned for {symbol}. Got: {prices}")
    return price


def get_candles(symbol: str, limit: int = 50) -> list[dict]:
    """Synthetic flat candles from spot price until Public exposes OHLC."""
    price = get_price(symbol)
    candle = {"close": price, "high": price, "low": price, "volume": 1.0}
    return [candle] * limit