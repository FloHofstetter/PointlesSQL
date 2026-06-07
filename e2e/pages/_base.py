"""Base page object for the e2e browser journeys.

Every surface-specific page object subclasses :class:`BasePage`.  The base
wraps a Playwright ``Page`` and centralises the wait/assert idioms so that
the per-surface objects stay declarative (selectors + intent) instead of
re-deriving wait logic.

Design contract:

* **Auto-wait only.**  Every helper builds on Playwright's built-in
  auto-waiting (``locator.wait_for``, ``expect``, ``get_by_*().wait_for``).
  There is **no** ``time.sleep`` and **no** ``wait_until="networkidle"`` —
  the home and notebook surfaces hold WebSocket connections (notifications,
  presence, co-edit) open for the lifetime of the page, so ``networkidle``
  never fires and would hang the test.  ``domcontentloaded`` plus an
  explicit element/URL wait is the portable substitute.
* **Selector priority** (most stable first), so journeys survive cosmetic
  churn and never depend on the user's in-flight CSS:

  1. an existing ``data-testid`` attribute,
  2. a playbook-quoted CSS selector (e.g. ``i.bi-shield-check``),
  3. an ARIA role or visible text,
  4. a form field by ``#id`` / ``[name=...]``,
  5. a URL or ``page.evaluate`` (JS) probe of last resort.

* **Browser-neutral.**  CI runs bundled Chromium; the manual MCP replays
  run Firefox.  Helpers avoid engine-specific selector tricks.

The base is intentionally framework-light: it is a thin, typed convenience
layer, not a DSL.  Subclasses add ``goto_*`` navigation plus assertions
phrased in the vocabulary of their surface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only, playwright optional at import
    from playwright.sync_api import Locator, Page, Response

# Default per-action wait.  Generous enough for a cold-cache first paint on a
# CI runner, short enough that a genuinely-broken selector fails fast rather
# than stalling the whole suite.
DEFAULT_TIMEOUT_MS = 10_000


class BasePage:
    """A Playwright ``Page`` wrapper with the project's wait/assert idioms.

    Args:
        page: The live Playwright ``Page`` (from a fresh ``BrowserContext``).
        base_url: The live server base URL (``http://127.0.0.1:<port>``);
            relative paths passed to :meth:`goto` are resolved against it.
    """

    def __init__(self, page: Page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url.rstrip("/")

    # -- navigation ---------------------------------------------------------

    def url(self, path: str) -> str:
        """Resolve *path* against the base URL (absolute paths pass through)."""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def goto(self, path: str = "/", *, wait_until: str = "domcontentloaded") -> Response | None:
        """Navigate to *path* and return the navigation response.

        Uses ``domcontentloaded`` by default — never ``networkidle`` — so the
        always-open notification/presence WebSockets do not stall the load.

        Args:
            path: Absolute URL or a path relative to the base URL.
            wait_until: Playwright load state; keep it off ``networkidle``.

        Returns:
            The main navigation :class:`Response`, or ``None`` if Playwright
            reports no response (e.g. an in-page anchor navigation).
        """
        return self.page.goto(self.url(path), wait_until=wait_until)  # type: ignore[arg-type]

    # -- locators -----------------------------------------------------------

    def testid(self, value: str) -> Locator:
        """Locate by ``data-testid`` — the most stable selector tier."""
        return self.page.get_by_test_id(value)

    def loc(self, selector: str) -> Locator:
        """Locate by a raw CSS/text selector (playbook-quoted)."""
        return self.page.locator(selector)

    def by_text(self, text: str, *, exact: bool = False) -> Locator:
        """Locate the first element containing *text*."""
        return self.page.get_by_text(text, exact=exact)

    def by_role(self, role: str, *, name: str | None = None) -> Locator:
        """Locate by ARIA role, optionally constrained by accessible name."""
        if name is None:
            return self.page.get_by_role(role)  # type: ignore[arg-type]
        return self.page.get_by_role(role, name=name)  # type: ignore[arg-type]

    # -- waits / assertions -------------------------------------------------

    def wait_visible(self, selector: str, *, timeout: int = DEFAULT_TIMEOUT_MS) -> Locator:
        """Wait until the first match of *selector* is visible; return it."""
        locator = self.loc(selector)
        locator.first.wait_for(state="visible", timeout=timeout)
        return locator

    def wait_testid(self, value: str, *, timeout: int = DEFAULT_TIMEOUT_MS) -> Locator:
        """Wait until the ``data-testid`` element is visible; return it."""
        locator = self.testid(value)
        locator.first.wait_for(state="visible", timeout=timeout)
        return locator

    def wait_text(self, text: str, *, timeout: int = DEFAULT_TIMEOUT_MS) -> Locator:
        """Wait until an element containing *text* is visible; return it."""
        locator = self.by_text(text)
        locator.first.wait_for(state="visible", timeout=timeout)
        return locator

    def expect_url_contains(self, fragment: str) -> None:
        """Assert the current URL contains *fragment* (after any redirect)."""
        assert fragment in self.page.url, (
            f"expected URL to contain {fragment!r}, got {self.page.url!r}"
        )

    def expect_url_excludes(self, fragment: str) -> None:
        """Assert the current URL does **not** contain *fragment*."""
        assert fragment not in self.page.url, (
            f"expected URL to exclude {fragment!r}, got {self.page.url!r}"
        )

    # -- interaction --------------------------------------------------------

    def click(self, selector: str, *, timeout: int = DEFAULT_TIMEOUT_MS) -> None:
        """Click the first match of *selector* (auto-waits for actionability)."""
        self.loc(selector).first.click(timeout=timeout)

    def fill(self, selector: str, value: str, *, timeout: int = DEFAULT_TIMEOUT_MS) -> None:
        """Fill a single input/textarea identified by *selector*."""
        self.loc(selector).first.fill(value, timeout=timeout)

    def fill_form(self, fields: dict[str, str]) -> None:
        """Fill several fields keyed by CSS selector → value, in order."""
        for selector, value in fields.items():
            self.fill(selector, value)

    def eval_js(self, expression: str, arg: Any = None) -> Any:
        """Evaluate *expression* in the page and return the JSON result.

        The last-resort probe tier: use only when a surface exposes state
        that has no stable DOM affordance (e.g. an Alpine store flag).
        """
        return self.page.evaluate(expression, arg)

    # -- diagnostics --------------------------------------------------------

    def screenshot(self, path: str, *, full_page: bool = True) -> None:
        """Write a PNG screenshot of the current page to *path*."""
        self.page.screenshot(path=path, full_page=full_page)
