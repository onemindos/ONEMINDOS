# SPDX-License-Identifier: Apache-2.0
"""apps/hermes-agent declares its model-provider keys in spec.secrets (no printed kubectl command)."""

from pathlib import Path

from onemind_core.catalog import Catalog

ROOT = Path(__file__).resolve().parents[2]


def test_hermes_declares_its_model_provider_keys():
    cat = Catalog(ROOT / "apps", ROOT / "sdk" / "schema" / "onemind.app.schema.json")
    apps = cat.load()
    assert "hermes-agent" in apps, cat.errors.get("hermes-agent")
    (creds,) = apps["hermes-agent"].secrets
    assert creds.name == "hermes-agent-credentials"
    keys = {k.key: k for k in creds.keys}
    assert {"OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"} <= set(keys)
    assert all(k.kind == "api-key" and k.source == "owner" for n, k in keys.items() if n.endswith("_API_KEY"))
    assert keys["OPENAI_BASE_URL"].kind == "url" and not keys["OPENAI_BASE_URL"].required
    # the Deployment loads the Secret the gateway writes, and still starts before a key is set
    deployment = (ROOT / "apps" / "hermes-agent" / "manifests" / "deployment.yaml").read_text()
    assert "name: hermes-agent-credentials\n                optional: true" in deployment


def test_no_printed_kubectl_secret_command_remains():
    readme = (ROOT / "apps" / "hermes-agent" / "README.md").read_text()
    assert "create secret generic hermes-agent-credentials" not in readme
