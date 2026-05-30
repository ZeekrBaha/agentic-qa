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
