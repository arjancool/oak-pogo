"""Limits on failed logins: per username and address, taken before the password check, with
IPv6 counted per /64 (issue #39)."""

from __future__ import annotations

import threading
from typing import Any

import pytest

from app.api.v1 import auth
from app.core.errors import RateLimitedError
from app.core.ratelimit import SlidingWindowLimiter, address_key
from tests.conftest import PASSWORD, Api

WRONG = "verkeerd wachtwoord"


class Addresses:
    """Lets a test choose the address every request comes from."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.current = "192.0.2.1"
        monkeypatch.setattr(auth, "_client_ip", lambda _request: self.current)


@pytest.fixture
def addresses(owner: Api, monkeypatch: pytest.MonkeyPatch) -> Addresses:
    owner.post("/api/v1/auth/logout")
    return Addresses(monkeypatch)


def _fail(owner: Api, times: int, username: str = "eigenaar") -> None:
    for _ in range(times):
        assert owner.login(username, WRONG).status_code == 401


def test_another_address_can_still_log_in(owner: Api, container: Any, addresses: Addresses) -> None:
    _fail(owner, container.settings.login_max_attempts)
    blocked = owner.login("eigenaar")
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers
    addresses.current = "198.51.100.7"
    assert owner.login("eigenaar").status_code == 200, "the right password from elsewhere still works"


def test_an_address_is_blocked_for_every_username(owner: Api, container: Any, addresses: Addresses) -> None:
    attempts = container.settings.login_max_attempts
    for number in range(3):
        _fail(owner, attempts, f"iemand{number}")
    assert owner.login("eigenaar").status_code == 429
    addresses.current = "198.51.100.7"
    assert owner.login("eigenaar").status_code == 200


def test_many_addresses_only_slow_a_username_down(owner: Api, container: Any, addresses: Addresses) -> None:
    now = [0.0]
    container.login_slow_by_user = SlidingWindowLimiter(1, 5, clock=lambda: now[0])
    attempts = container.settings.login_max_attempts
    for number in range(container.login_by_user.limit // attempts):
        addresses.current = f"203.0.113.{number}"
        _fail(owner, attempts)
    addresses.current = "198.51.100.7"
    assert owner.login("eigenaar", WRONG).status_code == 401, "one attempt per few seconds still goes through"
    slowed = owner.login("eigenaar")
    assert slowed.status_code == 429 and int(slowed.headers["Retry-After"]) <= 6
    now[0] += 6
    assert owner.login("eigenaar").status_code == 200, "after a short wait the right password works"


def test_a_successful_login_gives_its_places_back(owner: Api, container: Any, addresses: Addresses) -> None:
    attempts = container.settings.login_max_attempts
    _fail(owner, attempts - 1)
    assert owner.login("eigenaar").status_code == 200
    owner.post("/api/v1/auth/logout")
    _fail(owner, attempts - 1)
    assert owner.login("eigenaar").status_code == 200, "failures from this address were forgiven"
    owner.post("/api/v1/auth/logout")
    ip_hits = 2 * (attempts - 1)
    assert container.login_by_ip.blocked("ip:192.0.2.1") is None
    for _ in range(container.login_by_ip.limit - ip_hits):
        container.login_by_ip.hit("ip:192.0.2.1")
    assert owner.login("eigenaar").status_code == 429, "only the failures counted for the address"


def test_the_place_is_taken_before_the_password_is_checked(
    owner: Api, container: Any, addresses: Addresses, monkeypatch: pytest.MonkeyPatch
) -> None:
    during: list[bool] = []
    original = auth.verify_password

    def watching(stored: str | None, password: str) -> bool:
        during.append(container.login_by_pair.blocked("pair:192.0.2.1|eigenaar") is not None)
        return original(stored, password)

    container.login_by_pair = SlidingWindowLimiter(1, 900)
    monkeypatch.setattr(auth, "verify_password", watching)
    assert owner.login("eigenaar", WRONG).status_code == 401
    assert during == [True], "a second attempt at the same time would already be refused"


def test_attempts_at_the_same_time_cannot_pass_the_limit(container: Any) -> None:
    limit = container.login_by_pair.limit
    start = threading.Barrier(50)
    passed: list[bool] = []
    lock = threading.Lock()

    def attempt() -> None:
        start.wait()
        try:
            auth._reserve_login(container, "192.0.2.9", "eigenaar")
            ok = True
        except RateLimitedError:
            ok = False
        with lock:
            passed.append(ok)

    threads = [threading.Thread(target=attempt) for _ in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert passed.count(True) == limit


def test_ipv6_counts_per_64_block(owner: Api, container: Any, addresses: Addresses) -> None:
    assert address_key("2001:db8:1:2::1") == address_key("2001:db8:1:2:ffff:ffff:ffff:9") == "2001:db8:1:2::/64"
    assert address_key("2001:db8:1:3::1") != address_key("2001:db8:1:2::1")
    assert address_key("::ffff:192.0.2.5") == "192.0.2.5"
    assert address_key("192.0.2.5") == "192.0.2.5"
    assert address_key("testclient") == "testclient"

    addresses.current = "2001:db8:1:2::1"
    _fail(owner, container.settings.login_max_attempts)
    addresses.current = "2001:db8:1:2::abcd"
    assert owner.login("eigenaar").status_code == 429, "a new address in the same /64 is the same address"
    addresses.current = "2001:db8:1:3::1"
    assert owner.login("eigenaar", PASSWORD).status_code == 200
