// SPDX-License-Identifier: Apache-2.0

package imagegc

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"path/filepath"
	"sort"
	"testing"
	"time"
)

// fakeBox is a k3s node with no internet: an image store, containers and the
// cluster's objects. Remove really removes; nothing can be pulled.
type fakeBox struct {
	images     map[string]Image
	containers map[string]bool
	objects    []map[string]any
	noCluster  bool
	failRemove map[string]bool
	removed    []string
}

func (f *fakeBox) Images(context.Context) ([]Image, error) {
	out := make([]Image, 0, len(f.images))
	for _, img := range f.images {
		out = append(out, img)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ID < out[j].ID })
	return out, nil
}

func (f *fakeBox) ContainerImages(context.Context) (map[string]bool, error) { return f.containers, nil }

func (f *fakeBox) Workloads(context.Context) ([]byte, error) {
	if f.noCluster {
		return nil, errors.New("kubectl: no kubeconfig on a worker")
	}
	return json.Marshal(map[string]any{"items": f.objects})
}

func (f *fakeBox) Remove(_ context.Context, id string) error {
	if f.failRemove[id] {
		return errors.New("image is in use")
	}
	delete(f.images, id)
	f.removed = append(f.removed, id)
	return nil
}

func tmpl(image string) map[string]any {
	return map[string]any{"spec": map[string]any{"containers": []any{map[string]any{"name": "main", "image": image}}}}
}

func workload(kind, ns, name string, replicas int, image string) map[string]any {
	return map[string]any{"kind": kind, "metadata": map[string]any{"name": name, "namespace": ns, "uid": ns + "/" + name},
		"spec": map[string]any{"replicas": replicas, "template": tmpl(image)}}
}

func replicaSet(ns, owner string, rev int, image string) map[string]any {
	return map[string]any{"kind": "ReplicaSet", "metadata": map[string]any{
		"name": owner + "-" + string(rune('a'+rev)), "namespace": ns,
		"annotations":     map[string]any{RevisionAnnotation: itoa(rev)},
		"ownerReferences": []any{map[string]any{"kind": "Deployment", "uid": ns + "/" + owner}},
	}, "spec": map[string]any{"replicas": 0, "template": tmpl(image)}}
}

func itoa(n int) string { b, _ := json.Marshal(n); return string(b) }

func img(id, ref string, size int64) Image {
	return Image{ID: id, RepoDigests: []string{ref}, Size: size}
}

const (
	photos2 = "ghcr.io/acme/photos:2.0@sha256:p2"
	photos1 = "ghcr.io/acme/photos:1.9@sha256:p1"
	photos0 = "ghcr.io/acme/photos:1.8@sha256:p0"
	notes14 = "docker.io/notes/server:1.4@sha256:n14"
	pg16    = "postgres:16@sha256:pg16"
)

// newOfflineBox: photos runs (revision 3, with revisions 2 and 1 in its history),
// notes and its database are installed but stopped (replicas 0, no container),
// plus the system's own images.
func newOfflineBox() *fakeBox {
	return &fakeBox{
		images: map[string]Image{
			"sha256:i-p2":    img("sha256:i-p2", "ghcr.io/acme/photos@sha256:p2", 300),
			"sha256:i-p1":    img("sha256:i-p1", "ghcr.io/acme/photos@sha256:p1", 290),
			"sha256:i-p0":    img("sha256:i-p0", "ghcr.io/acme/photos@sha256:p0", 280),
			"sha256:i-n14":   img("sha256:i-n14", "docker.io/notes/server@sha256:n14", 100),
			"sha256:i-n13":   img("sha256:i-n13", "docker.io/notes/server@sha256:n13", 90),
			"sha256:i-pg16":  img("sha256:i-pg16", "docker.io/library/postgres@sha256:pg16", 400),
			"sha256:i-pause": {ID: "sha256:i-pause", RepoTags: []string{"docker.io/rancher/mirrored-pause:3.6"}, Size: 1, Pinned: true},
			"sha256:i-dns":   {ID: "sha256:i-dns", RepoTags: []string{"docker.io/rancher/mirrored-coredns-coredns:1.12.0"}, Size: 20},
			"sha256:i-helm":  {ID: "sha256:i-helm", RepoTags: []string{"docker.io/rancher/klipper-helm:v0.9.3"}, Size: 50},
		},
		containers: map[string]bool{"sha256:i-p2": true, "sha256:i-dns": true, "sha256:i-pause": true},
		objects: []map[string]any{
			workload("Deployment", "app-photos", "photos", 1, photos2),
			replicaSet("app-photos", "photos", 3, photos2),
			replicaSet("app-photos", "photos", 2, photos1),
			replicaSet("app-photos", "photos", 1, photos0),
			workload("Deployment", "app-notes", "notes", 0, notes14),
			replicaSet("app-notes", "notes", 1, notes14),
			workload("StatefulSet", "app-notes", "notes-db", 0, pg16),
			workload("Deployment", "kube-system", "coredns", 1, "rancher/mirrored-coredns-coredns:1.12.0"),
		},
	}
}

