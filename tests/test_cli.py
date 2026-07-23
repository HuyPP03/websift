"""CLI entry: help, version, serve/search/fetch wiring."""

from __future__ import annotations

import pytest

from websift import __version__
from websift.cli import main


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as ei:
        main(["--version"])
    assert ei.value.code == 0
    out = capsys.readouterr().out
    assert __version__ in out
    assert "websift" in out


def test_cli_help(capsys):
    with pytest.raises(SystemExit) as ei:
        main(["--help"])
    assert ei.value.code == 0
    out = capsys.readouterr().out
    assert "serve" in out
    assert "search" in out
    assert "fetch" in out


def test_cli_serve_help(capsys):
    with pytest.raises(SystemExit) as ei:
        main(["serve", "--help"])
    assert ei.value.code == 0
    out = capsys.readouterr().out
    assert "--host" in out
    assert "--port" in out
    assert "--transport" in out


def test_cli_search_delegates(monkeypatch, capsys):
    from websift import cli as cli_mod

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def search(self, query: str) -> str:
            return f"RESULTS:{query}"

    monkeypatch.setattr(cli_mod, "WebSearchClient", FakeClient)
    with pytest.raises(SystemExit) as ei:
        main(["search", "hello world"])
    assert ei.value.code == 0
    assert "RESULTS:hello world" in capsys.readouterr().out


def test_cli_fetch_delegates(monkeypatch, capsys):
    from websift import cli as cli_mod

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def fetch(self, url: str) -> str:
            return f"PAGE:{url}"

    monkeypatch.setattr(cli_mod, "WebSearchClient", FakeClient)
    with pytest.raises(SystemExit) as ei:
        main(["fetch", "https://example.com/", "--max-chars", "1000", "--timeout", "12"])
    assert ei.value.code == 0
    assert "PAGE:https://example.com/" in capsys.readouterr().out


def test_cli_serve_wires_create_server(monkeypatch):
    from websift import cli as cli_mod

    calls: dict = {}

    class FakeApp:
        def run(self):
            calls["ran"] = True

    def fake_create(settings):
        calls["host"] = settings.server.host
        calls["port"] = settings.server.port
        calls["transport"] = settings.server.transport
        calls["auth_mode"] = settings.auth.mode
        calls["token"] = settings.auth.bearer_token
        calls["provider"] = settings.provider.name
        calls["max_results"] = settings.provider.max_results
        calls["log_level"] = settings.logging.level
        return FakeApp()

    monkeypatch.setattr(cli_mod, "create_server", fake_create)
    with pytest.raises(SystemExit) as ei:
        main(
            [
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                "9999",
                "--transport",
                "stdio",
                "--auth-mode",
                "bearer",
                "--bearer-token",
                "secret-token",
                "--provider",
                "ddgs",
                "--max-results",
                "3",
                "--log-level",
                "DEBUG",
            ]
        )
    assert ei.value.code == 0
    assert calls.get("ran") is True
    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 9999
    assert calls["transport"] == "stdio"
    assert calls["auth_mode"] == "bearer"
    assert calls["token"] == "secret-token"
    assert calls["provider"] == "ddgs"
    assert calls["max_results"] == 3
    assert calls["log_level"] == "DEBUG"


def test_cli_top_level_flags_imply_serve(monkeypatch):
    from websift import cli as cli_mod

    calls = {}

    class FakeApp:
        def run(self):
            calls["ran"] = True

    def fake_create(settings):
        calls["port"] = settings.server.port
        return FakeApp()

    monkeypatch.setattr(cli_mod, "create_server", fake_create)
    with pytest.raises(SystemExit) as ei:
        main(["--port", "8777"])
    assert ei.value.code == 0
    assert calls["ran"] is True
    assert calls["port"] == 8777


def test_cli_bare_defaults_to_serve(monkeypatch):
    from websift import cli as cli_mod

    calls = {"ran": False}

    class FakeApp:
        def run(self):
            calls["ran"] = True

    monkeypatch.setattr(cli_mod, "create_server", lambda settings: FakeApp())
    with pytest.raises(SystemExit) as ei:
        main([])
    assert ei.value.code == 0
    assert calls["ran"] is True


def test_cli_serve_config_error(monkeypatch, capsys):
    from websift import cli as cli_mod
    from websift.settings import SettingsError

    def boom(*_a, **_k):
        raise SettingsError("bad", code="x")

    monkeypatch.setattr(cli_mod.AppSettings, "from_env", boom)
    with pytest.raises(SystemExit) as ei:
        main(["serve"])
    assert ei.value.code == 2
    assert "configuration error" in capsys.readouterr().err


def test_cli_search_config_error(monkeypatch, capsys):
    from websift import cli as cli_mod
    from websift.settings import SettingsError

    def boom(*_a, **_k):
        raise SettingsError("bad", code="x")

    monkeypatch.setattr(cli_mod.AppSettings, "from_env", boom)
    with pytest.raises(SystemExit) as ei:
        main(["search", "q"])
    assert ei.value.code == 2
    assert "configuration error" in capsys.readouterr().err


def test_cli_fetch_config_error(monkeypatch, capsys):
    from websift import cli as cli_mod
    from websift.settings import SettingsError

    def boom(*_a, **_k):
        raise SettingsError("bad", code="x")

    monkeypatch.setattr(cli_mod.AppSettings, "from_env", boom)
    with pytest.raises(SystemExit) as ei:
        main(["fetch", "https://example.com"])
    assert ei.value.code == 2
    assert "configuration error" in capsys.readouterr().err
