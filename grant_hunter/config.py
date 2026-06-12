"""
Central config & secret loading for 0xGrantHunter.

- Local: uses .env (python-dotenv)
- Cloud Run / GCP: loads from mounted Secret Manager secret (JSON with GEMINI_API_KEY + MONGODB_ATLAS_URI)
- Sets os.environ so downstream (ADK, mongo, etc.) pick up the values.
- Call load_secrets() as early as possible (before importing things that read env).
"""

import json
import os
from pathlib import Path

SECRET_FILE = Path("/secrets/granthunter-secrets")  # mounted by Cloud Run Terraform
ENV_KEYS = ["GOOGLE_GENAI_API_KEY", "MONGODB_ATLAS_URI"]


def load_secrets() -> dict:
    """
    Load secrets into os.environ.
    Returns the dict of loaded values (for logging redacted).
    Safe to call multiple times.

    Supports multiple ways the secret can be provided in Cloud Run / Terraform modules:
    - Mounted file at /secrets/granthunter-secrets (our previous explicit Terraform)
    - Env var "SECRET" containing the full JSON (common with env_secret_vars in modules)
    - Individual env vars GOOGLE_GENAI_API_KEY / MONGODB_ATLAS_URI (or GEMINI_API_KEY alias)
    """
    loaded = {}

    # 1. Try mounted secret file (explicit volume mount style)
    if SECRET_FILE.exists():
        try:
            raw = SECRET_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            _apply_secret_dict(data, loaded)
        except Exception as e:
            print(f"Warning: failed to load mounted secret {SECRET_FILE}: {e}")

    # 2. Try env var "SECRET" containing the JSON (module env_secret_vars style)
    secret_json = os.getenv("SECRET")
    if secret_json:
        try:
            data = json.loads(secret_json)
            _apply_secret_dict(data, loaded)
        except Exception as e:
            print(f"Warning: failed to parse SECRET env var as JSON: {e}")

    # 3. Fallback to .env (local development)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # 4. Pick up any direct env vars (set by Terraform env_vars or .env)
    for key in ENV_KEYS:
        val = os.getenv(key)
        if val and key not in loaded:
            os.environ[key] = val
            loaded[key] = val

    # Support GEMINI_API_KEY alias if GOOGLE_GENAI_API_KEY not set
    if "GEMINI_API_KEY" in os.environ and not os.getenv("GOOGLE_GENAI_API_KEY"):
        os.environ["GOOGLE_GENAI_API_KEY"] = os.environ["GEMINI_API_KEY"]
        loaded["GOOGLE_GENAI_API_KEY"] = os.environ["GEMINI_API_KEY"]

    return {k: ("***" if v else None) for k, v in loaded.items()}


def _apply_secret_dict(data: dict, loaded: dict):
    """Helper to apply keys from a secret JSON dict into os.environ and loaded."""
    for key in ENV_KEYS:
        if key in data and data[key]:
            os.environ[key] = data[key]
            loaded[key] = data[key]
    # Support the Packet's GEMINI_API_KEY alias
    if "GEMINI_API_KEY" in data and not os.getenv("GOOGLE_GENAI_API_KEY"):
        os.environ["GOOGLE_GENAI_API_KEY"] = data["GEMINI_API_KEY"]
        loaded["GOOGLE_GENAI_API_KEY"] = data["GEMINI_API_KEY"]


def get_mongodb_uri() -> str:
    load_secrets()
    uri = os.getenv("MONGODB_ATLAS_URI")
    if not uri:
        raise RuntimeError("MONGODB_ATLAS_URI not found in env or secret")
    return uri


def get_genai_key() -> str:
    load_secrets()
    key = os.getenv("GOOGLE_GENAI_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_GENAI_API_KEY not found in env or secret")
    return key
