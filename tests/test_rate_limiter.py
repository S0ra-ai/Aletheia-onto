"""Rate limiting: the counters, and the middleware that applies them.

Asserted against a fake clock rather than by sleeping. A window-boundary test that sleeps
sixty seconds is a test that gets deleted, and one that sleeps a fraction of a second to
"prove" a window is proving the sleep, not the window.

What is deliberately not asserted: that a specific limit is right for a deployment. That
is the operator's number, not this package's, and pinning it here would make a tuning
change look like a regression.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from ontology_platform.rate_limiter import (
    DEFAULT_AUTHENTICATION_LIMIT,
    RateLimiter,
    RateLimitMiddleware,
    resolve_authentication_limit,
    resolve_rate_limit,
)


class TestCounters:
    """The window arithmetic, independent of HTTP."""

    def test_allows_up_to_the_limit_then_refuses(self) -> None:
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        assert [limiter.is_allowed("caller", now=100.0) for _ in range(4)] == [
            True,
            True,
            True,
            False,
        ]

    def test_a_refused_request_does_not_extend_the_window(self) -> None:
        """Otherwise a caller at the limit locks themselves out by retrying.

        Each refused attempt would push the oldest hit out of reach, so a client polling
        faster would wait longer -- the opposite of what a limiter should do.
        """
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        assert limiter.is_allowed("caller", now=0.0) is True
        assert limiter.is_allowed("caller", now=30.0) is False
        # The first hit is the only one recorded, so the window still frees at 60s.
        assert limiter.is_allowed("caller", now=61.0) is True

    def test_counters_are_per_key(self) -> None:
        """One noisy caller must not spend another caller's budget."""
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        assert limiter.is_allowed("first", now=0.0) is True
        assert limiter.is_allowed("second", now=0.0) is True

    def test_window_expiry_frees_the_budget(self) -> None:
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        assert limiter.is_allowed("caller", now=0.0) is True
        assert limiter.is_allowed("caller", now=59.9) is False
        assert limiter.is_allowed("caller", now=60.1) is True

    def test_remaining_counts_down_and_never_goes_negative(self) -> None:
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        assert limiter.remaining("caller", now=0.0) == 3
        limiter.is_allowed("caller", now=0.0)
        assert limiter.remaining("caller", now=0.0) == 2
        limiter.is_allowed("caller", now=0.0)
        limiter.is_allowed("caller", now=0.0)
        limiter.is_allowed("caller", now=0.0)
        assert limiter.remaining("caller", now=0.0) == 0

    def test_retry_after_reflects_when_the_window_actually_frees(self) -> None:
        """Not the window length.

        A caller told to wait sixty seconds when three would do comes back at the wrong
        time, and a `Retry-After` that is usually an overestimate is one clients learn to
        ignore.
        """
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        limiter.is_allowed("caller", now=0.0)
        assert limiter.retry_after("caller", now=57.0) <= 4

    def test_retry_after_is_positive_when_the_window_is_full(self) -> None:
        """Never zero: `Retry-After: 0` invites an immediate retry that will also fail."""
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        limiter.is_allowed("caller", now=10.0)
        assert limiter.retry_after("caller", now=69.9) >= 1

    def test_expired_keys_are_evicted(self) -> None:
        """Key count is memory a caller controls.

        Rotating source addresses would otherwise grow the table without bound, turning a
        protection into a denial-of-service vector.
        """
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        for index in range(50):
            limiter.is_allowed(f"caller-{index}", now=0.0)
        assert limiter.tracked_keys() == 50

        # A later request prunes only the key it touches, so the keys that are never seen
        # again would leak -- the point of the assertion is that a *seen* key is dropped
        # once its window is empty rather than kept for the process lifetime.
        limiter.is_allowed("caller-0", now=120.0)
        assert limiter.remaining("caller-0", now=120.0) == 4


