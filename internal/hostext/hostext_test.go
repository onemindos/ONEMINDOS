// SPDX-License-Identifier: Apache-2.0

package hostext

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"hash/crc32"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func fixture(t *testing.T, name string) []byte {
	t.Helper()
	b, err := os.ReadFile(filepath.Join("testdata", name))
	if err != nil {
		t.Fatal(err)
	}
	return b
}

// keyDir returns a folder holding the named fixture certificates: the key set a box trusts.
func keyDir(t *testing.T, certs ...string) string {
	t.Helper()
	d := t.TempDir()
	for _, c := range certs {
		if err := os.WriteFile(filepath.Join(d, c), fixture(t, c), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	return d
}

func certFingerprint(t *testing.T, name string) string {
	t.Helper()
	keys, err := LoadKeys([]string{keyDir(t, name)})
	if err != nil || len(keys) != 1 {
		t.Fatalf("load %s: %v", name, err)
	}
	return fingerprint(keys[0])
}

func uuidFromHex(h string) string {
	return h[0:8] + "-" + h[8:12] + "-" + h[12:16] + "-" + h[16:20] + "-" + h[20:32]
}

// guidBytes encodes a GUID string the way GPT stores it (first three fields little-endian).
func guidBytes(s string) []byte {
	h, _ := hex.DecodeString(strings.ReplaceAll(s, "-", ""))
	b := make([]byte, 16)
	binary.LittleEndian.PutUint32(b[0:], binary.BigEndian.Uint32(h[0:]))
	binary.LittleEndian.PutUint16(b[4:], binary.BigEndian.Uint16(h[4:]))
	binary.LittleEndian.PutUint16(b[6:], binary.BigEndian.Uint16(h[6:]))
	copy(b[8:], h[8:])
	return b
}

type part struct {
	typ, uuid string
	data      []byte
}

// writeGPT writes a minimal GPT disk image (512-byte sectors), one 8-sector slot per partition.
// cmd/onemind/cli/ext_test.go carries a copy (a shared helper package would be an unwired package).
func writeGPT(t *testing.T, path string, parts []part) {
	t.Helper()
	const ss, entries, esize = 512, 128, 128
	img := make([]byte, ss*(64+8*len(parts)+40))
	tbl := make([]byte, entries*esize)
	for i, p := range parts {
		first := uint64(64 + 8*i)
		e := tbl[i*esize:]
		copy(e[0:], guidBytes(p.typ))
		copy(e[16:], guidBytes(p.uuid))
		binary.LittleEndian.PutUint64(e[32:], first)
		binary.LittleEndian.PutUint64(e[40:], first+7)
		copy(img[first*ss:], p.data)
	}
	copy(img[2*ss:], tbl)
	h := img[ss : ss+92]
	copy(h, "EFI PART")
	binary.LittleEndian.PutUint32(h[8:], 0x00010000)
	binary.LittleEndian.PutUint32(h[12:], 92)
	binary.LittleEndian.PutUint64(h[24:], 1)
	binary.LittleEndian.PutUint64(h[32:], uint64(len(img)/ss-1))
	binary.LittleEndian.PutUint64(h[40:], 34)
	binary.LittleEndian.PutUint64(h[48:], uint64(len(img)/ss-34))
	binary.LittleEndian.PutUint64(h[72:], 2)
	binary.LittleEndian.PutUint32(h[80:], entries)
	binary.LittleEndian.PutUint32(h[84:], esize)
	binary.LittleEndian.PutUint32(h[88:], crc32.ChecksumIEEE(tbl))
	binary.LittleEndian.PutUint32(h[16:], crc32.ChecksumIEEE(h))
	if err := os.WriteFile(path, img, 0o644); err != nil {
		t.Fatal(err)
	}
}

func sigJSON(rootHash string, p7s []byte, fp string) []byte {
	b, _ := json.Marshal(map[string]string{"rootHash": rootHash, "signature": base64.StdEncoding.EncodeToString(p7s), "certificateFingerprint": fp})
	return append(b, make([]byte, 4096-len(b))...)
}

func goodSig(t *testing.T) []byte {
	return sigJSON(strings.TrimSpace(string(fixture(t, "roothash"))), fixture(t, "rsa-noattr.p7s"), certFingerprint(t, "rsa.crt"))
}

// ddi builds a /usr extension image for arch whose verity signature partition holds sig (none if nil).
func ddi(t *testing.T, dir, name, arch string, sig []byte) string {
	t.Helper()
	rh := strings.TrimSpace(string(fixture(t, "roothash")))
	ty := PartTypes[arch]
	parts := []part{
		{ty.Usr, uuidFromHex(rh[:32]), []byte("erofs data, not read by the check")},
		{ty.UsrVerity, uuidFromHex(rh[32:64]), []byte("verity hash tree")},
	}
	if sig != nil {
		parts = append(parts, part{ty.UsrSig, "6a0d2c55-5f3b-4b1e-9d0e-0c0ffee00001", sig})
	}
	p := filepath.Join(dir, name)
	writeGPT(t, p, parts)
	return p
}

type box struct {
	m       *Manager
	src     string
	calls   []string
	release map[string]string
}

func newBox(t *testing.T, certs ...string) *box {
	t.Helper()
	root := t.TempDir()
	b := &box{src: filepath.Join(root, "incoming"), release: map[string]string{"ID": "onemind", "SYSEXT_LEVEL": "1.0", "CONFEXT_LEVEL": "1.0"}}
	osr := filepath.Join(root, "os-release")
	os.WriteFile(osr, []byte("ID=onemind\nNAME=\"OneMind OS\"\nSYSEXT_LEVEL=1.0\nCONFEXT_LEVEL=1.0\n"), 0o644)
	os.MkdirAll(b.src, 0o755)
	b.m = &Manager{Config: Config{
		Quarantine: filepath.Join(root, "data", "quarantine"),
		SysextDir:  filepath.Join(root, "var", "lib", "extensions"),
		ConfextDir: filepath.Join(root, "var", "lib", "confexts"),
		KeyDirs:    []string{keyDir(t, certs...)},
		OSRelease:  []string{osr},
		Arch:       "x86-64",
		ReadRelease: func(_ context.Context, image string, k Kind, name string) (map[string]string, error) {
			b.calls = append(b.calls, fmt.Sprintf("read %s %s", k, name))
			return b.release, nil
		},
		Run: func(_ context.Context, name string, args ...string) error {
			b.calls = append(b.calls, name+" "+strings.Join(args, " "))
			return nil
		},
	}}
	return b
}

func wantRefused(t *testing.T, err error, code string) {
	t.Helper()
	var r *RefusedError
	if !errors.As(err, &r) || r.Code != code {
		t.Fatalf("want refusal %q, got %v", code, err)
	}
}

func (b *box) assertNothingInstalled(t *testing.T) {
	t.Helper()
	for _, d := range []string{b.m.SysextDir, b.m.ConfextDir, b.m.Quarantine} {
		if es, _ := os.ReadDir(d); len(es) != 0 {
			t.Fatalf("%s is not empty after a refusal: %v", d, es)
		}
	}
	for _, c := range b.calls {
		if strings.Contains(c, "refresh") {
			t.Fatalf("refresh ran after a refusal: %v", b.calls)
		}
	}
}

func TestStageInstallsASignedImageAndRemoveLeavesNothing(t *testing.T) {
	b := newBox(t, "rsa.crt")
	img := ddi(t, b.src, "onemind-hello.raw", "x86-64", goodSig(t))
	ext, err := b.m.Stage(context.Background(), img, Sysext)
	if err != nil {
		t.Fatal(err)
	}
	if ext.Name != "onemind-hello" || ext.Status != "verified" || ext.RootHash != strings.TrimSpace(string(fixture(t, "roothash"))) {
		t.Fatalf("staged %+v", ext)
	}
	got, _ := os.ReadFile(filepath.Join(b.m.SysextDir, "onemind-hello.raw"))
	want, _ := os.ReadFile(img)
	if !bytes.Equal(got, want) {
		t.Fatal("the installed image differs from the verified one")
	}
	if es, _ := os.ReadDir(b.m.Quarantine); len(es) != 0 {
		t.Fatalf("quarantine not cleaned: %v", es)
	}
	if want := "systemd-sysext refresh --image-policy=" + ImagePolicy; b.calls[len(b.calls)-1] != want {
		t.Fatalf("calls %v, want last %q", b.calls, want)
	}
	if _, err := b.m.Stage(context.Background(), img, Sysext); !errors.Is(err, ErrExists) {
		t.Fatalf("second stage: %v", err)
	}
	list, err := b.m.List(context.Background())
	if err != nil || len(list) != 1 || list[0].Status != "verified" || list[0].Kind != Sysext {
		t.Fatalf("list %+v %v", list, err)
	}
	if err := b.m.Remove(context.Background(), "onemind-hello", Sysext); err != nil {
		t.Fatal(err)
	}
	if es, _ := os.ReadDir(b.m.SysextDir); len(es) != 0 {
		t.Fatalf("remove left %v", es)
	}
	if !strings.HasPrefix(b.calls[len(b.calls)-1], "systemd-sysext refresh") {
		t.Fatalf("remove must refresh so nothing stays merged in /usr: %v", b.calls)
	}
	if err := b.m.Remove(context.Background(), "onemind-hello", Sysext); !errors.Is(err, ErrNotFound) {
		t.Fatalf("remove twice: %v", err)
	}
}

func TestConfextGoesToConfexts(t *testing.T) {
	b := newBox(t, "rsa.crt")
	img := ddi(t, b.src, "greenhouse.raw", "x86-64", goodSig(t))
	if _, err := b.m.Stage(context.Background(), img, Confext); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(b.m.ConfextDir, "greenhouse.raw")); err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(b.calls[len(b.calls)-1], "systemd-confext refresh") {
		t.Fatalf("calls %v", b.calls)
	}
}

func TestUnsignedImageRefused(t *testing.T) {
	b := newBox(t, "rsa.crt")
	_, err := b.m.Stage(context.Background(), ddi(t, b.src, "x.raw", "x86-64", nil), Sysext)
	wantRefused(t, err, "unsigned")
	b.assertNothingInstalled(t)
}

func TestWrongKeyRefused(t *testing.T) {
	b := newBox(t, "ec.crt") // the box trusts only the EC key; the image is signed with the RSA key
	_, err := b.m.Stage(context.Background(), ddi(t, b.src, "x.raw", "x86-64", goodSig(t)), Sysext)
	wantRefused(t, err, "untrusted_key")
	b.assertNothingInstalled(t)
}

func TestTamperedRootHashRefused(t *testing.T) {
	b := newBox(t, "rsa.crt")
	rh := []byte(strings.TrimSpace(string(fixture(t, "roothash"))))
	rh[0] ^= 1 // the signed hash no longer matches the one the partitions carry
	_, err := b.m.Stage(context.Background(), ddi(t, b.src, "x.raw", "x86-64", sigJSON(string(rh), fixture(t, "rsa-noattr.p7s"), "")), Sysext)
	if err == nil {
		t.Fatal("tampered root hash accepted")
	}
	b.assertNothingInstalled(t)
}

func TestWrongLevelRefused(t *testing.T) {
	for _, tc := range []struct {
		name    string
		release map[string]string
		code    string
	}{
		{"level 2.0", map[string]string{"ID": "onemind", "SYSEXT_LEVEL": "2.0"}, "wrong_level"},
		{"no level", map[string]string{"ID": "onemind", "VERSION_ID": "1"}, "wrong_level"},
		{"other OS", map[string]string{"ID": "debian", "SYSEXT_LEVEL": "1.0"}, "wrong_os"},
		{"any OS", map[string]string{"ID": "_any"}, "wrong_os"},
		{"other arch", map[string]string{"ID": "onemind", "SYSEXT_LEVEL": "1.0", "ARCHITECTURE": "arm64"}, "wrong_arch"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			b := newBox(t, "rsa.crt")
			b.release = tc.release
			_, err := b.m.Stage(context.Background(), ddi(t, b.src, "x.raw", "x86-64", goodSig(t)), Sysext)
			wantRefused(t, err, tc.code)
			b.assertNothingInstalled(t)
		})
	}
}

