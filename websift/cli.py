"""Command-line interface for websift.

Examples::

    websift --help
    websift --version
    websift serve
    websift serve --host 0.0.0.0 --port 9000
    websift search "python 3.12 features"
    websift search "python" --json
    websift search "q1" "q2" --json
    websift fetch https://docs.python.org/3/
    websift fetch https://example.com --json
    websift doctor
    websift providers
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from typing import Sequence

from websift import __version__
from websift.client import WebSearchClient
from websift.doctor import doctor_report, providers_report
from websift.models import batch_search_to_dict
from websift.server import create_server
from websift.settings import AppSettings, SettingsError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="websift",
        description=(
            "websift — free self-hosted web search + page fetch for AI agents (MCP server and Python library)."
        ),
        epilog=(
            "Environment variables (MCP_HOST, SEARCH_PROVIDER, …) still apply. "
            "CLI flags override env for the current process. "
            "See README for the full configuration matrix."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    serve = sub.add_parser(
        "serve",
        help="Start the MCP server (default when no command is given)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    _add_serve_args(serve)
    serve.set_defaults(_handler="serve")

    search = sub.add_parser(
        "search",
        help="Run one or more web searches and print results",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    search.add_argument(
        "query",
        nargs="+",
        help="Search query string(s); multiple queries run as a concurrent batch",
    )
    search.add_argument(
        "-n",
        "--max-results",
        type=int,
        default=None,
        help="Max results (default: env SEARCH_MAX_RESULTS or 5)",
    )
    search.add_argument(
        "--provider",
        default=None,
        help="Search provider name (default: env SEARCH_PROVIDER or ddgs)",
    )
    search.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Search timeout in seconds",
    )
    search.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON schema v2 (ok/results/error) for scripting",
    )
    search.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Max concurrent workers for multi-query batch (default: SEARCH_MAX_CONCURRENCY)",
    )
    search.set_defaults(_handler="search")

    fetch = sub.add_parser(
        "fetch",
        help="Fetch a URL and print readable text (HTML→Markdown, PDF→text)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    fetch.add_argument("url", help="URL to fetch")
    fetch.add_argument(
        "--max-chars",
        type=int,
        default=None,
        dest="max_page_chars",
        help="Max characters of output (default: env PAGE_MAX_CHARS)",
    )
    fetch.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Fetch timeout in seconds",
    )
    fetch.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON schema v2 (ok/content/error) for scripting",
    )
    fetch.set_defaults(_handler="fetch")

    doctor = sub.add_parser(
        "doctor",
        help="Check install, settings, credentials (no secrets printed), and MCP readiness",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    doctor.add_argument("--json", action="store_true", help="Print JSON report")
    doctor.set_defaults(_handler="doctor")

    providers = sub.add_parser(
        "providers",
        help="List registered search providers and capabilities",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    providers.add_argument("--json", action="store_true", help="Print JSON list")
    providers.set_defaults(_handler="providers")

    return parser


def _add_serve_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--host",
        default=None,
        help="Bind address (default: env MCP_HOST or 127.0.0.1)",
    )
    p.add_argument(
        "--port",
        type=int,
        default=None,
        help="Listen port (default: env MCP_PORT or 8787)",
    )
    p.add_argument(
        "--transport",
        choices=("streamable-http", "sse", "stdio"),
        default=None,
        help="MCP transport (default: env MCP_TRANSPORT or streamable-http)",
    )
    p.add_argument(
        "--auth-mode",
        choices=("none", "bearer"),
        default=None,
        help="HTTP/SSE auth mode (default: env MCP_AUTH_MODE or none)",
    )
    p.add_argument(
        "--bearer-token",
        default=None,
        help="Bearer token when --auth-mode=bearer (or env MCP_BEARER_TOKEN)",
    )
    p.add_argument(
        "--provider",
        default=None,
        help="Search provider (default: env SEARCH_PROVIDER or ddgs)",
    )
    p.add_argument(
        "--max-results",
        type=int,
        default=None,
        help="Max search results (default: env SEARCH_MAX_RESULTS or 5)",
    )
    p.add_argument(
        "--log-level",
        default=None,
        choices=("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"),
        help="Log level (default: env LOG_LEVEL or INFO)",
    )


def _settings_from_env_with_cli(
    *,
    host: str | None = None,
    port: int | None = None,
    transport: str | None = None,
    auth_mode: str | None = None,
    bearer_token: str | None = None,
    provider: str | None = None,
    max_results: int | None = None,
    log_level: str | None = None,
    search_timeout: float | None = None,
    fetch_timeout: float | None = None,
    max_page_chars: int | None = None,
) -> AppSettings:
    """Load env settings, then apply non-None CLI overrides."""
    settings = AppSettings.from_env()

    server = settings.server
    if host is not None or port is not None or transport is not None or auth_mode is not None:
        server = replace(
            server,
            host=host if host is not None else server.host,
            port=port if port is not None else server.port,
            transport=transport if transport is not None else server.transport,
            auth_mode=auth_mode if auth_mode is not None else server.auth_mode,
        )

    auth = settings.auth
    if auth_mode is not None or bearer_token is not None:
        auth = replace(
            auth,
            mode=auth_mode if auth_mode is not None else auth.mode,
            bearer_token=bearer_token if bearer_token is not None else auth.bearer_token,
        )
        if auth_mode is not None:
            server = replace(server, auth_mode=auth_mode)

    prov = settings.provider
    if provider is not None or max_results is not None or search_timeout is not None:
        prov = replace(
            prov,
            name=provider if provider is not None else prov.name,
            max_results=max_results if max_results is not None else prov.max_results,
            timeout_seconds=(float(search_timeout) if search_timeout is not None else prov.timeout_seconds),
        )

    fetch = settings.fetch
    if fetch_timeout is not None:
        fetch = replace(fetch, timeout_seconds=float(fetch_timeout))

    extraction = settings.extraction
    if max_page_chars is not None:
        extraction = replace(extraction, max_page_chars=int(max_page_chars))

    logging_s = settings.logging
    if log_level is not None:
        logging_s = replace(logging_s, level=log_level)

    return replace(
        settings,
        server=server,
        auth=auth,
        provider=prov,
        fetch=fetch,
        extraction=extraction,
        logging=logging_s,
    )


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        settings = _settings_from_env_with_cli(
            host=args.host,
            port=args.port,
            transport=args.transport,
            auth_mode=args.auth_mode,
            bearer_token=args.bearer_token,
            provider=args.provider,
            max_results=args.max_results,
            log_level=args.log_level,
        )
        settings.validate()
    except SettingsError as e:
        print(f"websift: configuration error: {e}", file=sys.stderr)
        return 2

    try:
        create_server(settings).run()
    except ImportError as e:
        print(f"websift: {e}", file=sys.stderr)
        return 2
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    try:
        settings = _settings_from_env_with_cli(
            provider=args.provider,
            max_results=args.max_results,
            search_timeout=args.timeout,
        )
        client = WebSearchClient(settings=settings)
    except SettingsError as e:
        print(f"websift: configuration error: {e}", file=sys.stderr)
        return 2

    queries = list(args.query)
    as_json = bool(getattr(args, "json", False))
    workers = getattr(args, "workers", None)

    if len(queries) == 1:
        if as_json:
            response = client.search_structured(queries[0])
            print(json.dumps(response.to_dict(), ensure_ascii=False))
            return 0 if response.ok else 1
        print(client.search(queries[0]))
        return 0

    responses = client.search_many(queries, max_workers=workers)
    if as_json:
        print(json.dumps(batch_search_to_dict(responses), ensure_ascii=False))
        return 0 if all(r.ok for r in responses) else 1
    from websift.client import format_search_response

    for i, (q, resp) in enumerate(zip(queries, responses)):
        if i:
            print("\n" + "=" * 40 + "\n")
        print(f"# query: {q}\n")
        print(format_search_response(resp))
    return 0 if all(r.ok for r in responses) else 1


def cmd_fetch(args: argparse.Namespace) -> int:
    try:
        settings = _settings_from_env_with_cli(
            fetch_timeout=args.timeout,
            max_page_chars=args.max_page_chars,
        )
        client = WebSearchClient(settings=settings)
    except SettingsError as e:
        print(f"websift: configuration error: {e}", file=sys.stderr)
        return 2
    if getattr(args, "json", False):
        result = client.fetch_structured(args.url)
        print(json.dumps(result.to_dict(), ensure_ascii=False))
        return 0 if result.ok else 1
    print(client.fetch(args.url))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    code, text = doctor_report(as_json=bool(getattr(args, "json", False)))
    print(text)
    return code


def cmd_providers(args: argparse.Namespace) -> int:
    code, text = providers_report(as_json=bool(getattr(args, "json", False)))
    print(text)
    return code


def main(argv: Sequence[str] | None = None) -> None:
    """Console entry point. ``websift`` with no args starts the MCP server."""
    argv_list = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()

    known = {"serve", "search", "fetch", "doctor", "providers", "-h", "--help", "-V", "--version"}

    # Backward compatible: bare `websift` → serve (same as pre-CLI behavior).
    if not argv_list:
        argv_list = ["serve"]
    # Allow `websift --host …` without explicit serve subcommand when first
    # token looks like a global/serve option (not a known subcommand / help).
    elif argv_list[0] not in known and argv_list[0].startswith("-"):
        argv_list = ["serve", *argv_list]

    args = parser.parse_args(argv_list)
    handler = getattr(args, "_handler", None)
    if handler == "serve":
        raise SystemExit(cmd_serve(args))
    if handler == "search":
        raise SystemExit(cmd_search(args))
    if handler == "fetch":
        raise SystemExit(cmd_fetch(args))
    if handler == "doctor":
        raise SystemExit(cmd_doctor(args))
    if handler == "providers":
        raise SystemExit(cmd_providers(args))
    parser.print_help()
    raise SystemExit(0)


if __name__ == "__main__":
    main()
