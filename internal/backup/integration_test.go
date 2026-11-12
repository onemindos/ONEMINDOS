// SPDX-License-Identifier: Apache-2.0

//go:build integration

// Integration test against the real restic and rest-server binaries.
//
//	ONEMIND_RESTIC=/path/to/restic ONEMIND_REST_SERVER=/path/to/rest-server \
//	  go test -tags integration -run Integration ./internal/backup/
//
// ONEMIND_VERIFY_PINS=1 also requires both binaries to match their pins
// (set by testdata/lima-integration.sh, which runs this in a Debian 13 VM).
// ONEMIND_SQLITE3 adds a real SQLite online-backup hook to the system unit.
package backup

import (
	"bytes"
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha1"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"math/big"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"slices"
	"strings"
	"testing"
	"time"
)

type itEnv struct {
	restic, restServer, sqlite string
	root                       string
}

func integrationEnv(t *testing.T) itEnv {
	e := itEnv{restic: os.Getenv("ONEMIND_RESTIC"), restServer: os.Getenv("ONEMIND_REST_SERVER"), sqlite: os.Getenv("ONEMIND_SQLITE3")}
	if e.restic == "" {
		t.Skip("ONEMIND_RESTIC not set")
	}
	if os.Getenv("ONEMIND_VERIFY_PINS") == "1" {
		for name, bin := range map[string]string{"restic": e.restic, "rest-server": e.restServer} {
			p, ok := PinFor(name, runtime.GOARCH)
			if !ok {
				t.Fatalf("no pin for %s/%s", name, runtime.GOARCH)
			}
			if err := VerifyBinary(bin, p); err != nil {
				t.Fatal(err)
			}
		}
	}
	root, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	e.root = root
	return e
}

func (e itEnv) write(t *testing.T, rel, content string) string {
	t.Helper()
	p := filepath.Join(e.root, rel)
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
	return p
}

func (e itEnv) config(t *testing.T, targets ...Target) Config {
	c := DefaultConfig()
	c.BoxID, c.NodeID = "itbox", "itnode"
	c.StateDir, c.ScratchDir = filepath.Join(e.root, "state"), filepath.Join(e.root, "scratch")
	c.Restic = ResticConfig{Binary: e.restic, CacheDir: filepath.Join(e.root, "cache"), SkipPinCheck: os.Getenv("ONEMIND_VERIFY_PINS") != "1"}
	c.DeviceKeyFile = filepath.Join(e.root, "secrets", "device.key")
	c.Schedule.VerifyMinAge = Duration{0}
	if _, err := os.Stat(c.DeviceKeyFile); err != nil {
		_ = os.MkdirAll(filepath.Dir(c.DeviceKeyFile), 0o700)
		if err := GenerateKey(c.DeviceKeyFile); err != nil {
			t.Fatal(err)
		}
	}
	c.Targets = targets
	c.Units = UnitsSpec{
		System: &SystemSpec{PathsSpec: PathsSpec{Paths: []string{filepath.Join(e.root, "data/custodian")}},
			AuditLog: filepath.Join(e.root, "data/audit/audit.jsonl")},
		Apps: []AppSpec{{ID: "photos", Revision: "r1", Paths: []string{filepath.Join(e.root, "data/storage/photos")}, Excludes: []string{"*.tmp"}}},
	}
	if e.sqlite != "" {
		c.SQLite3Binary = e.sqlite
		db := filepath.Join(e.root, "data/gateway/onemind.db")
		_ = os.MkdirAll(filepath.Dir(db), 0o755)
		if out, err := exec.Command(e.sqlite, db, "CREATE TABLE IF NOT EXISTS t(x); INSERT INTO t VALUES (1);").CombinedOutput(); err != nil {
			t.Fatalf("sqlite: %v %s", err, out)
		}
		c.Units.System.SQLite = []SQLiteFile{{Path: db, Name: "gateway.db"}}
	}
	return c
}