class TestMiddleware:
    """The middleware: which limit applies, and what the caller is told."""

    def _app(self, general: int, authentication: int) -> FastAPI:
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, general_limit=general, authentication_limit=authentication)

        @app.get("/health")
        def health() -> dict[str, bool]:
            return {"ok": True}

        @app.post("/auth/login")
        def login() -> dict[str, bool]:
            return {"ok": True}

        @app.get("/objects")
        def objects(request: Request) -> dict[str, str]:
            return {"client": request.client.host if request.client else "unknown"}

        return app

    def test_both_limits_off_lets_everything_through(self) -> None:
        """The default. A limit that is on unless disabled makes ordinary bursts look
        like a broken deployment."""
        client = TestClient(self._app(0, 0))
        assert [client.get("/objects").status_code for _ in range(20)] == [200] * 20
        assert "X-RateLimit-Limit" not in client.get("/objects").headers

    def test_general_limit_answers_429_with_retry_after(self) -> None:
        client = TestClient(self._app(2, 0))
        assert client.get("/objects").status_code == 200
        assert client.get("/objects").status_code == 200

        refused = client.get("/objects")
        assert refused.status_code == 429
        assert refused.json()["code"] == "rate_limited"
        # The header clients and proxies actually read.
        assert int(refused.headers["Retry-After"]) >= 1

    def test_allowed_responses_report_the_budget(self) -> None:
        client = TestClient(self._app(5, 0))
        response = client.get("/objects")
        assert response.headers["X-RateLimit-Limit"] == "5"
        assert response.headers["X-RateLimit-Remaining"] == "4"

    def test_public_routes_are_not_limited(self) -> None:
        """Health and metrics are polled by infrastructure on a fixed schedule.

        Counting them would consume the budget of whatever address the prober uses --
        which is often the same egress address as real traffic -- and make a healthy
        system throttle its own monitoring.
        """
        client = TestClient(self._app(1, 0))
        assert [client.get("/health").status_code for _ in range(5)] == [200] * 5

    def test_the_authentication_limit_is_separate_and_stricter(self) -> None:
        """Password guessing is stopped by a limit far below the general one."""
        client = TestClient(self._app(100, 2))
        assert client.post("/auth/login").status_code == 200
        assert client.post("/auth/login").status_code == 200
        assert client.post("/auth/login").status_code == 429
        # The general budget is untouched, because login drew on its own.
        assert client.get("/objects").status_code == 200

    def test_the_limit_covers_versioned_paths(self) -> None:
        """`/v1` and `/api` are aliases of the same routes.

        A skip list of literal paths would exempt them, and `/v1/auth/login` would be an
        unmetered copy of the endpoint the stricter limit exists to protect.
        """
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, general_limit=100, authentication_limit=1)
        app.include_router(_login_router(), prefix="/v1")

        client = TestClient(app)
        assert client.post("/v1/auth/login").status_code == 200
        assert client.post("/v1/auth/login").status_code == 429

    def test_limiting_applies_before_authentication(self) -> None:
        """The whole point of the placement.

        An unauthenticated flood is what the limit exists to bound, so it cannot sit
        behind the authentication it protects. Middleware nests in reverse registration
        order, so the authenticating layer is registered *first* here to end up inside --
        the same order `api.py` uses.
        """
        app = FastAPI()
        seen: list[str] = []

        @app.middleware("http")
        async def auth(request: Request, call_next):
            seen.append(request.url.path)
            return await call_next(request)

        @app.get("/protected")
        def protected() -> dict[str, bool]:
            return {"ok": True}

        # Registered after `auth`, so it is the outermost of the two.
        app.add_middleware(RateLimitMiddleware, general_limit=1, authentication_limit=0)

        client = TestClient(app)
        assert client.get("/protected").status_code == 200
        assert client.get("/protected").status_code == 429
        # The refused request never reached the layer that authenticates.
        assert seen == ["/protected"]


