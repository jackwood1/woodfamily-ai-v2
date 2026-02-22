"""Tests for COMMUNICATIONS agent."""

import sys
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))


def test_sms_available_unset(monkeypatch):
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TWILIO_PHONE_NUMBER", raising=False)
    from shared.communications_agent import sms_available
    assert sms_available() is False


def test_sms_available_set(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setenv("TWILIO_PHONE_NUMBER", "+15551234567")
    from shared.communications_agent import sms_available
    assert sms_available() is True


def test_send_unknown_channel():
    from shared.communications_agent import send
    result = send("unknown", "test@example.com", "subject", "body")
    assert result["ok"] is False
    assert "Unknown channel" in result["error"]


def test_send_sms_not_configured(monkeypatch):
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    from shared.communications_agent import send_sms
    result = send_sms("+15551234567", "Hello")
    assert result["ok"] is False
    assert "not configured" in result["error"].lower()


def test_run_communications_agent():
    from shared.communications_agent import run_communications_agent
    result = run_communications_agent()
    assert result["ok"] is True
    assert "channels" in result
    assert "email" in result["channels"]
    assert "sms" in result["channels"]
