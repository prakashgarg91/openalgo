import pytest

from services.phone import otp


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def book():
    clock = Clock()
    return otp.OtpBook("secret", {}, {}, clock), clock


def test_phone_normalisation():
    assert otp.normalise_phone("98765 43210") == "+919876543210"
    assert otp.normalise_phone("+91-98765-43210") == "+919876543210"
    assert otp.normalise_phone("919876543210") == "+919876543210"
    assert otp.normalise_phone("+14155550123") == "+14155550123"
    for bad in ("", None, "12345", "5876543210", "abc", "+0123456789"):
        assert otp.normalise_phone(bad) is None


def test_code_works_once(book):
    b, _ = book
    code = b.issue("login", "+919876543210").code
    assert len(code) == 6 and code.isdigit()
    assert b.verify("login", "+919876543210", code).ok
    assert b.verify("login", "+919876543210", code).reason == "none"


def test_wrong_codes_burn_the_code_after_five(book):
    b, _ = book
    phone = "+919876543210"
    code = b.issue("login", phone).code
    wrong = "000000" if code != "000000" else "111111"
    reasons = [b.verify("login", phone, wrong).reason for _ in range(5)]
    assert reasons == ["wrong"] * 4 + ["locked"]
    assert not b.verify("login", phone, code).ok  # the right code no longer works


def test_expiry(book):
    b, clock = book
    code = b.issue("login", "+919876543210").code
    clock.now += otp.TTL_SECONDS + 1
    assert b.verify("login", "+919876543210", code).reason == "expired"


def test_resend_cooldown_and_hourly_cap(book):
    b, clock = book
    phone = "+919876543210"
    assert b.issue("login", phone).code
    throttled = b.issue("login", phone)
    assert throttled.code is None and throttled.retry_after > 0
    sent = 1
    for _ in range(10):
        clock.now += otp.RESEND_AFTER_SECONDS + 1
        if b.issue("login", phone).code:
            sent += 1
    assert sent == otp.MAX_SENDS_PER_HOUR


def test_purposes_and_phones_do_not_cross(book):
    b, _ = book
    code = b.issue("login", "+919876543210").code
    assert not b.verify("register", "+919876543210", code).ok
    assert not b.verify("login", "+919876543211", code).ok


def test_code_is_not_stored_in_clear(book):
    b, _ = book
    code = b.issue("login", "+919876543210").code
    assert code not in repr(b._store)


def test_mask():
    assert otp.mask_phone("+919876543210") == "+91********10"


def test_parallel_guesses_cannot_beat_the_attempt_cap():
    import threading
    import time

    class SlowStore(dict):
        def get(self, key, default=None):
            value = super().get(key, default)
            time.sleep(0.002)  # a yield point, so unlocked check-then-act interleaves
            return value

    b = otp.OtpBook("secret", SlowStore(), {}, Clock())
    phone = "+919876543210"
    code = b.issue("login", phone).code
    wrong = "000000" if code != "000000" else "111111"
    verdicts = []
    barrier = threading.Barrier(40)

    def guess():
        barrier.wait()
        verdicts.append(b.verify("login", phone, wrong).reason)

    threads = [threading.Thread(target=guess) for _ in range(40)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(v in ("wrong", "locked") for v in verdicts) == otp.MAX_ATTEMPTS


def test_wrong_guesses_cap_per_hour_blocks_new_codes_and_old_ones(book):
    b, clock = book
    phone = "+919876543210"
    for _ in range(2):
        b.issue("login", phone)
        for _ in range(5):
            b.verify("login", phone, "000000")
        clock.now += otp.RESEND_AFTER_SECONDS + 1
    blocked = b.issue("login", phone)
    assert blocked.code is None and blocked.retry_after > 0
    clock.now += otp.HOUR  # the hour passes and the number works again
    assert b.issue("login", phone).code
