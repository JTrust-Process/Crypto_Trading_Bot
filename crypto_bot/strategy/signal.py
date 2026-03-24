# crypto_bot/strategy/signal.py

def ema(values, period):
    k = 2 / (period + 1)
    ema_vals = [values[0]]

    for price in values[1:]:
        ema_vals.append(price * k + ema_vals[-1] * (1 - k))

    return ema_vals


def generate_signal(candles, in_position):
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    volumes = [c["volume"] for c in candles]

    if len(closes) < 30:
        return "HOLD"

    # Indicators
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)

    recent_high = max(highs[-20:])
    avg_volume = sum(volumes[-20:]) / 20

    current_price = closes[-1]
    current_volume = volumes[-1]

    # Momentum + Breakout Conditions
    breakout = current_price > recent_high
    volume_spike = current_volume > 1.5 * avg_volume
    momentum = ema9[-1] > ema21[-1]

    # Entry
    if not in_position and momentum:
        return "BUY"

    # Exit
    if in_position:
        if ema9[-1] < ema21[-1]:
            return "SELL"

    return "HOLD"
