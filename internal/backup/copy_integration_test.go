// SPDX-License-Identifier: Apache-2.0

//go:build integration

package backup

import (
	"bytes"
	"context"
	"errors"
	"io"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/minio/minio-go/v7"
)

func TestIntegrationSovereignCopies(t *testing.T) {
	if os.Getenv("ONEMIND_RESTIC") == "" {
		t.Fatal("ONEMIND_RESTIC is required for the sovereign copy integration test")
	}
	for _, kind := range []string{KindUSB, KindS3} {
		t.Run(kind, func(t *testing.T) {
			e := integrationEnv(t)
			e.seed(t)
			tgt := Target{ID: "owner-target", Kind: kind, Primary: true, Sovereign: true}
			switch kind {
			case KindUSB:
				tgt.USBUUID, tgt.MountRoot, tgt.AllowNonMountDir = "owner-nas", e.root, true
				if err := os.Mkdir(filepath.Join(tgt.MountRoot, tgt.USBUUID), 0o700); err != nil {
					t.Fatal(err)
				}
			case KindS3:
				tgt.Endpoint, tgt.Bucket = os.Getenv("ONEMIND_COPY_S3_ENDPOINT"), os.Getenv("ONEMIND_COPY_S3_BUCKET")
				tgt.AccessKeyFile, tgt.SecretKeyFile = os.Getenv("ONEMIND_COPY_S3_ACCESS_FILE"), os.Getenv("ONEMIND_COPY_S3_SECRET_FILE")
				tgt.Region, tgt.Prefix = "us-east-1", "owner-prefix"
			}
			cfg := e.config(t, tgt)
			cfg.Restic.SkipPinCheck = false
			cfg.Retention = Retention{Hourly: 1}
			a, err := New(cfg)
			if err != nil {
				t.Fatal(err)
			}
			ctx := context.Background()
			if kind == KindS3 {
				store, err := a.openCopyStore(tgt, cfg.BoxID, true)
				if err != nil {
					t.Fatal(err)
				}
				if err := store.(s3CopyStore).client.MakeBucket(ctx, tgt.Bucket, minio.MakeBucketOptions{}); err != nil {
					t.Fatal(err)
				}
			}
			const ownerKey = "test-only-owner-repository-passphrase"
			source := a
			job := func(p copyJob) any {
				t.Helper()
				v, err := a.sovereignCopy(ctx, p)
				if err != nil {
					t.Fatalf("%s: %v", p.Operation, err)
				}
				return v
			}
			run, err := a.Run(ctx, RunRequest{Reason: ReasonScheduled})
			if err != nil || run.State != StateSucceeded {
				t.Fatalf("backup: %v (%+v)", err, run)
			}
			var ids []string
			for _, unit := range run.Units {
				ids = append(ids, unit.SnapshotID)
			}
			p := copyJob{Operation: "prepare", TargetID: tgt.ID, BoxID: cfg.BoxID, RunID: run.ID, Snapshots: ids}
			point := job(p).(copyBackup)
			if len(point.Snapshots) != len(ids) || !fullID(point.Repository) {
				t.Fatalf("prepare did not confirm both units in this repository: %+v", point)
			}

			p.Operation, p.RecoveryKey, p.Repository = "publish", ownerKey, point.Repository
			p.CopyID = strings.Repeat("1", 32)
			p.Bundle, p.Record = []byte("encrypted octets"), []byte("signed completion bytes")
			if _, err := a.sovereignCopy(ctx, p); err == nil {
				t.Fatal("publication installed a key without the attachment flag")
			}
			p.AttachRecoveryKey = true
			job(p)
			job(p) // safe retry with identical bytes
			if _, err := a.AddKey(ctx, "additional-test-passphrase"); err != nil {
				t.Fatal(err)
			}
			original := p
			p.Record = []byte("different completion bytes")
			if _, err := a.sovereignCopy(ctx, p); err == nil {
				t.Fatal("an existing completion record was overwritten")
			}
			p = original
			p.Bundle = []byte("different encrypted octets")
			if _, err := a.sovereignCopy(ctx, p); err == nil {
				t.Fatal("a published bundle was overwritten")
			}

			store, err := a.openCopyStore(tgt, cfg.BoxID, true)
			if err != nil {
				t.Fatal(err)
			}
			// A crash after the bundle write leaves no discoverable completion.
			if err := store.put(ctx, strings.Repeat("2", 32)+"/box.omb", []byte("partial copy")); err != nil {
				t.Fatal(err)
			}
			store.close()
			p = original
			p.Operation = "list"
			if got := job(p).([]string); !slices.Equal(got, []string{p.CopyID}) {
				t.Fatalf("list = %v", got)
			}
			p.Operation = "record"
			if !bytes.Equal(job(p).([]byte), p.Record) {
				t.Fatal("published record changed")
			}
			p.Operation = "bundle"
			if !bytes.Equal(job(p).([]byte), p.Bundle) {
				t.Fatal("published bundle changed")
			}

			stamp := time.Now().Add(2 * time.Hour)
			a.Now = func() time.Time { return stamp }
			e.write(t, "data/storage/photos/a.jpg", "later")
			next, err := a.Run(ctx, RunRequest{Reason: ReasonScheduled})
			if err != nil || next.State != StateSucceeded {
				t.Fatalf("second backup: %v (%+v)", err, next)
			}
			if err := a.Prune(ctx, tgt.ID); !errors.Is(err, errSovereignRetention) {
				t.Fatalf("sovereign prune: %v", err)
			}

			// Use a different box/device key to prove recovery needs only the
			// original box ID, owner kit and access to this one destination.
			fresh := cfg
			fresh.BoxID = "new-box"
			fresh.StateDir = filepath.Join(e.root, "fresh")
			fresh.DeviceKeyFile = filepath.Join(e.root, "secrets", "new-device.key")
			if err := GenerateKey(fresh.DeviceKeyFile); err != nil {
				t.Fatal(err)
			}
			a, err = New(fresh)
			if err != nil {
				t.Fatal(err)
			}
			p.Operation = "check"
			job(p)
			p.RecoveryKey = "different-password"
			if _, err := a.sovereignCopy(ctx, p); err == nil {
				t.Fatal("check accepted the wrong recovery key")
			}
			p.RecoveryKey = ownerKey
			p.Repository = strings.Repeat("0", 64)
			if _, err := a.sovereignCopy(ctx, p); err == nil {
				t.Fatal("check accepted another repository identity")
			}
			p.Repository = point.Repository
			p.Snapshots = append(ids, strings.Repeat("a", 64))
			if _, err := a.sovereignCopy(ctx, p); err == nil {
				t.Fatal("check accepted a missing snapshot")
			}
			p.Snapshots = ids
			snapshots, err := a.ListSnapshotsOfBox(ctx, tgt.ID, cfg.BoxID, "", ownerKey)
			if err != nil || len(snapshots) != 4 {
				t.Fatalf("original box snapshots after retention = %d (%v)", len(snapshots), err)
			}
			if kind == KindUSB {
				repo := filepath.Join(tgt.MountRoot, tgt.USBUUID, "boxes", cfg.BoxID, "data")
				// The same files must remain usable by stock restic directly on the
				// mounted destination, without passing through the daemon.
				var restored bytes.Buffer
				stderr, _, err := (ExecRunner{}).Run(ctx, cfg.Restic.Binary, []string{"--no-cache", "--no-lock", "dump", ids[0], "/"},
					[]string{"RESTIC_REPOSITORY=" + repo, "RESTIC_PASSWORD=" + ownerKey}, nil, &restored)
				if err != nil || restored.Len() == 0 {
					t.Fatalf("stock restic could not read the NAS copy with the existing kit: %v (%s)", err, stderr)
				}
				testNASKeyDirectory(t, source, repo, e.root)
				cached, err := NewRestic(&cfg, tgt, nil)
				if err != nil {
					t.Fatal(err)
				}
				cached.useRecoveryKey(ownerKey)
				warm := func() {
					t.Helper()
					for _, id := range ids {
						if err := cached.Dump(ctx, id, "/", io.Discard); err != nil {
							t.Fatalf("expected a cached dump to succeed: %v", err)
						}
					}
				}
				warm()
				cachedPacks, err := filepath.Glob(filepath.Join(cfg.Restic.CacheDir, point.Repository, "data", "*", "*"))
				if err != nil || len(cachedPacks) == 0 {
					t.Fatalf("expected restic to cache metadata packs: %v", err)
				}
				for _, pack := range cachedPacks {
					name := filepath.Base(pack)
					damagePack(t, filepath.Join(repo, "data", name[:2], name))
				}
				warm() // metadata is still sound in the cache alone
				t.Run("warm-cache-discovery", func(t *testing.T) {
					if _, err := a.sovereignCopy(ctx, p); err == nil || !strings.Contains(err.Error(), "data check") {
						t.Fatalf("discovery should reject destination damage with a warm cache: %v", err)
					}
				})
				t.Run("warm-cache-publication", func(t *testing.T) {
					publication := original
					publication.CopyID = strings.Repeat("3", 32)
					if _, err := source.sovereignCopy(ctx, publication); err == nil || !strings.Contains(err.Error(), "data check") {
						t.Fatalf("publication should reject destination damage with a warm cache: %v", err)
					}
				})
				if got := job(copyJob{Operation: "list", TargetID: tgt.ID, BoxID: cfg.BoxID}).([]string); !slices.Equal(got, []string{original.CopyID}) {
					t.Fatalf("the damaged copy was published: %v", got)
				}
				packs, err := filepath.Glob(filepath.Join(repo, "data", "*", "*"))
				if err != nil || len(packs) == 0 {
					t.Fatalf("expected real restic data packs: %v", err)
				}
				// Damage every pack so the required snapshots exist but cannot be read.
				for _, pack := range packs {
					damagePack(t, pack)
				}
				if _, err := a.sovereignCopy(ctx, p); err == nil {
					t.Fatal("check accepted damaged snapshot data")
				}
			}
		})
	}
}

func damagePack(t *testing.T, pack string) {
	t.Helper()
	if err := os.Chmod(pack, 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(pack, []byte("damaged pack"), 0o600); err != nil {
		t.Fatal(err)
	}
}

func testNASKeyDirectory(t *testing.T, a *Agent, repo, outside string) {
	t.Helper()
	keys := filepath.Join(repo, "keys")
	external := filepath.Join(outside, "external-keys")
	if err := os.Rename(keys, external); err != nil {
		t.Fatal(err)
	}
	defer func() {
		if err := errors.Join(os.Remove(keys), os.Rename(external, keys)); err != nil {
			t.Error(err)
		}
	}()
	if err := os.Symlink(external, keys); err != nil {
		t.Fatal(err)
	}
	before, err := os.ReadDir(external)
	if err != nil {
		t.Fatal(err)
	}
	_, addErr := a.AddKey(context.Background(), "nas-symlink-test-passphrase")
	after, err := os.ReadDir(external)
	if err != nil || len(before) != len(after) || addErr == nil {
		t.Fatalf("restic followed the repository's keys symlink: key add %v, outside entries %d -> %d, read %v",
			addErr, len(before), len(after), err)
	}
}
