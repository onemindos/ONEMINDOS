// SPDX-License-Identifier: Apache-2.0

// Package imagegc is the offline-aware image cleanup and disk budget of a box
// (NMD-08, #133).
//
// The lesson it encodes (Project NOMAD #858): old container images filled a
// 64 GB SSD, and a careless prune deleted images that an offline box needed to
// start its apps again. Kubernetes' own image garbage collection removes every
// image no running container uses, which on OneMind includes the images of a
// stopped app (app.stop scales its workloads to zero). A box with no internet
// then cannot start that app again.
//
// So this cleaner removes only *superseded* images: an image whose repository
// an app still uses, but at a version no workload, recent revision or
// container refers to any more. Everything else stays:
//
//   - every image a workload's pod template names, at any replica count, so a
//     stopped app restarts offline;
//   - the images of the previous revision of every workload, so the gateway's
//     health-gated update can `kubectl rollout undo` without a download;
//   - every image a container (running or exited) uses;
//   - images the runtime pins (the pod sandbox image);
//   - images of repositories no workload uses at all (system and air-gap
//     images, a removed app): not ours to judge.
//
// The cleanup runs on the node as root (it needs the container runtime), once
// a day and at once when the disk passes the box's budget, before kubelet's
// own collector (85 % by default) would start removing stopped apps' images.
// It is deterministic housekeeping, not an AI decision; it never removes an
// app, a volume or data.
package imagegc

import (
	"encoding/json"
	"sort"
	"strconv"
	"strings"
)

// Image is one image in the container runtime's store (`crictl images -o json`).
type Image struct {
	ID          string   `json:"id"`
	RepoTags    []string `json:"repoTags"`
	RepoDigests []string `json:"repoDigests"`
	Size        int64    `json:"size,string"`
	Pinned      bool     `json:"pinned"`
}

// Ref is a parsed image reference: repository (registry/path), tag, digest.
type Ref struct {
	Repo, Tag, Digest string
}

// ParseRef normalises an image reference the way the container runtime does:
// a bare name gets docker.io (and library/ for one path segment), a missing tag
// and digest means :latest.
func ParseRef(s string) Ref {
	s = strings.TrimSpace(s)
	var r Ref
	if i := strings.Index(s, "@"); i >= 0 {
		s, r.Digest = s[:i], s[i+1:]
	}
	if i := strings.LastIndex(s, ":"); i > strings.LastIndex(s, "/") {
		s, r.Tag = s[:i], s[i+1:]
	}
	parts := strings.Split(s, "/")
	if (parts[0] == "docker.io" || parts[0] == "index.docker.io") && len(parts) > 1 {
		// An explicit Docker Hub name is the same repository as the bare one: the
		// runtime stores "docker.io/redis" as docker.io/library/redis. Without
		// this, two spellings of one image look like two repositories and a
		// stopped app's image could be judged superseded.
		parts = parts[1:]
	}
	first := parts[0]
	if len(parts) == 1 || (!strings.ContainsAny(first, ".:") && first != "localhost") {
		if len(parts) == 1 {
			parts = append([]string{"library"}, parts...)
		}
		parts = append([]string{"docker.io"}, parts...)
	}
	r.Repo = strings.Join(parts, "/")
	if r.Tag == "" && r.Digest == "" {
		r.Tag = "latest"
	}
	return r
}

// Matches reports whether img is the image this reference names.
func (r Ref) Matches(img Image) bool {
	if r.Digest != "" {
		for _, d := range img.RepoDigests {
			if p := ParseRef(d); p.Repo == r.Repo && p.Digest == r.Digest {
				return true
			}
		}
		return img.ID == r.Digest // an image may be named by its id
	}
	for _, t := range img.RepoTags {
		if p := ParseRef(t); p.Repo == r.Repo && p.Tag == r.Tag {
			return true
		}
	}
	return false
}

// Repos returns the repositories the image is known under.
func (img Image) Repos() []string {
	var out []string
	for _, s := range append(append([]string{}, img.RepoTags...), img.RepoDigests...) {
		out = append(out, ParseRef(s).Repo)
	}
	return out
}

// Decision is what Plan decided about the store.
type Decision struct {
	Keep  []Image
	Prune []Image
}

// PruneBytes is the space the prune list frees.
func (d Decision) PruneBytes() int64 {
	var n int64
	for _, img := range d.Prune {
		n += img.Size
	}
	return n
}

