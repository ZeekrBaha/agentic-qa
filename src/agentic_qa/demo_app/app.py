"""A tiny, fully-controlled demo bank with ONE deliberately planted bug.

This is a prop for the Phase 8 showcase, not a product. It exists so the planted
bug is unambiguous: the agent's catch can be verified against a defect we
control exactly.

THE PLANTED BUG (see ``do_transfer``): a funds transfer credits the destination
account but never debits the source account. The confirmation page therefore
shows the source's "new balance" equal to its "previous balance" after a
transfer — a data error that violates the rule "a transfer must reduce the
source balance."

Run standalone:  python -m agentic_qa.demo_app.app    (serves on :5005)
"""

from __future__ import annotations

from copy import deepcopy

from flask import Flask, redirect, render_template_string, request, session, url_for

app = Flask(__name__)
app.secret_key = "demo-not-secret"

DEMO_USER = ("demo", "demo")

INITIAL_ACCOUNTS = {
    "1001": {"name": "Checking", "balance": 1000.00},
    "1002": {"name": "Savings", "balance": 500.00},
}

# Per-process state. Reset on each login so the demo is repeatable.
accounts: dict[str, dict] = deepcopy(INITIAL_ACCOUNTS)
history: list[dict] = []

_PAGE = """
<!doctype html><html><head><title>DemoBank | {{ title }}</title>
<style>body{font-family:system-ui,sans-serif;max-width:640px;margin:2rem auto}
label{display:block;margin:.5rem 0 .2rem}input,select{padding:.3rem;width:220px}
.bal{font-weight:600}nav a{margin-right:1rem}</style></head>
<body><h1>DemoBank — {{ title }}</h1>{{ body|safe }}</body></html>
"""


def render(title: str, body: str):
    return render_template_string(_PAGE, title=title, body=body)


def require_login():
    return session.get("user") == DEMO_USER[0]


@app.route("/", methods=["GET"])
def index():
    if require_login():
        return redirect(url_for("dashboard"))
    return render("Login", """
      <form method="post" action="/login">
        <label for="username">Username</label>
        <input id="username" name="username" type="text">
        <label for="password">Password</label>
        <input id="password" name="password" type="password">
        <p><button id="login" type="submit">Log In</button></p>
        <p>Use demo / demo.</p>
      </form>""")


@app.route("/login", methods=["POST"])
def login():
    global accounts, history
    if (request.form.get("username"), request.form.get("password")) == DEMO_USER:
        session["user"] = DEMO_USER[0]
        accounts = deepcopy(INITIAL_ACCOUNTS)  # repeatable demo state
        history = []
        return redirect(url_for("dashboard"))
    return render("Login", "<p id='error'>Invalid credentials.</p>"
                  "<p><a href='/'>Back</a></p>")


@app.route("/dashboard")
def dashboard():
    if not require_login():
        return redirect(url_for("index"))
    rows = "".join(
        f"<tr><td>{num}</td><td>{a['name']}</td>"
        f"<td class='bal'>${a['balance']:.2f}</td></tr>"
        for num, a in accounts.items()
    )
    return render("Accounts", f"""
      <nav><a href="/transfer">Transfer</a><a href="/history">History</a>
      <a href="/logout">Log Out</a></nav>
      <table border="1" cellpadding="6"><tr><th>Account</th><th>Name</th>
      <th>Balance</th></tr>{rows}</table>""")


@app.route("/transfer", methods=["GET", "POST"])
def transfer():
    if not require_login():
        return redirect(url_for("index"))
    if request.method == "GET":
        opts = "".join(
            f"<option value='{num}'>{num} — {a['name']}</option>"
            for num, a in accounts.items()
        )
        return render("Transfer Funds", f"""
          <nav><a href="/dashboard">Dashboard</a></nav>
          <form method="post" action="/transfer">
            <label for="from_acct">From account</label>
            <select id="from_acct" name="from_acct">{opts}</select>
            <label for="to_acct">To account</label>
            <select id="to_acct" name="to_acct">{opts}</select>
            <label for="amount">Amount</label>
            <input id="amount" name="amount" type="text">
            <p><button id="submit" type="submit">Transfer</button></p>
          </form>""")
    return do_transfer()


def do_transfer():
    src = request.form.get("from_acct", "")
    dst = request.form.get("to_acct", "")
    try:
        amount = round(float(request.form.get("amount", "0")), 2)
    except ValueError:
        return render("Transfer Funds", "<p id='error'>Invalid amount.</p>")
    if src not in accounts or dst not in accounts:
        return render("Transfer Funds", "<p id='error'>Unknown account.</p>")

    prev_balance = accounts[src]["balance"]
    accounts[dst]["balance"] += amount
    # --- PLANTED BUG -------------------------------------------------------
    # The source account should be debited here:
    #     accounts[src]["balance"] -= amount
    # That line is intentionally missing, so the source balance never changes.
    # -----------------------------------------------------------------------
    new_balance = accounts[src]["balance"]
    history.append({"from": src, "to": dst, "amount": amount})

    return render("Transfer Complete", f"""
      <nav><a href="/dashboard">Dashboard</a><a href="/history">History</a></nav>
      <p id="result">Transfer Complete: ${amount:.2f} from {accounts[src]['name']}
       ({src}) to {accounts[dst]['name']} ({dst}).</p>
      <p>{accounts[src]['name']} previous balance:
       <span class="bal">${prev_balance:.2f}</span></p>
      <p>{accounts[src]['name']} new balance:
       <span class="bal" id="new_balance">${new_balance:.2f}</span></p>""")


@app.route("/history")
def history_page():
    if not require_login():
        return redirect(url_for("index"))
    if not history:
        body = "<p id='empty'>No transactions yet.</p>"
    else:
        body = "<ul>" + "".join(
            f"<li>${h['amount']:.2f} from {h['from']} to {h['to']}</li>"
            for h in history
        ) + "</ul>"
    return render("Transaction History",
                  f"<nav><a href='/dashboard'>Dashboard</a></nav>{body}")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(port=5005, debug=False)
