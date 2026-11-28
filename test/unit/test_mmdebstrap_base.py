# SPDX-License-Identifier: Apache-2.0
"""Step 2 PR 9: the Debian base is made by mmdebstrap from the pinned snapshot, not taken from a Docker Hub image."""
import os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
read = lambda p: open(os.path.join(ROOT, p)).read()
CF = read("os/rootfs/Containerfile")


class DebianBase(unittest.TestCase):
    def test_debian_base_is_built_from_scratch_by_mmdebstrap(self):
        self.assertIn("FROM scratch AS base-debian", CF)
        self.assertIn("COPY --from=bootstrap /newroot/ /", CF)
        self.assertRegex(CF, r"(?m)^FROM base-\$\{LEG\} AS base$")
        sh = read("os/rootfs/sources/mkbase.sh")
        self.assertIn("mmdebstrap --mode=chrootless --variant=minbase", sh)
        # all three suites configure-apt.sh gives the image, from the same snapshot
        for suite in ("trixie main", "trixie-updates main", "trixie-security main"):
            self.assertIn(suite, sh)
        self.assertIn("signed-by=$KR", sh)

    def test_no_stage_starts_from_the_hub_image_as_the_base(self):
        # BASE may host mmdebstrap (bootstrap*) and be the Ubuntu hedge's base (base-ubuntu*), nothing else.
        for stage in re.findall(r"(?m)^FROM (?:--platform=\S+ )?\$\{BASE\} AS (\S+)$", CF):
            self.assertRegex(stage, r"^(bootstrap|bootstrap-build|base-ubuntu|base-ubuntu-build)$", stage)
        self.assertIn("FROM --platform=$BUILDPLATFORM base-${LEG}-build AS onemind-buildbase", CF)

    def test_build_only_helpers_do_not_ship(self):
        self.assertIn("/usr/sbin/policy-rc.d", CF)
        rm = [l for l in CF.splitlines() if l.strip().startswith("rm -f /usr/sbin/policy-rc.d")]
        self.assertEqual(len(rm), 1)
        for gone in ("onemind-build-speedup", "/etc/apt/apt.conf.d/docker-*", "/etc/dpkg/dpkg.cfg.d/docker-*"):
            self.assertIn(gone, rm[0])

    def test_t0_fails_on_container_leftovers(self):
        s = read("test/qemu/mkfixtures.sh")
        self.assertIn('checks["no_container_leftovers"]', s)
        for leftover in ("usr/sbin/policy-rc.d", ".dockerenv", "etc/apt/apt.conf.d/docker-*", "etc/dpkg/dpkg.cfg.d/docker-*"):
            self.assertIn(leftover, s)

    def test_apt_config_replaces_what_the_hub_image_set(self):
        s = read("os/rootfs/sources/configure-apt.sh")
        self.assertIn('Acquire::Languages "none";', s)                # was docker-no-languages
        self.assertIn('APT::Keep-Downloaded-Packages "false";', s)    # was docker-clean (no .deb files left in the root)


if __name__ == "__main__":
    unittest.main()