// restartOffline starts every installed app's workloads (and rolls each back
// one revision) with no network: each image must already be in the store. It
// returns what could not start.
func restartOffline(box *fakeBox) []string {
	var stranded []string
	store, _ := box.Images(context.Background())
	need := map[string]string{}
	for _, o := range box.objects {
		ns, _ := o["metadata"].(map[string]any)["namespace"].(string)
		if ns == "kube-system" {
			continue
		}
		for _, ref := range podImages(o) {
			if o["kind"] == "ReplicaSet" && ref == photos0 {
				continue // three revisions back: rollout undo goes one back
			}
			need[ref] = ns
		}
	}
	for ref, ns := range need {
		found := false
		for _, im := range store {
			if ParseRef(ref).Matches(im) {
				found = true
			}
		}
		if !found {
			stranded = append(stranded, ns+" needs "+ref)
		}
	}
	sort.Strings(stranded)
	return stranded
}

// Done when (#133): an offline box restarts every installed app after cleanup.
func TestOfflineBoxRestartsEveryInstalledAppAfterCleanup(t *testing.T) {
	box := newOfflineBox()
	c := New(box, Config{}, nil)
	res := c.Clean(context.Background())
	if res.Outcome != "succeeded" {
		t.Fatalf("outcome %s: %s", res.Outcome, res.Reason)
	}
	sort.Strings(box.removed)
	if got := box.removed; len(got) != 2 || got[0] != "sha256:i-n13" || got[1] != "sha256:i-p0" {
		t.Fatalf("removed %v, want only the superseded notes 1.3 and photos 1.8", got)
	}
	if res.Freed != 370 {
		t.Fatalf("freed %d", res.Freed)
	}
	for _, keep := range []string{"sha256:i-pause", "sha256:i-dns", "sha256:i-helm", "sha256:i-n14", "sha256:i-pg16", "sha256:i-p1", "sha256:i-p2"} {
		if _, ok := box.images[keep]; !ok {
			t.Errorf("%s was removed", keep)
		}
	}
	if stranded := restartOffline(box); len(stranded) > 0 {
		t.Fatalf("offline box cannot start (images removed, no network to pull): %v", stranded)
	}
	r := c.Report()
	if r.LastResult != "succeeded" || r.LastRemoved != 2 || r.LastFreedBytes != 370 || r.Count != 7 || r.SupersededBytes != 0 {
		t.Fatalf("report %+v", r)
	}
}

// What the cleaner exists to avoid: kubelet-style "remove every image no
// container uses" deletes the stopped apps' images, and the offline box can no
// longer start them. The test proves restartOffline would catch it.
func TestUnusedImagePruneWouldStrandStoppedApps(t *testing.T) {
	box := newOfflineBox()
	for id, im := range box.images {
		if !box.containers[id] && !im.Pinned {
			delete(box.images, id)
		}
	}
	if stranded := restartOffline(box); len(stranded) != 3 {
		t.Fatal("a naive unused-image prune left the stopped apps startable; the offline check proves nothing")
	}
}

