"""Diagnostics helpers for ``websift doctor`` / ``websift providers`` (no secrets)."""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from typing import Any

from websift import __version__
from websift.models import JSON_SCHEMA_VERSION
from websift.providers.registry import is_registered, list_providers
from websift.settings import AppSettings, SettingsError

# Map registry name -> (module, class) for capability introspection without credentials.
_PROVIDER_CLASSES: dict[str, tuple[str, str]] = {
    "ddgs": ("websift.providers.ddgs", "DdgsProvider"),
    "searxng": ("websift.providers.searxng", "SearxngProvider"),
    "brave": ("websift.providers.brave", "BraveProvider"),
    "tavily": ("websift.providers.tavily", "TavilyProvider"),
    "exa": ("websift.providers.exa", "ExaProvider"),
    "serper": ("websift.providers.serper", "SerperProvider"),
}


def mcp_installed() -> bool:
    return importlib.util.find_spec("mcp") is not None


def _capabilities_for(name: str) -> dict[str, bool] | None:
    path = _PROVIDER_CLASSES.get(name)
    if path is None:
        return None
    mod = importlib.import_module(path[0])
    cls = getattr(mod, path[1])
    caps = getattr(cls, "capabilities", None)
    if caps is None:
        return None
    return {
        "safe_search": bool(caps.safe_search),
        "region": bool(caps.region),
        "time_range": bool(caps.time_range),
        "pagination": bool(caps.pagination),
        "domain_filter": bool(caps.domain_filter),
    }


def providers_report(*, as_json: bool = False) -> tuple[int, str]:
    """List allowlisted providers and capabilities."""
    rows: list[dict[str, Any]] = []
    for name in list_providers():
        rows.append({"name": name, "capabilities": _capabilities_for(name)})

    if as_json:
        return 0, json.dumps(
            {"schema_version": JSON_SCHEMA_VERSION, "providers": rows},
            ensure_ascii=False,
            indent=2,
        )

    lines = ["Registered search providers:"]
    for row in rows:
        caps = row.get("capabilities") or {}
        if not caps:
            lines.append(f"  - {row['name']}")
            continue
        flags = []
        for key in ("safe_search", "region", "time_range", "pagination", "domain_filter"):
            flags.append(f"{key}={'yes' if caps.get(key) else 'no'}")
        lines.append(f"  - {row['name']}: " + ", ".join(flags))
    return 0, "\n".join(lines)


def doctor_report(*, as_json: bool = False) -> tuple[int, str]:
    """Environment/settings health check. Never prints secret values."""
    checks: list[dict[str, Any]] = []
    exit_code = 0

    def add(name: str, ok: bool, detail: str, *, level: str = "ok") -> None:
        nonlocal exit_code
        status_level = level if ok else ("warn" if level == "warn" else "error")
        checks.append({"name": name, "ok": ok, "level": status_level, "detail": detail})
        if not ok and status_level == "error":
            exit_code = 1

    add("version", True, f"websift {__version__} (Python {sys.version.split()[0]})")
    add(
        "mcp",
        True,
        "installed" if mcp_installed() else "not installed (library-only; serve needs websift[mcp])",
    )

    try:
        settings = AppSettings.from_env()
        settings.validate()
        add("settings", True, "AppSettings.from_env().validate() passed")
    except SettingsError as e:
        add("settings", False, f"{e} (code={getattr(e, 'code', '')})")
        settings = None
    except Exception as e:  # pragma: no cover
        add("settings", False, f"unexpected: {type(e).__name__}: {e}")
        settings = None

    if settings is not None:
        name = (settings.provider.name or "").strip().lower()
        add(
            "provider",
            is_registered(name),
            f"SEARCH_PROVIDER={name!r} registered={is_registered(name)}",
        )
        ep = settings.provider.endpoint(name)
        if name in {"brave", "tavily", "exa", "serper"}:
            has_key = bool((ep.api_key or "").strip())
            add(
                "credentials",
                has_key,
                f"{name} API key: {'set' if has_key else 'MISSING'}",
            )
        elif name == "searxng":
            has_url = bool((ep.base_url or "").strip())
            add(
                "credentials",
                has_url,
                f"SEARXNG_BASE_URL: {'set' if has_url else 'MISSING'}",
            )
        else:
            add("credentials", True, "default provider needs no API key")

        add(
            "cache",
            True,
            (
                f"enabled={settings.cache.enabled} backend={settings.cache.backend} "
                f"dir={'set' if settings.cache.directory else 'none'}"
            ),
        )
        allow = sorted(settings.fetch.allowed_domains)
        deny = sorted(settings.fetch.denied_domains)
        add(
            "domain_policy",
            True,
            f"allowed={allow or 'any'} denied={deny or 'none'}",
        )
        add(
            "server",
            True,
            (
                f"host={settings.server.host} port={settings.server.port} "
                f"transport={settings.server.transport} auth={settings.auth.mode}"
            ),
        )
        if not mcp_installed():
            add(
                "serve_ready",
                False,
                "MCP not installed; websift serve needs: pip install 'websift[mcp]'",
                level="warn",
            )
        else:
            add("serve_ready", True, "mcp package available")

    if as_json:
        payload = {
            "schema_version": JSON_SCHEMA_VERSION,
            "ok": exit_code == 0,
            "checks": checks,
        }
        return exit_code, json.dumps(payload, ensure_ascii=False, indent=2)

    lines = ["websift doctor"]
    for c in checks:
        if c["ok"]:
            mark = "OK"
        elif c.get("level") == "warn":
            mark = "WARN"
        else:
            mark = "FAIL"
        lines.append(f"  [{mark}] {c['name']}: {c['detail']}")
    if exit_code == 0:
        lines.append("All required checks passed.")
    else:
        lines.append("One or more checks failed.")
    return exit_code, "\n".join(lines)
