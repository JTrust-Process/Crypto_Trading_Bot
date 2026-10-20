import json

with open("state.json") as f:
    state = json.load(f)

for symbol, prices in state["price_history"].items():
    k9  = 2 / 10
    k21 = 2 / 22
    ema9  = [prices[0]]
    ema21 = [prices[0]]
    for p in prices[1:]:
        ema9.append(p * k9 + ema9[-1] * (1 - k9))
        ema21.append(p * k21 + ema21[-1] * (1 - k21))

    print(f"\n{symbol} — crossover history:")
    for i in range(1, len(prices)):
        gap_now  = ema9[i]  - ema21[i]
        gap_prev = ema9[i-1] - ema21[i-1]
        crossed_up   = gap_prev <= 0 and gap_now > 0
        crossed_down = gap_prev >= 0 and gap_now < 0
        marker = " ← BUY SIGNAL" if crossed_up else (" ← SELL SIGNAL" if crossed_down else "")
        print(f"  [{i:02d}] price={prices[i]:.2f}  gap={gap_now:+.2f}{marker}")