func (e itEnv) seed(t *testing.T) {
	e.write(t, "data/custodian/ca.pem", "ca")
	e.write(t, "data/audit/audit.jsonl", auditLines(5))
	e.write(t, "data/storage/photos/a.jpg", "photo-a")
	e.write(t, "data/storage/photos/sub/b.jpg", strings.Repeat("b", 1<<20))
	e.write(t, "data/storage/photos/skip.tmp", "x")
}

// resticDirect runs restic exactly as the emergency kit tells an owner to,
// with no OneMind code involved (B-R10, W5-R14).
func resticDirect(t *testing.T, e itEnv, repo, keyFile string, args ...string) []byte {
	t.Helper()
	cmd := exec.Command(e.restic, append([]string{"--no-cache"}, args...)...)
	cmd.Env = []string{"RESTIC_REPOSITORY=" + repo, "RESTIC_PASSWORD_FILE=" + keyFile, "PATH=/usr/bin:/bin"}
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("restic %v: %v\n%s", args, err, out)
	}
	return out
}

func TestIntegrationLocalTarget(t *testing.T) {
	e := integrationEnv(t)
	e.seed(t)
	usb := Target{ID: "usb1", Kind: KindUSB, Primary: true, USBUUID: "IT-0001", MountRoot: filepath.Join(e.root, "mnt"), AllowNonMountDir: true}
	_ = os.MkdirAll(filepath.Join(usb.MountRoot, usb.USBUUID), 0o755)
	cfg := e.config(t, usb)
	a, err := New(cfg)
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()

	// BT-1: a run makes tagged snapshots readable with plain restic.
	run, err := a.Run(ctx, RunRequest{Reason: ReasonScheduled})
	if err != nil || run.State != StateSucceeded {
		t.Fatalf("run %+v %v", run, err)
	}
	repoPath := filepath.Join(usb.MountRoot, usb.USBUUID, "onemind-restic")
	var snaps []Snapshot
	if err := json.Unmarshal(resticDirect(t, e, repoPath, cfg.DeviceKeyFile, "snapshots", "--json"), &snaps); err != nil {
		t.Fatal(err)
	}
	if len(snaps) != 2 {
		t.Fatalf("plain restic sees %d snapshots", len(snaps))
	}
	for _, s := range snaps {
		for _, want := range []string{"onemind", "box=itbox", "gen=0", "node=itnode", "run=" + run.ID, "reason=scheduled", "keep=ladder"} {
			if !slices.Contains(s.Tags, want) {
				t.Errorf("snapshot %s lacks tag %s: %v", s.ShortID, want, s.Tags)
			}
		}
		if s.Hostname != "itnode" {
			t.Errorf("hostname %q", s.Hostname)
		}
	}

	// Excludes work and the tree lists direct children only.
	info, _ := a.ListSnapshots(ctx, "", "app:photos")
	photos := filepath.Join(e.root, "data/storage/photos")
	tree, err := a.Tree(ctx, "", info[0].ShortID, photos)
	if err != nil {
		t.Fatal(err)
	}
	var names []string
	for _, n := range tree {
		names = append(names, n.Name+":"+n.Type)
	}
	if strings.Join(names, ",") != "a.jpg:file,sub:dir" {
		t.Fatalf("tree = %v", names)
	}
	var buf bytes.Buffer
	if err := a.DumpFile(ctx, "", info[0].ID, filepath.Join(photos, "a.jpg"), &buf); err != nil || buf.String() != "photo-a" {
		t.Fatalf("dump %q %v", buf.String(), err)
	}

	// Rewind: restore one file with its mtime, then undo.
	mtime := time.Date(2025, 5, 6, 7, 8, 9, 0, time.UTC)
	file := filepath.Join(photos, "a.jpg")
	_ = os.Chtimes(file, mtime, mtime)
	if _, err := a.Run(ctx, RunRequest{Reason: ReasonManual, Units: []string{"app:photos"}}); err != nil {
		t.Fatal(err)
	}
	info, _ = a.ListSnapshots(ctx, "", "app:photos")
	e.write(t, "data/storage/photos/a.jpg", "changed")
	res, err := a.RestorePath(ctx, RestoreRequest{SnapshotID: info[0].ID, Path: file})
	if err != nil {
		t.Fatal(err)
	}
	got, _ := os.ReadFile(file)
	fi, _ := os.Stat(file)
	if string(got) != "photo-a" || !fi.ModTime().Equal(mtime) || res.PreRestoreSnapshotID == "" {
		t.Fatalf("restored %q mtime %v res %+v", got, fi.ModTime(), res)
	}
	if _, err := a.RestorePath(ctx, RestoreRequest{SnapshotID: res.PreRestoreSnapshotID, Path: file}); err != nil {
		t.Fatal(err)
	}
	if got, _ := os.ReadFile(file); string(got) != "changed" {
		t.Fatalf("undo gave %q", got)
	}
	// Directory restore over a changed directory.
	e.write(t, "data/storage/photos/sub/extra.jpg", "x")
	if _, err := a.RestorePath(ctx, RestoreRequest{SnapshotID: info[0].ID, Path: filepath.Join(photos, "sub")}); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(photos, "sub/extra.jpg")); !os.IsNotExist(err) {
		t.Fatal("directory restore kept a newer file")
	}
	if b, _ := os.ReadFile(filepath.Join(photos, "sub/b.jpg")); len(b) != 1<<20 {
		t.Fatalf("sub/b.jpg has %d bytes", len(b))
	}

	// Verified restore into scratch, for every unit.
	units, _ := a.Units(ctx)
	for _, u := range units {
		v, err := a.VerifyRestore(ctx, u, "")
		if err != nil || v.Verdict != VerdictPassed {
			t.Fatalf("verify %s: %+v %v", u.Name, v, err)
		}
	}
	if v, err := a.CheckRepo(ctx, ""); err != nil || v.Verdict != VerdictPassed {
		t.Fatalf("check %+v %v", v, err)
	}

	// Retention with --group-by '' is accepted by real restic and thins
	// the ladder: with hourly=1 and no other rules only the newest stays.
	a.Cfg.Retention = Retention{Hourly: 1}
	repo, _ := a.OpenRepo(usb)
	if err := a.forget(ctx, repo, "app:photos", "ladder"); err != nil {
		t.Fatalf("forget: %v", err)
	}
	if left, _ := repo.Snapshots(ctx, []string{"onemind", "unit=app:photos", "keep=ladder"}); len(left) != 1 {
		t.Fatalf("ladder kept %d snapshots", len(left))
	}
	if pre, _ := repo.Snapshots(ctx, []string{"onemind", "unit=app:photos", "keep=14d"}); len(pre) != 3 { // two file restores + one directory restore
		t.Fatalf("pre-restore snapshots touched by the ladder: %d left", len(pre))
	}
	if err := a.Prune(ctx, ""); err != nil {
		t.Fatal(err)
	}

	// BT-3 (part): an owner key added to the repository opens it alone.
	owner := filepath.Join(e.root, "secrets", "owner.key")
	if err := GenerateKey(owner); err != nil {
		t.Fatal(err)
	}
	if err := repo.AddKey(ctx, owner); err != nil {
		t.Fatal(err)
	}
	if out := resticDirect(t, e, repoPath, owner, "snapshots", "--tag", "onemind,unit=system"); !bytes.Contains(out, []byte("itnode")) {
		t.Fatalf("owner key listing: %s", out)
	}

	// BT-9: a restored box (generation 1) fences this one.
	cfg2 := cfg
	cfg2.Generation = 1
	cfg2.StateDir = filepath.Join(e.root, "state2")
	b, err := New(cfg2)
	if err != nil {
		t.Fatal(err)
	}
	if err := b.WriteFence(ctx, ""); err != nil {
		t.Fatal(err)
	}
	if r, _ := a.Run(ctx, RunRequest{Reason: ReasonScheduled}); r.State != StateRefused {
		t.Fatalf("replaced box still backs up: %+v", r)
	}
}

