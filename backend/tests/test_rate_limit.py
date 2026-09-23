"""Tests for rate limiting categories and fixed-window limits (Phase 8)."""

import threading

from backend.middleware.rate_limit import (
    RateLimiter,
    classify_request,
)


def test_classify_sensitive_endpoints():
    assert classify_request("/api/auth/login") == "login"
    assert classify_request("/api/auth/refresh") == "refresh"
    assert classify_request("/api/auth/change-password") == "password"
    assert classify_request("/api/email/test") == "email"


def test_classify_password_suffixes():
    assert classify_request("/api/users/1/change-password") == "password"
    assert classify_request("/api/users/1/password") == "password"


def test_classify_resend_suffix_is_email():
    assert (
        classify_request(
            "/api/reconciliation/runs/5/email-deliveries/12/resend"
        )
        == "email"
    )


def test_classify_unknown_paths_are_none():
    assert classify_request("/api/settings/application") is None
    assert classify_request("/api/health") is None
    assert classify_request("/api/imports/12") is None
    assert classify_request("/api/reconciliation/runs/5/email-deliveries") is None


class _FakeRequest:
    def __init__(self, path, method="POST", headers=None, remote_addr=None):
        self.path = path
        self.method = method
        self.headers = headers or {}
        self.remote_addr = remote_addr


def test_upload_category_requires_post(monkeypatch):
    limiter = RateLimiter({"upload": (1, 60)})
    post = _FakeRequest("/api/imports", method="POST")
    monkeypatch.setattr("backend.middleware.rate_limit.request", post)
    assert limiter.check() is None          # first request allowed
    assert limiter.check() == "upload"      # second request blocked

    get = _FakeRequest("/api/imports", method="GET")
    monkeypatch.setattr("backend.middleware.rate_limit.request", get)
    assert limiter.check() is None          # GET is never limited


def test_fixed_window_limits():
    limiter = RateLimiter({"email": (2, 60)})
    assert limiter.allow("email", "198.51.100.1") is True
    assert limiter.allow("email", "198.51.100.1") is True
    assert limiter.allow("email", "198.51.100.1") is False

    uploads = RateLimiter({"upload": (3, 60)})
    for _ in range(3):
        assert uploads.allow("upload", "198.51.100.2") is True
    assert uploads.allow("upload", "198.51.100.2") is False


def test_unknown_category_always_allowed():
    limiter = RateLimiter({"login": (1, 60)})
    assert limiter.allow("email", "198.51.100.9") is True


def test_client_identifier_prefers_x_real_ip(monkeypatch):
    monkeypatch.setattr(
        "backend.middleware.rate_limit.request",
        _FakeRequest("/api/auth/login", headers={"X-Real-IP": "203.0.113.7"}),
    )
    limiter = RateLimiter()
    assert limiter._client_identifier(None) == "203.0.113.7"


def test_client_identifier_falls_back_to_remote_addr(monkeypatch):
    req = _FakeRequest("/api/auth/login", remote_addr="192.0.2.9")
    monkeypatch.setattr("backend.middleware.rate_limit.request", req)
    limiter = RateLimiter()
    assert limiter._client_identifier(None) == "192.0.2.9"


def test_exempt_prefixes():
    limiter = RateLimiter({"login": (1, 60)}, exempt_ip_prefixes=["127.0.0.1"])
    assert limiter.is_exempt("127.0.0.1") is True
    assert limiter.is_exempt("203.0.113.7") is False


def test_default_limits_table_covers_all_categories():
    limiter = RateLimiter()
    expected = {
        "login": (5, 60),
        "refresh": (30, 60),
        "password": (5, 60),
        "email": (10, 60),
        "upload": (5, 60),
    }
    assert limiter._limits == expected
    # Every category must actually trigger its own limit.
    for category, (count, _window) in expected.items():
        trial = RateLimiter()
        for i in range(count):
            assert trial.allow(category, "198.51.100.7") is True, (category, i)
        assert trial.allow(category, "198.51.100.7") is False


def test_default_limits_allow_healthy_traffic(monkeypatch):
    limiter = RateLimiter({"email": (10, 60)})
    req = _FakeRequest("/api/email/test", method="POST")
    monkeypatch.setattr("backend.middleware.rate_limit.request", req)
    for _ in range(10):
        assert limiter.check() is None
    assert limiter.check() == "email"