func TestNoClusterNoDeletion(t *testing.T) {
	box := newOfflineBox()
	box.noCluster = true
	c := New(box, Config{}, nil)
	res := c.Clean(context.Background())
	if res.Outcome != "skipped" || len(box.removed) != 0 {
		t.Fatalf("outcome %s removed %v", res.Outcome, box.removed)
	}
	if r := c.Report(); r.LastResult != "skipped" || r.Count != 9 {
		t.Fatalf("report %+v", r)
	}
	if d := Plan(nil, nil, nil); len(d.Prune) != 0 {
		t.Fatal("empty plan pruned")
	}
	box.noCluster, box.objects = false, nil // an empty cluster is no evidence either
	if res := New(box, Config{}, nil).Clean(context.Background()); len(res.Removed) != 0 {
		t.Fatalf("empty cluster removed %v", res.Removed)
	}
}

func TestRemoveFailureIsPartial(t *testing.T) {
	box := newOfflineBox()
	box.failRemove = map[string]bool{"sha256:i-n13": true}
	c := New(box, Config{}, nil)
	res := c.Clean(context.Background())
	if res.Outcome != "partial" || len(res.Removed) != 1 || res.Reason == "" {
		t.Fatalf("%+v", res)
	}
	if r := c.Report(); r.SupersededBytes != 90 || r.Count != 8 {
		t.Fatalf("report %+v", r)
	}
}

func TestParseRef(t *testing.T) {
	for in, want := range map[string]Ref{
		"nginx":                            {"docker.io/library/nginx", "latest", ""},
		"nginx:1.27":                       {"docker.io/library/nginx", "1.27", ""},
		"bitnami/redis:7@sha256:ab":        {"docker.io/bitnami/redis", "7", "sha256:ab"},
		"ghcr.io/a/b@sha256:cd":            {"ghcr.io/a/b", "", "sha256:cd"},
		"localhost:5000/x":                 {"localhost:5000/x", "latest", ""},
		"localhost/x:dev":                  {"localhost/x", "dev", ""},
		"docker.io/library/postgres:16":    {"docker.io/library/postgres", "16", ""},
		"docker.io/redis:7":                {"docker.io/library/redis", "7", ""},
		"index.docker.io/bitnami/redis:7":  {"docker.io/bitnami/redis", "7", ""},
		"registry.example:443/team/app:v2": {"registry.example:443/team/app", "v2", ""},
	} {
		if got := ParseRef(in); got != want {
			t.Errorf("ParseRef(%q) = %+v, want %+v", in, got, want)
		}
	}
}

// Two apps name one Docker Hub repository in two spellings ("docker.io/redis"
// and "redis"): the stopped app's version is still wanted, not superseded.
func TestDockerHubSpellingsAreOneRepository(t *testing.T) {
	images := []Image{
		{ID: "sha256:r70", RepoTags: []string{"docker.io/library/redis:7.0"}, Size: 10},
		{ID: "sha256:r72", RepoTags: []string{"docker.io/library/redis:7.2"}, Size: 10},
		{ID: "sha256:r60", RepoTags: []string{"docker.io/library/redis:6.0"}, Size: 10},
	}
	d := Plan(images, []string{"docker.io/redis:7.0", "redis:7.2"}, map[string]bool{"sha256:r72": true})
	if len(d.Prune) != 1 || d.Prune[0].ID != "sha256:r60" {
		t.Fatalf("pruned %+v, want only the superseded redis 6.0", d.Prune)
	}
}

