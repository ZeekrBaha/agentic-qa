"""Playwright actions wrapped as callable tools for the explorer agent.

Each tool takes a Playwright ``Page``, does one thing, and raises ``ToolError``
on failure. The error is fuel for the explorer's self-healing loop: a failed
action is recorded and re-planned, not fatal.

Page-state design
-----------------
``get_page_state`` returns a compact view built from the accessibility tree
(roles, names, visible text) rather than raw HTML, which would explode token
usage. Because an accessibility name is not something you can click, every
interactive element is also tagged in-page with a stable ``data-aqa-ref``
attribute and returned with a ready-to-use CSS selector
(``[data-aqa-ref="e0"]``). The agent reasons over roles/names and acts over refs.
"""

from __future__ import annotations

import re
from typing import Any

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from . import config

# Strip a trailing cluster of JSON structural / quote / whitespace characters.
# gpt-4o-mini occasionally appends junk like `}}]}` to a structured-output
# string value; bank form values never legitimately end in these, so removing
# the trailing run repairs the model artifact without touching real content.
_TRAILING_JUNK = re.compile(r"[\s}\]{\"'`]+$")


def clean_value(value: str | None) -> str:
    """Repair trailing structured-output junk in a model-provided value."""
    if not value:
        return value or ""
    return _TRAILING_JUNK.sub("", value)


class ToolError(Exception):
    """Raised when a tool action fails. Carries which action failed and why."""

    def __init__(self, action: str, detail: str) -> None:
        self.action = action
        self.detail = detail
        super().__init__(f"{action} failed: {detail}")


# --- Instrumentation (console + network capture) --------------------------

_CONSOLE_ATTR = "_aqa_console_errors"
_NETWORK_ATTR = "_aqa_network_failures"


def instrument(page: Page) -> None:
    """Attach console-error and network-failure listeners.

    Must be called once on a fresh page BEFORE navigation so nothing is missed.
    Captured events accumulate and are read back via the getter tools.
    """
    console_errors: list[str] = []
    network_failures: list[dict[str, Any]] = []
    setattr(page, _CONSOLE_ATTR, console_errors)
    setattr(page, _NETWORK_ATTR, network_failures)

    def on_console(msg: Any) -> None:
        if msg.type == "error":
            console_errors.append(msg.text)

    def on_page_error(exc: Any) -> None:
        console_errors.append(f"uncaught: {exc}")

    def on_request_failed(request: Any) -> None:
        network_failures.append(
            {
                "type": "request_failed",
                "url": request.url,
                "method": request.method,
                "failure": (request.failure or ""),
            }
        )

    def on_response(response: Any) -> None:
        if response.status >= 400:
            network_failures.append(
                {
                    "type": "http_error",
                    "url": response.url,
                    "status": response.status,
                }
            )

    page.on("console", on_console)
    page.on("pageerror", on_page_error)
    page.on("requestfailed", on_request_failed)
    page.on("response", on_response)


# --- Action tools ---------------------------------------------------------

async def navigate(page: Page, target_url: str) -> str:
    """Navigate to a URL. Returns the final (post-redirect) URL."""
    try:
        await page.goto(target_url, timeout=config.RUN.action_timeout_ms)
        await page.wait_for_load_state("domcontentloaded")
        return page.url
    except PlaywrightError as e:
        raise ToolError("navigate", f"could not load {target_url}: {e}") from e


async def click(page: Page, selector: str) -> str:
    """Click the element matched by a CSS selector."""
    if await page.locator(selector).count() == 0:
        raise ToolError("click", f"selector {selector!r}: element not found")
    try:
        await page.locator(selector).first.click(
            timeout=config.RUN.action_timeout_ms
        )
        await page.wait_for_load_state("domcontentloaded")
        return f"clicked {selector}"
    except PlaywrightError as e:
        raise ToolError("click", f"selector {selector!r}: {e}") from e


async def fill(page: Page, selector: str, value: str) -> str:
    """Type ``value`` into the field matched by a CSS selector."""
    if await page.locator(selector).count() == 0:
        raise ToolError("fill", f"selector {selector!r}: element not found")
    try:
        await page.locator(selector).first.fill(
            value, timeout=config.RUN.action_timeout_ms
        )
        return f"filled {selector} with {value!r}"
    except PlaywrightError as e:
        raise ToolError("fill", f"selector {selector!r}: {e}") from e


def _match_option(requested: str, options: list[dict[str, str]]) -> str | None:
    """Find the option value best matching a (possibly noisy) requested string."""
    req = clean_value(requested).strip()
    reqn = req.lower()
    # 1) exact value or label (case-insensitive)
    for o in options:
        if reqn == o["value"].lower() or reqn == o["label"].strip().lower():
            return o["value"]
    # 2) the option's value appears in the request (e.g. "1001 — Checking" -> 1001)
    for o in options:
        if o["value"] and o["value"].lower() in reqn:
            return o["value"]
    # 3) the request is contained in an option's label (e.g. "Savings")
    for o in options:
        if reqn and reqn in o["label"].strip().lower():
            return o["value"]
    return None