def test_window_advance_resets_counter():
    limiter = RateLimiter({"email": (1, 60)})
    assert limiter.allow("email", "198.51.100.4", now=100.0) is True
    assert limiter.allow("email", "198.51.100.4", now=100.0) is False
    # New bucket one minute later starts fresh.
    assert limiter.allow("email", "198.51.100.4", now=160.0) is True
    assert limiter.allow("email", "198.51.100.4", now=160.0) is False


def test_stale_buckets_are_pruned():
    limiter = RateLimiter({"email": (5, 60)})
    limiter.allow("email", "198.51.100.4", now=100.0)
    limiter.allow("email", "198.51.100.4", now=220.0)
    keys = [k for k in limiter._counters if k[1] == "198.51.100.4"]
    assert len(keys) == 1
    assert keys[0][2] == 3  # only the current bucket (220 // 60) remains


def test_versioned_paths_use_same_categories():
    assert classify_request("/api/v1/auth/login") == "login"
    assert classify_request("/api/v1/auth/refresh") == "refresh"
    assert classify_request("/api/v1/users/1/password") == "password"


def test_upload_rate_limit_counts_only_post(monkeypatch):
    limiter = RateLimiter({"upload": (1, 60)})
    req = _FakeRequest("/api/imports", method="POST")
    monkeypatch.setattr("backend.middleware.rate_limit.request", req)
    assert limiter.check() is None
    assert limiter.check() == "upload"


def test_register_rate_limits_respects_enable_flag(monkeypatch):
    from backend.middleware.rate_limit import register_rate_limits, _rate_limiter

    class _FakeApp:
        def __init__(self, config):
            self.config = config
            self.hooks = []

        def before_request(self, hook):
            self.hooks.append(hook)

    disabled = _FakeApp({"RATE_LIMIT_ENABLED": False})
    register_rate_limits(disabled)
    assert disabled.hooks == []

    enabled = _FakeApp({"RATE_LIMIT_ENABLED": True})
    register_rate_limits(enabled)
    assert len(enabled.hooks) == 1
    assert enabled.hooks[0].__name__ == "before_request_rate_limit"
    # The module-wide limiter picks up the app's exempt-IP list.
    assert _rate_limiter.is_exempt("127.0.0.1") is True  # default dev exempt


class TestConcurrentAccess:
    """Concurrent callers must never exceed the fixed-window limit.

    The counter update in ``allow()`` runs under an in-process lock. Without
    it, racing threads could both read the count, both append, and together
    over-admit (check-then-act lost update).
    """

    def _hammer(self, limiter, category, client, now, results, barrier):
        barrier.wait()
        results.append(limiter.allow(category, client, now=now))

    def test_concurrent_calls_never_exceed_limit(self):
        limit = 5
        limiter = RateLimiter({"login": (limit, 60)})
        now = 100.0  # fixed window so every thread hits the same bucket
        threads = 200
        barrier = threading.Barrier(threads)
        results = []
        workers = [
            threading.Thread(
                target=self._hammer,
                args=(limiter, "login", "198.51.100.50", now, results, barrier),
            )
            for _ in range(threads)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()

        granted = sum(1 for r in results if r is True)
        assert granted == limit
        assert sum(1 for r in results if r is False) == threads - limit
        # The stored fixed-window counter records every attempt in the bucket.
        # Under the lock no attempt is lost or double-recorded, even though
        # 200 threads appended concurrently.
        bucket_keys = [k for k in limiter._counters if k[1] == "198.51.100.50"]
        assert len(bucket_keys) == 1
        assert len(limiter._counters[bucket_keys[0]]) == threads
        assert set(limiter._counters[bucket_keys[0]]) == {now}

    def test_concurrent_clients_are_isolated(self):
        limiter = RateLimiter({"email": (2, 60)})
        clients = ["203.0.113.1", "203.0.113.2", "203.0.113.3"]
        threads = 30
        barrier = threading.Barrier(threads)
        results = {client: [] for client in clients}
        workers = []
        for i in range(threads):
            client = clients[i % len(clients)]
            worker = threading.Thread(
                target=self._hammer,
                args=(limiter, "email", client, 100.0, results[client], barrier),
            )
            workers.append(worker)
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()

        for client in clients:
            granted = sum(1 for r in results[client] if r is True)
            assert granted == 2
            key = next(k for k in limiter._counters if k[1] == client)
            # Fixed-window counters record every attempt; concurrent clients
            # must not leak attempts into each other's buckets.
            assert len(limiter._counters[key]) == threads // len(clients)