func TestHostWithoutLevelRefusesEverything(t *testing.T) {
	b := newBox(t, "rsa.crt")
	os.WriteFile(b.m.OSRelease[0], []byte("ID=onemind\n"), 0o644)
	_, err := b.m.Stage(context.Background(), ddi(t, b.src, "x.raw", "x86-64", goodSig(t)), Sysext)
	wantRefused(t, err, "wrong_level")
}

func TestDirectoryAndOtherNonImagesRefused(t *testing.T) {
	b := newBox(t, "rsa.crt")
	dir := filepath.Join(b.src, "tree.raw")
	os.MkdirAll(filepath.Join(dir, "usr", "bin"), 0o755)
	_, err := b.m.Stage(context.Background(), dir, Sysext)
	wantRefused(t, err, "not_image")
	img := ddi(t, b.src, "real.raw", "x86-64", goodSig(t))
	link := filepath.Join(b.src, "link.raw")
	os.Symlink(img, link)
	_, err = b.m.Stage(context.Background(), link, Sysext)
	wantRefused(t, err, "not_image")
	plain := filepath.Join(b.src, "plain.raw")
	os.WriteFile(plain, bytes.Repeat([]byte{0}, 8192), 0o644)
	_, err = b.m.Stage(context.Background(), plain, Sysext)
	wantRefused(t, err, "not_image")
	for _, n := range []string{"noext.img", ".hidden.raw", "a b.raw"} {
		p := ddi(t, b.src, n, "x86-64", goodSig(t))
		_, err = b.m.Stage(context.Background(), p, Sysext)
		wantRefused(t, err, "bad_name")
	}
	b.assertNothingInstalled(t)
}

