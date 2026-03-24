# crypto_bot/utils/retry.py

import time

def retry(max_attempts=3, delay=2):
    def wrapper(func):
        def inner(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(delay)
        return inner
    return wrapper
