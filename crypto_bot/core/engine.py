# crypto_bot/core/engine.py

import time
from crypto_bot.data.market_data import get_mock_candles
from crypto_bot.strategy.signal import generate_signal
from crypto_bot.execution.trader import Trader
from crypto_bot.risk.manager import RiskManager
from crypto_bot.config.settings import SYMBOLS, POLL_INTERVAL, INITIAL_CAPITAL
from crypto_bot.logging.logger import log

def run():
    trader = Trader()
    risk = RiskManager(INITIAL_CAPITAL)

    while True:
        start = time.time()

        for symbol in SYMBOLS:
            candles = get_mock_candles(symbol)

            in_position = trader.position is not None
            signal = generate_signal(candles, in_position)

            price = candles[-1]["close"]
            log(f"{symbol} | Price: {price:.2f} | Signal: {signal}")

            exit_signal = trader.check_exit(price)
            if exit_signal:
                trader.sell(price, exit_signal)
                log(f"{symbol} exit: {exit_signal}")
                continue

            if signal == "BUY" and not in_position:
                size = risk.position_size(price)
                trader.buy(symbol, price, size)
                log(f"{symbol} BUY triggered")

            elif signal == "SELL" and in_position:
                trader.sell(price, "signal")
                log(f"{symbol} SELL triggered")

        elapsed = time.time() - start
        sleep_time = max(0, POLL_INTERVAL - elapsed)

        time.sleep(sleep_time)