func TestIntegrationAppendOnlyNodeTarget(t *testing.T) {
	e := integrationEnv(t)
	if e.restServer == "" {
		t.Skip("ONEMIND_REST_SERVER not set")
	}
	e.seed(t)
	certFile, keyFile := selfSignedCert(t, e.root)
	data := filepath.Join(e.root, "rest")
	_ = os.MkdirAll(data, 0o700)
	sum := sha1.Sum([]byte("node-pw"))
	if err := os.WriteFile(filepath.Join(data, ".htpasswd"), []byte("itbox:{SHA}"+base64.StdEncoding.EncodeToString(sum[:])+"\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	l, _ := net.Listen("tcp", "127.0.0.1:0")
	addr := l.Addr().String()
	l.Close()
	srv := exec.Command(e.restServer, "--path", data, "--listen", addr, "--append-only", "--private-repos",
		"--tls", "--tls-cert", certFile, "--tls-key", keyFile)
	var srvLog bytes.Buffer
	srv.Stdout, srv.Stderr = &srvLog, &srvLog
	if err := srv.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = srv.Process.Kill(); _ = srv.Wait() })
	for i := 0; ; i++ {
		if c, err := net.Dial("tcp", addr); err == nil {
			c.Close()
			break
		}
		if i > 100 {
			t.Fatalf("rest-server did not start: %s", srvLog.String())
		}
		time.Sleep(50 * time.Millisecond)
	}

	pw := e.write(t, "secrets/node.pw", "node-pw")
	node := Target{ID: "peer", Kind: KindNode, Primary: true, URL: "https://" + addr + "/itbox/", CAFile: certFile,
		User: "itbox", PasswordFile: pw, AppendOnly: true}
	a, err := New(e.config(t, node))
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	for i := 0; i < 2; i++ {
		if r, err := a.Run(ctx, RunRequest{Reason: ReasonScheduled}); err != nil || r.State != StateSucceeded {
			t.Fatalf("run %d: %+v %v\n%s", i, r, err, srvLog.String())
		}
	}
	info, err := a.ListSnapshots(ctx, "", "app:photos")
	if err != nil || len(info) != 2 {
		t.Fatalf("list %v %v", info, err)
	}
	var buf bytes.Buffer
	if err := a.DumpFile(ctx, "", info[0].ID, filepath.Join(e.root, "data/storage/photos/a.jpg"), &buf); err != nil || buf.String() != "photo-a" {
		t.Fatalf("dump over rest: %q %v", buf.String(), err)
	}
	// BT-12 (source side): the server refuses deletes from the box.
	repo, _ := a.OpenRepo(node)
	a.Cfg.Retention = Retention{Hourly: 1}
	if err := a.forget(ctx, repo, "app:photos", "ladder"); err == nil {
		t.Fatal("append-only rest-server accepted a forget from the box")
	}
	if left, _ := repo.Snapshots(ctx, []string{"onemind", "unit=app:photos"}); len(left) != 2 {
		t.Fatalf("snapshots after refused forget: %d", len(left))
	}
	// Wrong password is refused, not silently re-initialised.
	bad := e.write(t, "secrets/bad.pw", "wrong")
	node.PasswordFile = bad
	rs, _ := NewRestic(&a.Cfg, node, nil)
	if err := rs.Init(ctx); err == nil {
		t.Fatal("wrong rest-server password accepted")
	}
}

func selfSignedCert(t *testing.T, dir string) (string, string) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	tmpl := &x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "onemind-it"},
		NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour),
		IPAddresses: []net.IP{net.ParseIP("127.0.0.1")}, KeyUsage: x509.KeyUsageDigitalSignature,
		ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}}
	der, err := x509.CreateCertificate(rand.Reader, tmpl, tmpl, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	kb, _ := x509.MarshalECPrivateKey(key)
	cert, kf := filepath.Join(dir, "tls.crt"), filepath.Join(dir, "tls.key")
	_ = os.WriteFile(cert, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}), 0o644)
	_ = os.WriteFile(kf, pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: kb}), 0o600)
	return cert, kf
}
