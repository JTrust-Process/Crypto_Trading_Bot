# crypto_bot/utils/retry.py

import time
import functools


def retry(max_attempts: int = 3, delay: float = 2.0):
    """
    Decorator that retries a function on exception.

    Usage:
        @retry(max_attempts=3, delay=2)
        def flaky_api_call(): ...
    """
    def decorator(func):
        @functools.wraps(func)  # preserves __name__, __doc__ for debugging
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if attempt < max_attempts:
                        print(f"[retry] {func.__name__} attempt {attempt}/{max_attempts} failed: {e} — retrying in {delay}s")
                        time.sleep(delay)
            raise last_exc
        return wrapper
    return decorator