// Plan splits the image store into what stays and what is superseded. wanted
// are the references the cluster still needs (Wanted), inUse the image ids (or
// references) of every container, running or exited. With no wanted references at all (the
// cluster could not be read, or it is empty) nothing is pruned: no evidence,
// no deletion.
func Plan(images []Image, wanted []string, inUse map[string]bool) Decision {
	refs := make([]Ref, 0, len(wanted))
	repos := map[string]bool{}
	for _, w := range wanted {
		r := ParseRef(w)
		refs = append(refs, r)
		repos[r.Repo] = true
	}
	var d Decision
	for _, img := range images {
		if len(refs) == 0 || img.Pinned || used(img, inUse) || !anyRepo(img, repos) || anyMatch(refs, img) {
			d.Keep = append(d.Keep, img)
			continue
		}
		d.Prune = append(d.Prune, img)
	}
	return d
}

// used: a container names its image by id or (crictl's imageRef) by one of its references.
func used(img Image, inUse map[string]bool) bool {
	if inUse[img.ID] {
		return true
	}
	for _, r := range append(append([]string{}, img.RepoDigests...), img.RepoTags...) {
		if inUse[r] {
			return true
		}
	}
	return false
}

func anyRepo(img Image, repos map[string]bool) bool {
	for _, r := range img.Repos() {
		if repos[r] {
			return true
		}
	}
	return false
}

func anyMatch(refs []Ref, img Image) bool {
	for _, r := range refs {
		if r.Matches(img) {
			return true
		}
	}
	return false
}

// RevisionAnnotation is the Deployment revision a ReplicaSet carries.
const RevisionAnnotation = "deployment.kubernetes.io/revision"

// Wanted returns every image reference the cluster still needs, from a
// `kubectl get ... -A -o json` list: the pod templates of all workloads
// (replicas zero included), pods, and the newest two revisions (current and
// previous) of every ReplicaSet and ControllerRevision owner.
func Wanted(list []byte) ([]string, error) {
	var doc struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(list, &doc); err != nil {
		return nil, err
	}
	type rev struct {
		n    int
		refs []string
	}
	byOwner := map[string][]rev{}
	seen := map[string]bool{}
	var out []string
	add := func(refs []string) {
		for _, r := range refs {
			if r != "" && !seen[r] {
				seen[r] = true
				out = append(out, r)
			}
		}
	}
	for _, it := range doc.Items {
		kind, _ := it["kind"].(string)
		md, _ := it["metadata"].(map[string]any)
		switch kind {
		case "ReplicaSet", "ControllerRevision":
			owner := ownerUID(md)
			n := revision(kind, it, md)
			refs := podImages(it)
			if owner == "" { // a bare ReplicaSet is a workload of its own
				add(refs)
				continue
			}
			byOwner[owner] = append(byOwner[owner], rev{n, refs})
		default:
			add(podImages(it))
		}
	}
	owners := make([]string, 0, len(byOwner))
	for o := range byOwner {
		owners = append(owners, o)
	}
	sort.Strings(owners)
	for _, o := range owners {
		revs := byOwner[o]
		sort.SliceStable(revs, func(i, j int) bool { return revs[i].n > revs[j].n })
		for i := 0; i < len(revs) && i < 2; i++ {
			add(revs[i].refs)
		}
	}
	return out, nil
}

func ownerUID(md map[string]any) string {
	refs, _ := md["ownerReferences"].([]any)
	for _, r := range refs {
		if m, ok := r.(map[string]any); ok {
			if uid, _ := m["uid"].(string); uid != "" {
				return uid
			}
		}
	}
	return ""
}

func revision(kind string, it, md map[string]any) int {
	if kind == "ControllerRevision" {
		if f, ok := it["revision"].(float64); ok {
			return int(f)
		}
		return 0
	}
	ann, _ := md["annotations"].(map[string]any)
	s, _ := ann[RevisionAnnotation].(string)
	n, _ := strconv.Atoi(s)
	return n
}

// podImages walks an object for container lists ("containers",
// "initContainers", "ephemeralContainers") at any depth: pod specs, pod
// templates, CronJob job templates and ControllerRevision data alike.
func podImages(v any) []string {
	var out []string
	var walk func(any)
	walk = func(v any) {
		switch x := v.(type) {
		case map[string]any:
			for k, child := range x {
				if k == "containers" || k == "initContainers" || k == "ephemeralContainers" {
					if list, ok := child.([]any); ok {
						for _, c := range list {
							if m, ok := c.(map[string]any); ok {
								if img, _ := m["image"].(string); img != "" {
									out = append(out, img)
								}
							}
						}
						continue
					}
				}
				walk(child)
			}
		case []any:
			for _, child := range x {
				walk(child)
			}
		}
	}
	walk(v)
	sort.Strings(out)
	return out
}
