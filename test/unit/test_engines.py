# SPDX-License-Identifier: Apache-2.0
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_engines", ROOT / "scripts/check-engines.py")
check_engines = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_engines)


class EngineRegister(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        deploy = self.root / "deploy"
        deploy.mkdir()
        self.compose = deploy / "compose.yaml"
        self.compose.write_text("    image: example/engine:3.0@sha256:" + "a" * 64, encoding="utf-8")
        self.engine = {
            "id": "test-engine",
            "upstream": "https://example.test/engine",
            "spdx": "MIT",
            "licence_url": "https://example.test/engine/licence",
            "pinned": {"source": "deploy/compose.yaml", "selector": "example/engine:"},
            "runs_as": "container",
            "modified": False,
            "used_by": ["test-app"],
            "adapter": "Local HTTP adapter",
            "swap_plan": "Keep the existing API contract and data.",
            "images": ["docker.io/example/engine"],
        }

    def errors(self, **override):
        return "\n".join(check_engines.validate(self.root, {"engines": [{**self.engine, **override}]}))

    def test_seed_register_matches_the_repo(self):
        register = json.loads((ROOT / "deploy/engines.yaml").read_text(encoding="utf-8"))
        self.assertEqual(check_engines.validate(ROOT, register), [])

    def test_image_repository_matches_tags_digests_and_docker_hub_aliases(self):
        self.assertFalse(self.errors())
        self.compose.write_text("    image: registry.example.test:5000/team/engine:3.1", encoding="utf-8")
        self.assertFalse(self.errors(
            images=["registry.example.test:5000/team/engine"],
            pinned={"source": "deploy/compose.yaml", "selector": "team/engine:"},
        ))

    def test_requires_each_pinned_deploy_image(self):
        with self.compose.open("a", encoding="utf-8") as f:
            f.write("\n    image: example/unlisted:1.2\n")
        self.assertIn("docker.io/example/unlisted is missing", self.errors())

    def test_requires_swap_plan_and_live_version_reference(self):
        self.assertIn("missing swap_plan", self.errors(swap_plan=" "))
        self.assertIn("version selector is missing", self.errors(
            pinned={"source": "deploy/compose.yaml", "selector": "deleted-pin"},
        ))

    def test_requires_active_image_declaration_for_manifest_pin(self):
        manifests = self.root / "apps/offline-maps/manifests"
        manifests.mkdir(parents=True)
        manifest = manifests / "deployment.yaml"
        pinned = {"source": str(manifest.relative_to(self.root)), "selector": "protomaps/go-pmtiles:"}
        image = '    image: "docker.io/protomaps/go-pmtiles:v1.31.2"'
        manifest.write_text(image + "\n", encoding="utf-8")
        self.assertFalse(self.errors(pinned=pinned))
        manifest.write_text("    # " + image.lstrip() + "\n", encoding="utf-8")
        self.assertIn("version selector is missing", self.errors(pinned=pinned))

    def test_requires_active_nonempty_env_pin(self):
        pins = self.root / "deploy/pins.env"
        pinned = {"source": "deploy/pins.env", "selector": "RESTIC_VERSION"}
        for assignment in (
            '# RESTIC_VERSION="0.19.1"',
            'OTHER_RESTIC_VERSION="0.19.1"',
            'RESTIC_VERSION= # no version',
            'RESTIC_VERSION=""',
            "RESTIC_VERSION='  '",
            'RESTIC_VERSION="0.19.1"\nRESTIC_VERSION=""',
            'RESTIC_VERSION="${UNSET_RESTIC_VERSION:-}"',
            'RESTIC_VERSION="0.19.1"\nRESTIC_VERSION=${UNSET_RESTIC_VERSION:-}',
        ):
            with self.subTest(assignment=assignment):
                pins.write_text(assignment + "\n", encoding="utf-8")
                self.assertIn("version selector is missing", self.errors(pinned=pinned))

        pins.write_text('# RESTIC_VERSION=""\nexport RESTIC_VERSION="0.19.1" # live pin\n', encoding="utf-8")
        self.assertFalse(self.errors(pinned=pinned))

    def test_rejects_gpl_agpl_and_other_non_allowlisted_app_binary_licences(self):
        for spdx in ("GPL-3.0-only", "AGPL-3.0-or-later", "Proprietary", "UNVERIFIED"):
            with self.subTest(spdx=spdx):
                self.assertIn(f"D-032 forbids {spdx}", self.errors(spdx=spdx, also_runs_as=["library-in-app"]))

    def test_accepts_allowlisted_app_binary_licences(self):
        for spdx in ("MIT", "BSD-3-Clause", "Apache-2.0", "MPL-2.0", "CC0-1.0", "LicenseRef-Public-Domain"):
            with self.subTest(spdx=spdx):
                self.assertFalse(self.errors(spdx=spdx, also_runs_as=["library-in-app"]))

    def test_gpl_engine_must_be_isolated_behind_a_protocol(self):
        self.assertFalse(self.errors(spdx="AGPL-3.0-only", protocol="CalDAV"))
        self.assertIn("standard protocol", self.errors(spdx="AGPL-3.0-only"))
        self.assertIn("own container", self.errors(spdx="GPL-3.0-only", runs_as="debian-package", protocol="CalDAV"))

    def test_modified_gpl_needs_a_published_fork(self):
        gpl = {"spdx": "GPL-3.0-only", "protocol": "CalDAV"}
        self.assertIn("missing fork_repo", self.errors(**gpl, modified=True))
        self.assertIn("missing fork_repo", self.errors(**gpl, modified=True, fork_repo=" "))
        self.assertFalse(self.errors(**gpl, modified=True, fork_repo="https://example.test/fork"))
        self.assertFalse(self.errors(**gpl, modified=False))

    def test_tag_only_images_are_found_whatever_the_tag(self):
        for text in ("    image: docker.io/library/redis:bookworm\n", "FROM example/built:${TAG}\n"):
            with self.subTest(text=text):
                self.compose.write_text(text, encoding="utf-8")
                self.assertTrue(list(check_engines.deploy_images(self.root)))

    def test_unverified_plans_cannot_include_a_deployment_pin(self):
        plan = {
            **self.engine, "spdx": "UNVERIFIED", "runs_as": "library-in-app",
            "planned": True, "pinned": None, "images": [],
        }
        self.compose.write_text("", encoding="utf-8")
        self.assertEqual(check_engines.validate(self.root, {"engines": [plan]}), [])
        self.assertIn("planned engine cannot declare", "\n".join(check_engines.validate(
            self.root, {"engines": [{**plan, "pinned": self.engine["pinned"]}]},
        )))
