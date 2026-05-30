"""Authentication helpers for Parabank.

Logging in is a precondition for almost every flow the explorer walks, so it
lives in its own module rather than being duplicated per flow. ``ensure_logged_in``
is idempotent: it logs the fixed test user in, registering them first if they do
not yet exist in the (resettable) Parabank database.
"""

from __future__ import annotations

from playwright.async_api import Page

from . import config
from .config import TestUser


async def _is_logged_in(page: Page) -> bool:
    """A logged-in Parabank session always shows a 'Log Out' link in the left panel."""
    try:
        return await page.locator('a[href*="logout.htm"]').count() > 0
    except Exception:
        return False


async def login(page: Page, user: TestUser) -> bool:
    """Submit the login form. Returns True if a session was established."""
    await page.goto(config.url("index.htm"))
    await page.locator('input[name="username"]').fill(user.username)
    await page.locator('input[name="password"]').fill(user.password)
    await page.locator('form[action*="login.htm"] input[type="submit"]').click()
    await page.wait_for_load_state("networkidle")
    return await _is_logged_in(page)


async def register(page: Page, user: TestUser) -> bool:
    """Fill and submit the registration form. Registration logs the user in.

    Returns True if the user is logged in afterward (covers both a fresh
    registration and the 'username already exists' case where we fall back
    to a plain login).
    """
    await page.goto(config.url("register.htm"))
    fields = {
        "customer.firstName": user.first_name,
        "customer.lastName": user.last_name,
        "customer.address.street": user.street,
        "customer.address.city": user.city,
        "customer.address.state": user.state,
        "customer.address.zipCode": user.zip_code,
        "customer.phoneNumber": user.phone,
        "customer.ssn": user.ssn,
        "customer.username": user.username,
        "customer.password": user.password,
        "repeatedPassword": user.password,
    }
    for field_id, value in fields.items():
        await page.locator(f'[id="{field_id}"]').fill(value)
    await page.locator('input[value="Register"]').click()
    await page.wait_for_load_state("networkidle")

    if await _is_logged_in(page):
        return True
    # Username already exists (or some validation error): try a normal login.
    return await login(page, user)


async def _account_count(page: Page) -> int:
    await page.goto(config.url("overview.htm"))
    await page.wait_for_load_state("networkidle")
    rows = await page.locator("#accountTable tbody tr").count()
    return max(0, rows - 1)  # the final row is the "Total" row


async def ensure_min_accounts(page: Page, minimum: int = 2) -> int:
    """Open accounts until the user has at least ``minimum`` (transfer needs 2).

    A freshly-registered Parabank user has a single account, which makes the
    funds-transfer flow impossible (source and destination would be identical).
    This setup step removes that false-failure cause.
    """
    count = await _account_count(page)
    attempts = 0
    while count < minimum and attempts < minimum + 2:
        attempts += 1
        await page.goto(config.url("openaccount.htm"))
        await page.wait_for_load_state("networkidle")
        try:  # default to a SAVINGS account; funding account defaults to first
            await page.locator("#type").select_option(value="1")
        except Exception:  # noqa: BLE001 - selection is best-effort
            pass
        try:
            await page.locator('input[value="Open New Account"]').click()
            await page.wait_for_load_state("networkidle")
        except Exception:  # noqa: BLE001
            break
        count = await _account_count(page)
    return count


async def ensure_logged_in(page: Page, user: TestUser | None = None) -> None:
    """Idempotently establish a logged-in session for the fixed test user."""
    user = user or config.TEST_USER
    if await login(page, user):
        return
    if await register(page, user):
        return
    raise RuntimeError(
        f"Could not log in or register user '{user.username}' at {config.BASE_URL}. "
        "Is Parabank running? (docker ps | grep parabank)"
    )