async def select_option(page: Page, selector: str, option: str) -> str:
    """Choose an option in a <select>, tolerating noisy values and failing fast.

    Reads the element's real options up front so a non-matching request raises
    immediately instead of waiting out Playwright's full action timeout.
    """
    if await page.locator(selector).count() == 0:
        raise ToolError("select", f"selector {selector!r}: element not found")
    locator = page.locator(selector).first
    try:
        options = await locator.evaluate(
            "el => Array.from(el.options || [])"
            ".map(o => ({value: o.value, label: (o.textContent || '').trim()}))"
        )
    except PlaywrightError as e:
        raise ToolError("select", f"selector {selector!r} is not a <select>: {e}") from e
    if not options:
        raise ToolError("select", f"selector {selector!r}: no options available")

    target = _match_option(option, options)
    if target is None:
        available = [o["value"] for o in options]
        raise ToolError(
            "select",
            f"selector {selector!r}: no option matches {option!r}; available={available}",
        )
    await locator.select_option(value=target, timeout=config.RUN.action_timeout_ms)
    return f"selected {target!r} in {selector}"


async def screenshot(page: Page, path: str | None = None) -> str:
    """Save a full-page screenshot. Returns the path written."""
    if path is None:
        path = str(config.runs_dir() / "screenshot.png")
    try:
        await page.screenshot(path=path, full_page=True)
        return path
    except PlaywrightError as e:
        raise ToolError("screenshot", str(e)) from e


# JavaScript that tags interactive elements and extracts a compact page view.
_PAGE_STATE_JS = r"""
() => {
  const isVisible = (el) => {
    const r = el.getBoundingClientRect();
    const s = window.getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const accName = (el) => {
    const aria = el.getAttribute('aria-label');
    if (aria) return aria.trim();
    if (el.tagName === 'SELECT') {
      // Use the field's label, never the joined option text.
      if (el.id) {
        const lab = document.querySelector(`label[for="${el.id}"]`);
        if (lab && lab.innerText.trim()) return lab.innerText.trim();
      }
      return (el.getAttribute('name') || '').trim();
    }
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
      if (el.id) {
        const lab = document.querySelector(`label[for="${el.id}"]`);
        if (lab && lab.innerText.trim()) return lab.innerText.trim();
      }
      if (el.placeholder) return el.placeholder.trim();
      if (el.name) return el.name.trim();
    }
    if (el.value && (el.tagName === 'INPUT')) return el.value.trim();
    const txt = (el.innerText || el.textContent || '').trim();
    if (txt) return txt.slice(0, 80);
    return (el.getAttribute('alt') || el.getAttribute('title') || '').trim();
  };
  const roleOf = (el) => {
    const r = el.getAttribute('role');
    if (r) return r;
    const tag = el.tagName.toLowerCase();
    if (tag === 'a') return 'link';
    if (tag === 'button') return 'button';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'input') {
      const t = (el.getAttribute('type') || 'text').toLowerCase();
      if (t === 'submit' || t === 'button') return 'button';
      if (t === 'checkbox') return 'checkbox';
      if (t === 'radio') return 'radio';
      return 'textbox';
    }
    return tag;
  };
  const sel = 'a, button, input, select, textarea, [role=button], [role=link], [onclick]';
  const els = Array.from(document.querySelectorAll(sel)).filter(isVisible);
  const interactive = [];
  let i = 0;
  for (const el of els) {
    if (i >= 80) break;
    const ref = 'e' + i;
    el.setAttribute('data-aqa-ref', ref);
    const name = (accName(el) || '').replace(/\s+/g, ' ').trim();
    const entry = { selector: `[data-aqa-ref="${ref}"]`, role: roleOf(el), name };
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') entry.value = el.value || '';
    if (el.tagName === 'SELECT') {
      entry.options = Array.from(el.options).slice(0, 20).map(o => ({
        value: o.value, label: (o.textContent || '').replace(/\s+/g, ' ').trim()
      }));
    }
    interactive.push(entry);
    i++;
  }
  const headings = Array.from(document.querySelectorAll('h1, h2, h3'))
    .filter(isVisible).map(h => h.innerText.trim()).filter(Boolean).slice(0, 20);
  const bodyText = (document.body ? document.body.innerText : '').replace(/\s+/g, ' ').trim().slice(0, 1500);
  return { url: location.href, title: document.title, headings, text: bodyText, interactive };
}
"""


async def get_page_state(page: Page) -> dict[str, Any]:
    """Return a compact, token-friendly page view (a11y roles/names + refs)."""
    try:
        return await page.evaluate(_PAGE_STATE_JS)
    except PlaywrightError as e:
        raise ToolError("get_page_state", str(e)) from e


def reset_capture(page: Page) -> None:
    """Clear captured console/network events so the next flow starts clean."""
    for attr in (_CONSOLE_ATTR, _NETWORK_ATTR):
        captured = getattr(page, attr, None)
        if captured is not None:
            captured.clear()


async def get_console_errors(page: Page) -> list[str]:
    """Console errors + uncaught exceptions captured since ``instrument``."""
    return list(getattr(page, _CONSOLE_ATTR, []))


async def get_network_failures(page: Page) -> list[dict[str, Any]]:
    """Failed requests and >=400 HTTP responses captured since ``instrument``."""
    return list(getattr(page, _NETWORK_ATTR, []))
