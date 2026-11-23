// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"hash/crc32"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/onemindos/onemindos/internal/hostext"
)

// extFixtures are the OpenSSL fixtures of internal/hostext (testdata/README.md there).
var extFixtures = filepath.Join("..", "..", "..", "internal", "hostext", "testdata")

func extFixture(t *testing.T, name string) []byte {
	t.Helper()
	b, err := os.ReadFile(filepath.Join(extFixtures, name))
	if err != nil {
		t.Fatal(err)
	}
	return b
}

// extImage writes a /usr extension image (GPT, 512-byte sectors), signed with the RSA fixture key
// or with no signature partition. A trimmed copy of writeGPT in internal/hostext/hostext_test.go.
func extImage(t *testing.T, dir, name string, signed bool) string {
	t.Helper()
	rh := strings.TrimSpace(string(extFixture(t, "roothash")))
	ty := hostext.PartTypes["x86-64"]
	keys, _ := hostext.LoadKeys([]string{extFixtures})
	var fp string
	for _, k := range keys {
		if k.Subject.CommonName == "OneMind test sysext key (fixture only)" {
			s := sha256.Sum256(k.Raw)
			fp = hex.EncodeToString(s[:])
		}
	}
	sig, _ := json.Marshal(map[string]string{"rootHash": rh, "signature": base64.StdEncoding.EncodeToString(extFixture(t, "rsa-noattr.p7s")), "certificateFingerprint": fp})
	uuid := func(h string) string {
		return h[0:8] + "-" + h[8:12] + "-" + h[12:16] + "-" + h[16:20] + "-" + h[20:32]
	}
	parts := [][3]string{{ty.Usr, uuid(rh[:32])}, {ty.UsrVerity, uuid(rh[32:64])}}
	if signed {
		parts = append(parts, [3]string{ty.UsrSig, "6a0d2c55-5f3b-4b1e-9d0e-0c0ffee00001", string(sig)})
	}
	img, tbl := make([]byte, 512*128), make([]byte, 128*128)
	for i, p := range parts {
		e, first := tbl[i*128:], uint64(64+8*i)
		for j, g := range p[:2] {
			h, _ := hex.DecodeString(strings.ReplaceAll(g, "-", ""))
			binary.LittleEndian.PutUint32(e[16*j:], binary.BigEndian.Uint32(h))
			binary.LittleEndian.PutUint16(e[16*j+4:], binary.BigEndian.Uint16(h[4:]))
			binary.LittleEndian.PutUint16(e[16*j+6:], binary.BigEndian.Uint16(h[6:]))
			copy(e[16*j+8:], h[8:])
		}
		binary.LittleEndian.PutUint64(e[32:], first)
		binary.LittleEndian.PutUint64(e[40:], first+7)
		copy(img[first*512:], p[2])
	}
	copy(img[1024:], tbl)
	h := img[512 : 512+92]
	copy(h, "EFI PART")
	binary.LittleEndian.PutUint32(h[12:], 92)
	binary.LittleEndian.PutUint64(h[72:], 2)
	binary.LittleEndian.PutUint32(h[80:], 128)
	binary.LittleEndian.PutUint32(h[84:], 128)
	binary.LittleEndian.PutUint32(h[88:], crc32.ChecksumIEEE(tbl))
	binary.LittleEndian.PutUint32(h[16:], crc32.ChecksumIEEE(h))
	p := filepath.Join(dir, name)
	if err := os.WriteFile(p, img, 0o644); err != nil {
		t.Fatal(err)
	}
	return p
}

