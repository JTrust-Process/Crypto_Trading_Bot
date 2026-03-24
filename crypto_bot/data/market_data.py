# crypto_bot/data/market_data.py

import random

def get_mock_candles(symbol):
    # Simulated candles (replace with real API later)
    candles = []
    price = 100

    for _ in range(50):
        change = random.uniform(-1, 1)
        price += change
        candles.append({
            "close": price,
            "high": price + random.uniform(0, 1),
            "low": price - random.uniform(0, 1),
            "volume": random.uniform(100, 200)
        })

    return candles
