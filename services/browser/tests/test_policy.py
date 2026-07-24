from __future__ import annotations

import pytest

from browser_service.config import Settings
from browser_service.policy import BlockedTarget, merge_policy


def settings(**overrides):
    values = {
        "allow_http": False,
        "allowed_ports": frozenset({443, 8443}),
        "allowed_domains": frozenset({"example.com"}),
        "denied_domains": frozenset({"blocked.example.com"}),
    }
    values.update(overrides)
    return Settings(**values)


def test_request_policy_can_tighten_daemon_policy():
    policy = merge_policy(
        settings(),
        allow_http=False,
        allowed_ports={443},
        allowed_domains={"www.example.com"},
        denied_domains={"ads.www.example.com"},
    )
    policy.validate_url("https://www.example.com/")
    with pytest.raises(BlockedTarget):
        policy.validate_url("https://other.example.com/")
    with pytest.raises(BlockedTarget):
        policy.validate_url("https://ads.www.example.com/")


def test_request_policy_cannot_loosen_daemon_policy():
    with pytest.raises(BlockedTarget):
        merge_policy(settings(), allow_http=True, allowed_ports={443}, allowed_domains=set(), denied_domains=set())
    with pytest.raises(BlockedTarget):
        merge_policy(settings(), allow_http=False, allowed_ports={80, 443}, allowed_domains=set(), denied_domains=set())
    with pytest.raises(BlockedTarget):
        merge_policy(
            settings(), allow_http=False, allowed_ports={443}, allowed_domains={"example.net"}, denied_domains=set()
        )


def test_url_policy_rejects_userinfo_and_local_schemes():
    policy = merge_policy(
        settings(allowed_domains=frozenset()),
        allow_http=False,
        allowed_ports={443},
        allowed_domains=set(),
        denied_domains=set(),
    )
    with pytest.raises(BlockedTarget):
        policy.validate_url("https://user@example.com/")
    with pytest.raises(BlockedTarget):
        policy.validate_url("file:///etc/passwd")