// extBox points `onemind ext` at temp folders, fake systemd tools and a fixed extension-release.
func extBox(t *testing.T) (root string, flags []string, calls *[]string) {
	t.Helper()
	isolate(t)
	root = t.TempDir()
	osr := filepath.Join(root, "os-release")
	os.WriteFile(osr, []byte("ID=onemind\nSYSEXT_LEVEL=1.0\n"), 0o644)
	calls = &[]string{}
	keys := filepath.Join(root, "keys")
	os.MkdirAll(keys, 0o755)
	os.WriteFile(filepath.Join(keys, "rsa.crt"), extFixture(t, "rsa.crt"), 0o644)
	old := newHostext
	newHostext = func(c hostext.Config) *hostext.Manager {
		c.Arch = "x86-64"
		c.ReadRelease = func(context.Context, string, hostext.Kind, string) (map[string]string, error) {
			return map[string]string{"ID": "onemind", "SYSEXT_LEVEL": "1.0"}, nil
		}
		c.Run = func(_ context.Context, name string, args ...string) error {
			*calls = append(*calls, name+" "+strings.Join(args, " "))
			return nil
		}
		return hostext.New(c)
	}
	t.Cleanup(func() { newHostext = old })
	flags = []string{"--quarantine", filepath.Join(root, "q"), "--sysext-dir", filepath.Join(root, "ext"),
		"--confext-dir", filepath.Join(root, "conf"), "--keys", keys, "--os-release", osr}
	return root, flags, calls
}

func TestExtStageListRemove(t *testing.T) {
	root, flags, calls := extBox(t)
	img := extImage(t, root, "onemind-hello.raw", true)
	r := run(t, "", false, append([]string{"ext", "stage", img}, flags...)...)
	if r.code != 0 || !strings.Contains(r.out, "installed sysext onemind-hello") {
		t.Fatalf("stage %+v", r)
	}
	if len(*calls) != 1 || (*calls)[0] != "systemd-sysext refresh --image-policy="+hostext.ImagePolicy {
		t.Fatalf("calls %v", *calls)
	}
	r = run(t, "", false, append([]string{"--json", "ext", "list"}, flags...)...)
	var got struct {
		Schema     string
		Extensions []struct{ Kind, Name, Status string }
	}
	if r.code != 0 || json.Unmarshal([]byte(r.out), &got) != nil || got.Schema != "onemind.cli.ext/v1" ||
		len(got.Extensions) != 1 || got.Extensions[0].Name != "onemind-hello" || got.Extensions[0].Status != "verified" {
		t.Fatalf("list %+v", r)
	}
	if r = run(t, "", false, append([]string{"ext", "stage", img}, flags...)...); r.code != ExitConflict {
		t.Fatalf("stage twice %+v", r)
	}
	if r = run(t, "", false, append([]string{"ext", "remove", "onemind-hello"}, flags...)...); r.code != 0 {
		t.Fatalf("remove %+v", r)
	}
	if es, _ := os.ReadDir(filepath.Join(root, "ext")); len(es) != 0 {
		t.Fatalf("remove left %v", es)
	}
	if r = run(t, "", false, append([]string{"ext", "remove", "onemind-hello"}, flags...)...); r.code != ExitNotFound {
		t.Fatalf("remove twice %+v", r)
	}
	if r = run(t, "", false, append([]string{"ext", "list"}, flags...)...); r.code != 0 || !strings.Contains(r.out, "no host extensions") {
		t.Fatalf("empty list %+v", r)
	}
}

func TestExtStageRefusals(t *testing.T) {
	root, flags, calls := extBox(t)
	dir := filepath.Join(root, "tree.raw")
	os.MkdirAll(filepath.Join(dir, "usr", "bin"), 0o755)
	for _, tc := range []struct {
		path string
		code int
		name string
	}{
		{extImage(t, root, "unsigned.raw", false), ExitVerifyFailed, "verify_failed"},
		{dir, ExitRefused, "refused"},
	} {
		r := run(t, "", false, append([]string{"--json", "ext", "stage", tc.path}, flags...)...)
		if r.code != tc.code || !strings.Contains(r.errOut+r.out, tc.name) {
			t.Errorf("%s: %+v", tc.path, r)
		}
	}
	if len(*calls) != 0 {
		t.Fatalf("a refused image must never reach systemd: %v", *calls)
	}
	if es, _ := os.ReadDir(filepath.Join(root, "ext")); len(es) != 0 {
		t.Fatalf("refused images installed: %v", es)
	}
}
