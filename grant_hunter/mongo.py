"""
MongoDB client helper for 0xGrantHunter.
Uses MONGODB_ATLAS_URI from environment (local .env) or Google Secret Manager (Cloud Run mount).
Automatically ensures useful indexes on the grants collection.
"""

from typing import Optional
from pymongo import MongoClient, ASCENDING, DESCENDING, TEXT
from pymongo.database import Database
from pymongo.collection import Collection

from .config import get_mongodb_uri, load_secrets

# Lazy singletons
_client: Optional[MongoClient] = None
_db: Optional[Database] = None
_indexes_ensured = False


def get_client() -> MongoClient:
    global _client
    if _client is None:
        load_secrets()  # ensure env is populated from secret or .env
        uri = get_mongodb_uri()
        _client = MongoClient(uri, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000)
        _client.admin.command("ping")  # fail fast on bad auth/network
    return _client


def get_db() -> Database:
    global _db
    if _db is None:
        client = get_client()
        # DB name comes from the URI path (/granthunter)
        _db = client.get_default_database()
        ensure_indexes()
    return _db


def get_collection(name: str) -> Collection:
    return get_db()[name]


def grants_collection() -> Collection:
    return get_collection("grants")


def profiles_collection() -> Collection:
    return get_collection("profiles")


def ensure_indexes():
    """Create useful indexes for the grant hunter use case. Idempotent."""
    global _indexes_ensured
    if _indexes_ensured:
        return

    grants = grants_collection()

    # Deadline queries (upcoming grants)
    grants.create_index([("deadline", ASCENDING)], background=True)

    # High-match first
    grants.create_index([("match_score", DESCENDING)], background=True)

    # Filter by funder + score
    grants.create_index([("funder", ASCENDING), ("match_score", DESCENDING)], background=True)

    # Location / eligibility (simple field index; can be compound later)
    grants.create_index([("location", ASCENDING)], background=True)

    # Text search on title + eligibility summary (great for keyword matching)
    grants.create_index(
        [("title", TEXT), ("eligibility_summary", TEXT)],
        name="grants_text_search",
        background=True
    )

    # Prevent duplicates on (title, funder)
    grants.create_index(
        [("title", ASCENDING), ("funder", ASCENDING)],
        unique=True,
        background=True
    )

    _indexes_ensured = True
