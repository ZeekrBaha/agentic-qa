"""Default set of Parabank flows the explorer walks.

Each goal is phrased the way you'd brief a human tester: what to do and what
"done" looks like. The explorer figures out the clicks; the judge decides
whether the goal was truly met.
"""

from __future__ import annotations

from .schema import FlowSpec

DEFAULT_FLOWS: list[FlowSpec] = [
    FlowSpec(
        flow="transfer",
        goal=(
            "From the Transfer Funds page, transfer $100 from one of your accounts "
            "to another and confirm the page reports the transfer completed."
        ),
        start_page="transfer.htm",
    ),
    FlowSpec(
        flow="billpay",
        goal=(
            "From the Bill Pay page, pay $50 to a payee named 'Acme Utilities' "
            "(make up a valid account number and address), and confirm the payment "
            "was sent successfully."
        ),
        start_page="billpay.htm",
    ),
    FlowSpec(
        flow="open_account",
        goal=(
            "Open a new SAVINGS account from the Open New Account page and confirm "
            "a new account number is created."
        ),
        start_page="openaccount.htm",
    ),
    FlowSpec(
        flow="find_transactions",
        goal=(
            "From Find Transactions, search your account's transactions by amount "
            "and confirm results (or a clear 'no transactions' message) are shown."
        ),
        start_page="findtrans.htm",
    ),
    FlowSpec(
        flow="request_loan",
        goal=(
            "From Request Loan, request a $1000 loan with a $100 down payment and "
            "confirm whether the loan was approved or denied."
        ),
        start_page="requestloan.htm",
    ),
]


def select(names: list[str] | None) -> list[FlowSpec]:
    """Return the named flows (in the given order), or all flows if names is None."""
    if not names:
        return list(DEFAULT_FLOWS)
    by_name = {f.flow: f for f in DEFAULT_FLOWS}
    missing = [n for n in names if n not in by_name]
    if missing:
        raise ValueError(
            f"unknown flow(s): {missing}. available: {sorted(by_name)}"
        )
    return [by_name[n] for n in names]
