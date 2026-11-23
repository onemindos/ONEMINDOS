# SPDX-License-Identifier: Apache-2.0
"""The agent browser's pure parts (#694): URL rules, step plans, the sealed pod, the proxy's address rule.

test_agentbrowser.py drives the same rules through the gateway routes.
"""

from __future__ import annotations

import pytest

from onemind_core.agentbrowser import policy
from onemind_core.agentbrowser.pods import SESSION_LABEL, isolation_problems, session_docs
from onemind_core.agentbrowser.proxy import EgressProxy, EgressRefused


def test_a_long_path_cannot_hide_a_sign_in_or_payment_page():
    """parse() cuts the audit copy of the URL to 2048 characters; classify() reads the URL the pod gets."""
    pad = "a/" * 1100
    for tail, reason in (("checkout?amount=9", "payment"), ("login", "sign_in")):
        t = policy.parse(f"https://shop.example.org/{pad}{tail}")
        assert len(t.full) > 2048 and len(t.url) == 2048 and tail.split("?")[0] not in t.url
        assert policy.classify(t, "navigate") == reason
    assert policy.classify(policy.parse(f"https://shop.example.org/{pad}docs"), "navigate") is None


def test_url_rules():
    for bad in ("http://example.org/", "https://192.0.2.1/", "https://[::1]/", "https://user@localhost/",
                "https://example.org:8443/", "https://nas.local/", "https://localhost/", "ftp://example.org/"):
        with pytest.raises(policy.UrlRefused):
            policy.parse(bad)
    t = policy.parse("https://Docs.Example.org/a/b?token=x#frag")
    assert (t.host, t.url) == ("docs.example.org", "https://docs.example.org/a/b")
    assert policy.allowed("a.b.example.org", frozenset({"*.example.org"}))
    assert not policy.allowed("example.org", frozenset({"*.example.org"}))
    assert not policy.allowed("evilexample.org", frozenset({"example.org", "*.example.org"}))
    assert policy.classify(policy.parse("https://checkout.stripe.com/x"), "navigate") == "payment"
    assert policy.classify(policy.parse("https://shop.example.org/cart/checkout"), "navigate") == "payment"
    assert policy.classify(policy.parse("https://example.org/docs"), "navigate") is None
    assert policy.classify(policy.parse("https://example.org/docs"), "submit") == "submit"  # D-001: a submit acts
    assert policy.classify(policy.parse("https://example.org/login"), "submit") == "sign_in"
    assert not policy.public_address("192.0.2.10") and not policy.public_address("::ffff:127.0.0.1")
    assert policy.public_address("93.184.215.14")


def test_pod_is_sealed():
    docs = session_docs("onemind-agent-browser", "abs_1", image="x@sha256:" + "b" * 64, control_token="t",
                        proxy_url="http://p", control_port=9300, lifetime_s=900, max_pages=5)
    pod = next(d for d in docs if d["kind"] == "Pod")
    assert pod["spec"]["automountServiceAccountToken"] is False and pod["spec"]["activeDeadlineSeconds"] == 900
    assert pod["metadata"]["labels"][SESSION_LABEL] == "ab-1"
    assert isolation_problems(pod) == []
    pod["spec"]["volumes"].append({"name": "cookies", "persistentVolumeClaim": {"claimName": "profile-x"}})
    pod["spec"]["containers"][0]["ports"].append({"containerPort": 9222})
    assert len(isolation_problems(pod)) == 2


def test_proxy_never_dials_a_private_address():
    import asyncio

    async def resolve(host, port):
        return ["127.0.0.1", "198.51.100.7"]

    proxy = EgressProxy(lambda *a: None, resolve=resolve)
    with pytest.raises(EgressRefused):
        asyncio.run(proxy._dial_public("approved.example.org", 443))


def test_a_step_plan_pins_the_exact_url():
    """The owner approves one exact URL: another query, a dropped query or a new fragment is another plan."""
    t = policy.parse("https://shop.example.org/checkout?amount=1")
    assert t.url == "https://shop.example.org/checkout" and t.query == "?amount=1"
    plan, sha = policy.step_plan("hermes", "abs_1", "navigate", "payment", t.url, t.query, t.full_sha256)
    assert plan["full_sha256"] == t.full_sha256 and plan["query"] == "?amount=1"
    for other in ("https://shop.example.org/checkout?amount=9999&to=attacker", "https://shop.example.org/checkout",
                  "https://shop.example.org/checkout?amount=1#x"):
        o = policy.parse(other)
        assert o.url == t.url and o.full_sha256 != t.full_sha256
        assert policy.step_plan("hermes", "abs_1", "navigate", "payment", o.url, o.query, o.full_sha256)[1] != sha
    long = policy.parse("https://example.org/a?" + "q" * 3000)
    assert len(long.query) == policy.QUERY_SHOWN + 1 and long.query.endswith("\u2026")  # the card cuts, the hash does not


@pytest.mark.parametrize("url,reason", [
    ("https://shop.example.org/%63heckout?amount=9", "payment"),
    ("https://shop.example.org/%70ay?to=x", "payment"),
    ("https://shop.example.org/check%6fut/", "payment"),
    ("https://shop.example.org/%2563heckout", "payment"),           # encoded twice: some servers decode twice
    ("https://shop.example.org/a%2Fcheckout", "payment"),            # an encoded slash still splits the path
    ("https://shop.example.org/a\\cart", "payment"),                # a browser reads a backslash as a slash
    ("https://shop.example.org/%EF%BD%83heckout", "payment"),        # a fullwidth letter folds to plain c
    ("https://shop.example.org/CheckOut%00", "payment"),             # a NUL byte does not glue a word on
    ("https://example.org/%6cogin", "sign_in"),
    ("https://example.org/%4C%4F%47%49%4E/", "sign_in"),
    ("https://example.org/a;%73ign-in", "sign_in"),
])
def test_an_encoded_path_still_needs_the_owner(url, reason):
    """The server decodes the path before routing it, so the sign-in and payment rules do too (D-001)."""
    assert policy.classify(policy.parse(url), "navigate") == reason


def test_decoding_does_not_flag_an_ordinary_page():
    for url in ("https://example.org/docs/%E2%9C%93-guide", "https://example.org/checkouts-history-of-tills",
                "https://example.org/%25", "https://example.org/blog/paying-it-forward"):
        assert policy.classify(policy.parse(url), "navigate") is None
