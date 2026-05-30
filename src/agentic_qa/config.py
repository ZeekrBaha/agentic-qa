"""Central configuration for the Agentic QA system.

Importing this module is side-effect free and does NOT require an API key.
The OpenAI key is only read lazily, when an LLM call is actually made
(see ``get_openai_key``), so Phases 0–1 run with no key present.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --- Target app -----------------------------------------------------------

# Local Docker Parabank is the default target (stable + repeatable).
# Override with AGENTIC_QA_BASE_URL to point at the public demo host.
BASE_URL = os.environ.get(
    "AGENTIC_QA_BASE_URL", "http://localhost:8080/parabank"
)


def url(path: str) -> str:
    """Join a Parabank page onto the base URL (e.g. ``url('overview.htm')``)."""
    return f"{BASE_URL.rstrip('/')}/{path.lstrip('/')}"


# --- Test user ------------------------------------------------------------

# A fixed user the system registers once (then reuses) so logins are
# deterministic regardless of the Parabank DB's reset state.
@dataclass(frozen=True)
class TestUser:
    first_name: str = "Ada"
    last_name: str = "Lovelace"
    street: str = "1 Analytical Engine Way"
    city: str = "London"
    state: str = "CA"
    zip_code: str = "94000"
    phone: str = "5551234567"
    ssn: str = "123-45-6789"
    username: str = "qa_explorer"
    password: str = "Sup3rSecret!"


TEST_USER = TestUser()


# --- Models ---------------------------------------------------------------

# Model split. The judge always uses a strong model. The explorer default is
# also gpt-4o: live validation showed gpt-4o-mini reliably FLAGS bugs but often
# fails to COMPLETE multi-field flows (e.g. funds transfer), where gpt-4o
# completes reliably. Set AGENTIC_QA_EXPLORER_MODEL=gpt-4o-mini to trade some
# completion reliability for ~2-3x lower explorer token cost.
EXPLORER_MODEL = os.environ.get("AGENTIC_QA_EXPLORER_MODEL", "gpt-4o")
JUDGE_MODEL = os.environ.get("AGENTIC_QA_JUDGE_MODEL", "gpt-4o")
EMBEDDING_MODEL = os.environ.get("AGENTIC_QA_EMBEDDING_MODEL", "text-embedding-3-small")


def get_openai_key() -> str:
    """Read the OpenAI key lazily. Fail fast with a clear message if absent."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Export it before running LLM phases:\n"
            "    export OPENAI_API_KEY=sk-..."
        )
    return key


# --- Run settings ---------------------------------------------------------

@dataclass
class RunSettings:
    headless: bool = True
    # Max observe->decide->act steps the explorer takes per flow.
    max_steps: int = 25
    # Consecutive unrecoverable tool failures that end a flow (self-healing budget).
    max_consecutive_failures: int = 3
    # Per-action navigation/visibility timeout (ms).
    action_timeout_ms: int = 8000


RUN = RunSettings()


# --- Paths ----------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = PROJECT_ROOT / "runs"


def runs_dir() -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    return RUNS_DIR
