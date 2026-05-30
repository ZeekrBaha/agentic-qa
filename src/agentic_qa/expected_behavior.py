"""Documented expected behavior for Parabank flows.

These are the acceptance-criteria notes the RAG-grounded judge retrieves from so
its verdict cites documented rules ("a transfer must reduce the source balance")
instead of guessing. In a real project these would come from a spec/wiki; here
they are kept inline and small.
"""

from __future__ import annotations

from pydantic import BaseModel


class SpecDoc(BaseModel):
    flow: str
    text: str


EXPECTED_BEHAVIOR: list[SpecDoc] = [
    SpecDoc(flow="transfer", text=(
        "Funds Transfer: a transfer MUST reduce the source account balance by the "
        "transferred amount and increase the destination account balance by the "
        "same amount. On success the page MUST display 'Transfer Complete!' along "
        "with the amount and both account numbers.")),
    SpecDoc(flow="billpay", text=(
        "Bill Pay: a successful payment MUST display 'Bill Payment Complete' with "
        "the payee name and amount, and MUST reduce the paying account's balance by "
        "the amount. It MUST NOT produce a server error page.")),
    SpecDoc(flow="open_account", text=(
        "Open New Account: opening an account MUST create and display a new, unique "
        "account number, and that account MUST then appear in Accounts Overview "
        "with an initial balance.")),
    SpecDoc(flow="find_transactions", text=(
        "Find Transactions: searching MUST return the matching transactions or a "
        "clear empty-result message. It MUST NOT display a stack trace or error "
        "page for a valid query.")),
    SpecDoc(flow="request_loan", text=(
        "Request Loan: the page MUST show a clear approved or denied decision. If "
        "approved, a new loan account MUST be created and shown.")),
    SpecDoc(flow="general", text=(
        "Global rules: no page may display 'An internal error has occurred', a Java "
        "stack trace, or an HTTP 500. Account balances are currency values and must "
        "never become negative due to a defect.")),
]