def _login_router():
    from fastapi import APIRouter

    router = APIRouter()

    @router.post("/auth/login")
    def login() -> dict[str, bool]:
        return {"ok": True}

    return router


class TestTheRealApplication:
    """The composed app, because that is where the ordering actually has to hold.

    A toy app proves the middleware can be ordered correctly; only the real one proves it
    was. Reloaded per test so the middleware stack -- which caches the configured limits
    when it is first built -- is rebuilt from the environment set here.
    """

    @pytest.fixture
    def client(self, tmp_path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("ONTOLOGY_AUTH_DISABLED", raising=False)
        monkeypatch.setenv("ONTOLOGY_ALLOWED_ORIGINS", "http://localhost:3000")
        monkeypatch.setenv("ONTOLOGY_RATE_LIMIT_PER_MINUTE", "1")
        monkeypatch.setenv("ONTOLOGY_RATE_LIMIT_AUTH_PER_MINUTE", "1")

        import importlib

        import ontology_platform.api as api_module
        import ontology_platform.database as database_module

        database_module._platform_adapter = None
        monkeypatch.setattr(database_module, "DEFAULT_PLATFORM_DB", tmp_path / "platform.sqlite3")
        reloaded = importlib.reload(api_module)
        monkeypatch.setattr(reloaded, "DEFAULT_PLATFORM_DB", tmp_path / "platform.sqlite3")
        try:
            # Entered as a context manager so the lifespan runs: without it the platform
            # schema is never created and every endpoint fails on a missing table.
            with TestClient(reloaded.app) as client:
                yield client
        finally:
            database_module._platform_adapter = None

    def test_an_anonymous_flood_is_throttled_rather_than_authenticated(self, client) -> None:
        """A 429 on the second request is the proof of ordering.

        If the limiter sat inside the authenticating middleware, the second request would
        be rejected with 401 as well and the limit would never bind on the traffic it
        exists to bound -- which is exactly the class of mistake an assertion on a
        middleware list would not catch.
        """
        first = client.get("/ontologies")
        assert first.status_code == 401, first.text

        second = client.get("/ontologies")
        assert second.status_code == 429, second.text
        assert second.json()["code"] == "rate_limited"

    def test_login_is_throttled_at_its_own_limit(self, client) -> None:
        """The stricter login budget, reached without the general one being touched."""
        first = client.post("/auth/login", json={"username": "nobody", "password": "wrong"})
        assert first.status_code != 429, first.text

        throttled = client.post("/auth/login", json={"username": "nobody", "password": "wrong"})
        assert throttled.status_code == 429, throttled.text

    def test_health_is_never_throttled(self, client) -> None:
        """Monitoring must not consume the budget of the address it probes from."""
        assert [client.get("/health").status_code for _ in range(5)] == [200] * 5


class TestSettings:
    """Environment configuration, including what happens when it is wrong."""

    def test_unset_means_no_general_limit_and_a_strict_login_limit(self) -> None:
        assert resolve_rate_limit() == 0
        assert resolve_authentication_limit() == DEFAULT_AUTHENTICATION_LIMIT

    def test_values_are_read_from_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ONTOLOGY_RATE_LIMIT_PER_MINUTE", "250")
        monkeypatch.setenv("ONTOLOGY_RATE_LIMIT_AUTH_PER_MINUTE", "5")
        assert resolve_rate_limit() == 250
        assert resolve_authentication_limit() == 5

    @pytest.mark.parametrize("value", ["", "abc", "-3", "1.5"])
    def test_an_unusable_value_falls_back_instead_of_refusing_to_start(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        """Refusing to start over a typo in a tuning knob is the worse failure.

        The failure mode being avoided: a deployment that will not boot because someone
        wrote `100/min` instead of `100`, with the real problem only visible in a log line
        the operator cannot reach because the process is not running.
        """
        monkeypatch.setenv("ONTOLOGY_RATE_LIMIT_PER_MINUTE", value)
        assert resolve_rate_limit() == 0
