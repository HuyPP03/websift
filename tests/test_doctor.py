"""doctor / providers CLI diagnostics."""

from __future__ import annotations

import json

from websift.cli import main
from websift.doctor import doctor_report, providers_report


def test_providers_report_text():
    code, text = providers_report()
    assert code == 0
    assert "ddgs" in text
    assert "serper" in text


def test_providers_report_json():
    code, text = providers_report(as_json=True)
    assert code == 0
    data = json.loads(text)
    assert data["schema_version"] == 2
    names = {p["name"] for p in data["providers"]}
    assert "ddgs" in names
    assert "brave" in names


def test_doctor_report_ok():
    code, text = doctor_report()
    assert code == 0
    assert "websift doctor" in text
    assert "[OK]" in text


def test_doctor_report_json():
    code, text = doctor_report(as_json=True)
    assert code == 0
    data = json.loads(text)
    assert data["schema_version"] == 2
    assert data["ok"] is True
    names = {c["name"] for c in data["checks"]}
    assert "version" in names
    assert "settings" in names
    assert "cache" in names
    assert "domain_policy" in names


def test_doctor_missing_credentials(monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "serper")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    code, text = doctor_report()
    assert code == 1
    assert "FAIL" in text or "MISSING" in text


def test_doctor_missing_searxng_url(monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "searxng")
    monkeypatch.delenv("SEARXNG_BASE_URL", raising=False)
    code, text = doctor_report(as_json=True)
    data = json.loads(text)
    # settings may fail validate OR credentials check
    assert data["ok"] is False or any(
        (not c["ok"]) and c["name"] in {"settings", "credentials"} for c in data["checks"]
    )


def test_cli_providers(capsys):
    try:
        main(["providers"])
    except SystemExit as e:
        assert e.code == 0
    out = capsys.readouterr().out
    assert "ddgs" in out


def test_cli_providers_json(capsys):
    try:
        main(["providers", "--json"])
    except SystemExit as e:
        assert e.code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["schema_version"] == 2


def test_cli_doctor(capsys):
    try:
        main(["doctor"])
    except SystemExit as e:
        assert e.code == 0
    out = capsys.readouterr().out
    assert "doctor" in out.lower()


def test_cli_doctor_json(capsys):
    try:
        main(["doctor", "--json"])
    except SystemExit as e:
        assert e.code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "checks" in data