func TestWantedKeepsCurrentAndPreviousRevision(t *testing.T) {
	box := newOfflineBox()
	cr := map[string]any{"kind": "ControllerRevision", "revision": 4.0, "metadata": map[string]any{
		"ownerReferences": []any{map[string]any{"uid": "app-notes/notes-db"}}}, "data": map[string]any{"spec": map[string]any{"template": tmpl("postgres:15@sha256:pg15")}}}
	cron := map[string]any{"kind": "CronJob", "spec": map[string]any{"jobTemplate": map[string]any{"spec": map[string]any{"template": map[string]any{
		"spec": map[string]any{"initContainers": []any{map[string]any{"image": "busybox:1.36"}}}}}}}}
	list, _ := json.Marshal(map[string]any{"items": append(box.objects, cr, cron)})
	got, err := Wanted(list)
	if err != nil {
		t.Fatal(err)
	}
	set := map[string]bool{}
	for _, r := range got {
		set[r] = true
	}
	for _, r := range []string{photos2, photos1, notes14, pg16, "postgres:15@sha256:pg15", "busybox:1.36"} {
		if !set[r] {
			t.Errorf("missing %s in %v", r, got)
		}
	}
	if set[photos0] {
		t.Errorf("revision 1 of 3 is not wanted: %v", got)
	}
	if _, err := Wanted([]byte("not json")); err == nil {
		t.Fatal("bad list accepted")
	}
}

func TestParseCrictl(t *testing.T) {
	imgs, err := ParseImages([]byte(`{"images":[{"id":"sha256:a","repoTags":["docker.io/x/y:1"],"repoDigests":[],"size":"1234","pinned":true}]}`))
	if err != nil || len(imgs) != 1 || imgs[0].Size != 1234 || !imgs[0].Pinned {
		t.Fatalf("%+v %v", imgs, err)
	}
	used, err := ParseContainers([]byte(`{"containers":[{"image":{"image":"sha256:a"},"imageRef":"docker.io/x/y@sha256:b"}]}`))
	if err != nil || !used["sha256:a"] || !used["docker.io/x/y@sha256:b"] {
		t.Fatalf("%v %v", used, err)
	}
	// A container naming its image by reference keeps it.
	d := Plan([]Image{img("sha256:z", "docker.io/x/y@sha256:b", 1)}, []string{"docker.io/x/y:2"}, used)
	if len(d.Prune) != 0 {
		t.Fatalf("pruned an image a container uses: %+v", d.Prune)
	}
}

func TestConfigAndReportFile(t *testing.T) {
	c := Config{}.Defaults()
	if c.BudgetPct != 80 || c.WarnPct != 70 || c.Every != 24*time.Hour {
		t.Fatalf("%+v", c)
	}
	if c := (Config{BudgetPct: 90, WarnPct: 95}).Defaults(); c.WarnPct != 80 {
		t.Fatalf("warn above budget kept: %+v", c)
	}
	t.Setenv("ONEMIND_IMAGES_BUDGET_PCT", "60")
	if c := ConfigFromEnv(); c.BudgetPct != 60 || c.WarnPct != 50 {
		t.Fatalf("%+v", c)
	}
	p := filepath.Join(t.TempDir(), "report.json")
	if ReadReport(p) != nil {
		t.Fatal("report from nowhere")
	}
	cl := New(newOfflineBox(), Config{}, func() (float64, bool) { return 83.4, true })
	cl.Clean(context.Background())
	if err := WriteReport(p, cl.Report()); err != nil {
		t.Fatal(err)
	}
	r := ReadReport(p)
	if r == nil || r.DiskUsedPct != 83.4 || r.BudgetPct != 80 || r.LastResult != "succeeded" || r.LastCleanupAt == nil {
		t.Fatalf("%+v", r)
	}
	if !cl.OverBudget() {
		t.Fatal("83.4 % is past an 80 % budget")
	}
}

func TestRunCleansAtStartAndPublishes(t *testing.T) {
	box := newOfflineBox()
	c := New(box, Config{Check: time.Millisecond}, func() (float64, bool) { return 10, true })
	ctx, cancel := context.WithCancel(context.Background())
	var got []*Report
	done := make(chan error, 1)
	go func() {
		done <- c.Run(ctx, slog.New(slog.NewTextHandler(io.Discard, nil)), func(r *Report) error {
			got = append(got, r)
			if len(got) == 3 {
				cancel()
			}
			return nil
		})
	}()
	if err := <-done; err != nil {
		t.Fatal(err)
	}
	if len(box.removed) != 2 || got[0].LastResult != "succeeded" || got[0].DiskUsedPct != 10 {
		t.Fatalf("removed %v first report %+v", box.removed, got[0])
	}
}