func TestOtherArchitectureImageRefused(t *testing.T) {
	b := newBox(t, "rsa.crt")
	_, err := b.m.Stage(context.Background(), ddi(t, b.src, "x.raw", "arm64", goodSig(t)), Sysext)
	wantRefused(t, err, "unsigned")
	b.assertNothingInstalled(t)
}

func TestListFlagsDirectoriesAndUnsignedImages(t *testing.T) {
	b := newBox(t, "rsa.crt")
	os.MkdirAll(filepath.Join(b.m.SysextDir, "handmade", "usr"), 0o755)
	ddi(t, b.m.SysextDir, "sneaky.raw", "x86-64", nil)
	list, err := b.m.List(context.Background())
	if err != nil || len(list) != 2 {
		t.Fatalf("list %+v %v", list, err)
	}
	for _, e := range list {
		if e.Status == "verified" {
			t.Fatalf("%s listed as verified", e.Name)
		}
	}
}

func TestRefreshFailureRollsBack(t *testing.T) {
	b := newBox(t, "rsa.crt")
	b.m.Run = func(_ context.Context, name string, args ...string) error { return errors.New("merge failed") }
	if _, err := b.m.Stage(context.Background(), ddi(t, b.src, "x.raw", "x86-64", goodSig(t)), Sysext); err == nil {
		t.Fatal("refresh failure not reported")
	}
	if es, _ := os.ReadDir(b.m.SysextDir); len(es) != 0 {
		t.Fatalf("a failed refresh must not leave the image installed: %v", es)
	}
}

