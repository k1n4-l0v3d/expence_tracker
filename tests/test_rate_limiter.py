from datetime import datetime, timedelta
from app import RateLimiter


def test_not_blocked_initially():
    rl = RateLimiter(max_attempts=3, block_minutes=5)
    blocked, minutes = rl.is_blocked("1.2.3.4")
    assert blocked is False
    assert minutes == 0


def test_not_blocked_below_threshold():
    rl = RateLimiter(max_attempts=3, block_minutes=5)
    rl.record_failure("1.2.3.4")
    rl.record_failure("1.2.3.4")
    blocked, _ = rl.is_blocked("1.2.3.4")
    assert blocked is False


def test_blocked_after_max_attempts():
    rl = RateLimiter(max_attempts=3, block_minutes=5)
    for _ in range(3):
        rl.record_failure("1.2.3.4")
    blocked, minutes = rl.is_blocked("1.2.3.4")
    assert blocked is True
    assert minutes >= 1


def test_different_ips_are_independent():
    rl = RateLimiter(max_attempts=2, block_minutes=5)
    for _ in range(2):
        rl.record_failure("1.1.1.1")
    blocked, _ = rl.is_blocked("2.2.2.2")
    assert blocked is False


def test_reset_clears_block():
    rl = RateLimiter(max_attempts=2, block_minutes=5)
    for _ in range(2):
        rl.record_failure("1.2.3.4")
    rl.reset("1.2.3.4")
    blocked, _ = rl.is_blocked("1.2.3.4")
    assert blocked is False


def test_block_expires_after_time():
    rl = RateLimiter(max_attempts=1, block_minutes=5)
    rl.record_failure("1.2.3.4")
    # Manually expire the block
    from datetime import timezone
    rl._data["1.2.3.4"]["blocked_until"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    blocked, _ = rl.is_blocked("1.2.3.4")
    assert blocked is False
