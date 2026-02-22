"""Tests for CONTACT agent."""

import sys
import tempfile
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))


def test_normalize_email():
    from shared.contact_agent import _normalize_email
    assert _normalize_email("  Test@Example.COM  ") == "test@example.com"
    assert _normalize_email("") == ""
    assert _normalize_email("a@b.co") == "a@b.co"


def test_parse_email_from_header():
    from shared.contact_agent import _parse_email_from_header
    assert _parse_email_from_header("John Doe <john@example.com>") == "john@example.com"
    assert _parse_email_from_header("jane@test.org") == "jane@test.org"
    assert _parse_email_from_header("") is None
    assert _parse_email_from_header("  ") is None


def test_extract_person_fields():
    from shared.contact_agent import _extract_person_fields
    p = {
        "names": [{"givenName": "John", "familyName": "Doe"}],
        "emailAddresses": [{"value": "john@example.com"}],
        "phoneNumbers": [{"value": "+1234567890"}],
    }
    name, email, phone = _extract_person_fields(p)
    assert name == "John Doe"
    assert email == "john@example.com"
    assert phone == "+1234567890"


def test_extract_person_fields_minimal():
    from shared.contact_agent import _extract_person_fields
    p = {"emailAddresses": [{"value": "a@b.co"}]}
    name, email, phone = _extract_person_fields(p)
    assert name == ""
    assert email == "a@b.co"
    assert phone == ""


def test_import_from_vcard(dashboard_db, monkeypatch):
    monkeypatch.setenv("DASHBOARD_DB_PATH", str(dashboard_db))
    from shared.contact_agent import import_from_vcard
    vcf = """BEGIN:VCARD
VERSION:3.0
FN:Test User
N:User;Test;;;
EMAIL:test@example.com
TEL:+1234567890
END:VCARD
"""
    added, skipped = import_from_vcard(vcf, dashboard_db_path=dashboard_db)
    assert added == 1
    assert skipped == 0


def test_import_from_vcard_skip_existing(dashboard_db, monkeypatch):
    monkeypatch.setenv("DASHBOARD_DB_PATH", str(dashboard_db))
    from shared.contact_agent import import_from_vcard
    vcf = """BEGIN:VCARD
VERSION:3.0
FN:Test User
EMAIL:test@example.com
END:VCARD
"""
    import_from_vcard(vcf, dashboard_db_path=dashboard_db)
    added, skipped = import_from_vcard(vcf, dashboard_db_path=dashboard_db)
    assert added == 0
    assert skipped == 1


@pytest.fixture
def dashboard_db(tmp_path):
    """Create temp dashboard DB with contacts, circles, wishlist."""
    db = tmp_path / "dashboard.db"
    import sqlite3
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE circles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE circle_members (
            circle_id INTEGER NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            PRIMARY KEY (circle_id, entity_type, entity_id)
        );
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            event_type TEXT NOT NULL DEFAULT 'event',
            recurrence TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.close()
    return db