func TestNoKeysMeansNoExtensions(t *testing.T) {
	b := newBox(t)
	_, err := b.m.Stage(context.Background(), ddi(t, b.src, "x.raw", "x86-64", goodSig(t)), Sysext)
	wantRefused(t, err, "untrusted_key")
}

// TestSfdiskImage checks the GPT reader against a table written by util-linux sfdisk (Linux CI).
func TestSfdiskImage(t *testing.T) {
	sfdisk, err := exec.LookPath("sfdisk")
	if err != nil {
		t.Skip("sfdisk not installed")
	}
	rh := strings.TrimSpace(string(fixture(t, "roothash")))
	ty := PartTypes["x86-64"]
	p := filepath.Join(t.TempDir(), "real.raw")
	if err := os.WriteFile(p, make([]byte, 4<<20), 0o644); err != nil {
		t.Fatal(err)
	}
	script := fmt.Sprintf("label: gpt\nstart=2048, size=8, type=%s, uuid=%s\nstart=2056, size=8, type=%s, uuid=%s\nstart=2064, size=8, type=%s\n",
		ty.Usr, uuidFromHex(rh[:32]), ty.UsrVerity, uuidFromHex(rh[32:64]), ty.UsrSig)
	cmd := exec.Command(sfdisk, "--no-reread", "--no-tell-kernel", p)
	cmd.Stdin = strings.NewReader(script)
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("sfdisk: %v\n%s", err, out)
	}
	f, _ := os.OpenFile(p, os.O_WRONLY, 0)
	f.WriteAt(goodSig(t), 2064*512)
	f.Close()
	keys, _ := LoadKeys([]string{keyDir(t, "rsa.crt")})
	v, err := VerifyImage(p, "x86-64", keys)
	if err != nil || v.RootHash != rh || v.Partition != "usr" {
		t.Fatalf("sfdisk image: %+v %v", v, err)
	}
}
