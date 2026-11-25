// SPDX-License-Identifier: Apache-2.0

// Package svcregistry reads the services registry the image ships (/usr/lib/onemind/services.yaml,
// #623) and joins it with what systemd says about each unit, for the host service's GET /v1/services.
// The gateway serves the result as GET /v1/system/services; `onemind services list` prints it.
//
// Trust: the file is on the read-only, signed OS image, so only an OS update changes it. It is still
// checked here: owned by root, not writable by group or others, valid against the published contract
// (sdk/schema/onemind.services.schema.json). A file that fails a check is not used, and every
// OneMind unit then shows as unknown, which the screen and the CLI flag. Nothing here changes a unit:
// the only systemctl verbs used are `show` and `list-unit-files`.
package svcregistry

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/santhosh-tekuri/jsonschema/v6"
	"gopkg.in/yaml.v3"

	"github.com/onemindos/onemindos/sdk/schema"
)

// DefaultPath is where the image puts the registry (os/rootfs/layers/onemind).
const DefaultPath = "/usr/lib/onemind/services.yaml"

// Schema names the host's answer.
const Schema = "onemind.host.services/v1"

// MaxBytes caps the registry file.
const MaxBytes = 256 << 10

// Registry states in View.Registry.
const (
	RegistryOK      = "ok"
	RegistryMissing = "missing"
	RegistryInvalid = "invalid"
)

// unitRE is the contract's unit pattern; every name passed to systemctl matches it.
var unitRE = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.@-]{0,90}\.(service|socket|timer|path)$`)

// Entry is one registry entry (the contract's $defs/service).
type Entry struct {
	Unit        string   `json:"unit"`
	Name        string   `json:"name"`
	Description string   `json:"description"`
	Docs        string   `json:"docs"`
	Restartable bool     `json:"restartable"`
	Risk        string   `json:"risk"`
	DependsOn   []string `json:"depends_on"`
}

// Registry is services.yaml.
type Registry struct {
	Schema   string  `json:"schema"`
	Services []Entry `json:"services"`
}

var contract = sync.OnceValues(func() (*jsonschema.Schema, error) {
	doc, err := jsonschema.UnmarshalJSON(strings.NewReader(schema.Services))
	if err != nil {
		return nil, err
	}
	c := jsonschema.NewCompiler()
	const loc = "https://onemind.invalid/services"
	if err := c.AddResource(loc, doc); err != nil {
		return nil, err
	}
	return c.Compile(loc)
})

// Parse checks a registry document against the contract and returns it.
func Parse(data []byte) (*Registry, error) {
	if len(data) > MaxBytes {
		return nil, fmt.Errorf("registry is larger than %d bytes", MaxBytes)
	}
	var doc any
	if err := yaml.Unmarshal(data, &doc); err != nil {
		return nil, fmt.Errorf("registry is not YAML: %w", err)
	}
	raw, err := json.Marshal(doc) // YAML maps decode with string keys in yaml.v3
	if err != nil {
		return nil, fmt.Errorf("registry: %w", err)
	}
	inst, err := jsonschema.UnmarshalJSON(bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}
	s, err := contract()
	if err != nil {
		return nil, err
	}
	if err := s.Validate(inst); err != nil {
		return nil, fmt.Errorf("registry breaks the contract: %w", err)
	}
	var r Registry
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&r); err != nil {
		return nil, err
	}
	seen := map[string]bool{}
	for _, e := range r.Services {
		if seen[e.Unit] {
			return nil, fmt.Errorf("registry lists %s twice", e.Unit)
		}
		seen[e.Unit] = true
	}
	return &r, nil
}

// Load reads and checks the file at path. fs.ErrNotExist means the image has none.
func Load(path string) (*Registry, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	st, err := f.Stat()
	if err != nil {
		return nil, err
	}
	if !st.Mode().IsRegular() || st.Mode().Perm()&0o022 != 0 {
		return nil, fmt.Errorf("%s must be a regular file nobody but its owner can write", path)
	}
	if sys, ok := st.Sys().(*syscall.Stat_t); ok && sys.Uid != 0 && os.Getuid() == 0 {
		return nil, fmt.Errorf("%s must be owned by root", path)
	}
	data, err := readCapped(f)
	if err != nil {
		return nil, err
	}
	return Parse(data)
}

func readCapped(f *os.File) ([]byte, error) {
	var b bytes.Buffer
	n, err := b.ReadFrom(&limited{f, MaxBytes + 1})
	if err != nil {
		return nil, err
	}
	if n > MaxBytes {
		return nil, fmt.Errorf("registry is larger than %d bytes", MaxBytes)
	}
	return b.Bytes(), nil
}

type limited struct {
	f *os.File
	n int64
}

func (l *limited) Read(p []byte) (int, error) {
	if l.n <= 0 {
		return 0, errors.New("too large")
	}
	if int64(len(p)) > l.n {
		p = p[:l.n]
	}
	n, err := l.f.Read(p)
	l.n -= int64(n)
	return n, err
}

// Card is one unit on the service cards: the registry's words plus systemd's state.
type Card struct {
	Entry
	Known       bool    `json:"known"`
	Installed   bool    `json:"installed"`
	LoadState   *string `json:"load_state"`
	ActiveState *string `json:"active_state"`
	SubState    *string `json:"sub_state"`
	MemoryBytes *int64  `json:"memory_bytes"`
	Version     *string `json:"version"`
}

// View is the host's GET /v1/services.
type View struct {
	Schema        string    `json:"schema"`
	Registry      string    `json:"registry"`
	RegistryError *string   `json:"registry_error"`
	At            time.Time `json:"at"`
	Services      []Card    `json:"services"`
}

// Runner runs systemctl with args and returns its standard output.
type Runner func(ctx context.Context, args ...string) ([]byte, error)

// Systemctl runs the real systemctl, read-only verbs only.
func Systemctl(ctx context.Context, args ...string) ([]byte, error) {
	if len(args) == 0 || (args[0] != "show" && args[0] != "list-unit-files") {
		return nil, fmt.Errorf("systemctl %v is not a read", args)
	}
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	var out bytes.Buffer
	cmd := exec.CommandContext(ctx, "systemctl", args...)
	cmd.Stdout = &limitedWriter{&out, 1 << 20}
	err := cmd.Run()
	return out.Bytes(), err
}

type limitedWriter struct {
	b *bytes.Buffer
	n int
}

func (w *limitedWriter) Write(p []byte) (int, error) {
	if room := w.n - w.b.Len(); room < len(p) {
		if room > 0 {
			w.b.Write(p[:room])
		}
		return len(p), nil
	}
	return w.b.Write(p)
}

// Reader builds the view.
type Reader struct {
	Path    string // DefaultPath when empty
	Run     Runner // Systemctl when nil
	Version string // the OneMind release of this image (internal/version)
	Now     func() time.Time
	// Restarter restarts a unit (SystemctlRestart when nil); Journal reads the journal (Journalctl when
	// nil). Both are used only by Restart and Logs (actions.go), never by Collect.
	Restarter func(ctx context.Context, unit string) error
	Journal   func(ctx context.Context, args []string, w io.Writer) error
}

// Collect reads the registry and systemd. Units named onemind* that the registry does not list come
// back with known=false. An error means systemd could not be asked at all.
func (r *Reader) Collect(ctx context.Context) (View, error) {
	path, run, now := r.Path, r.Run, r.Now
	if path == "" {
		path = DefaultPath
	}
	if run == nil {
		run = Systemctl
	}
	if now == nil {
		now = time.Now
	}
	v := View{Schema: Schema, Registry: RegistryOK, At: now().UTC(), Services: []Card{}}
	reg, err := Load(path)
	switch {
	case errors.Is(err, fs.ErrNotExist):
		v.Registry, reg = RegistryMissing, &Registry{}
	case err != nil:
		msg := err.Error()
		if len(msg) > 300 {
			msg = msg[:300]
		}
		v.Registry, v.RegistryError, reg = RegistryInvalid, &msg, &Registry{}
	}
	known := map[string]bool{}
	names := []string{}
	for _, e := range reg.Services {
		known[e.Unit] = true
		names = append(names, e.Unit)
	}
	files, err := run(ctx, "list-unit-files", "--no-legend", "--no-pager", "--plain", "onemind*")
	if err != nil && len(bytes.TrimSpace(files)) > 0 { // exit 1 with no output: no unit matched
		return View{}, fmt.Errorf("systemctl list-unit-files: %w", err)
	}
	extra := []string{}
	for _, line := range strings.Split(string(files), "\n") {
		f := strings.Fields(line)
		if len(f) > 0 && unitRE.MatchString(f[0]) && !known[f[0]] {
			known[f[0]] = false
			extra = append(extra, f[0])
		}
	}
	sort.Strings(extra)
	states, err := show(ctx, run, append(append([]string{}, names...), extra...))
	if err != nil {
		return View{}, err
	}
	version := &r.Version
	if r.Version == "" {
		version = nil
	}
	card := func(e Entry, isKnown bool) Card {
		c := Card{Entry: e, Known: isKnown}
		c.Restartable = c.Restartable && !NeverRestart(e.Unit) // rescue, first-boot, host, data layout: never a button
		if c.DependsOn == nil {
			c.DependsOn = []string{}
		}
		if st, ok := states[e.Unit]; ok {
			c.LoadState, c.ActiveState, c.SubState, c.MemoryBytes = st.load, st.active, st.sub, st.mem
			c.Installed = st.load != nil && *st.load != "not-found"
		}
		if isKnown && c.Installed {
			c.Version = version
		}
		return c
	}
	for _, e := range reg.Services {
		v.Services = append(v.Services, card(e, true))
	}
	for _, u := range extra {
		v.Services = append(v.Services, card(Entry{Unit: u, Name: u, Risk: "unknown"}, false))
	}
	return v, nil
}

type unitState struct {
	load, active, sub *string
	mem               *int64
}

var stateRE = regexp.MustCompile(`^[a-z-]{1,32}$`)

// show asks systemd for each unit's state. Template units (name@.service) are not instances, so they
// are not asked about and stay not installed.
func show(ctx context.Context, run Runner, units []string) (map[string]unitState, error) {
	ask := []string{}
	for _, u := range units {
		if unitRE.MatchString(u) && !strings.Contains(u, "@.") {
			ask = append(ask, u)
		}
	}
	out := map[string]unitState{}
	if len(ask) == 0 {
		return out, nil
	}
	args := append([]string{"show", "--no-pager", "--property=Id,LoadState,ActiveState,SubState,MemoryCurrent", "--"}, ask...)
	raw, err := run(ctx, args...)
	if err != nil {
		return nil, fmt.Errorf("systemctl show: %w", err)
	}
	// One block per unit, in the order asked, separated by blank lines.
	i := 0
	cur := map[string]string{}
	flush := func() {
		if len(cur) == 0 {
			return
		}
		name := cur["Id"]
		if i < len(ask) && (name == "" || name != ask[i]) {
			name = ask[i] // an alias resolves to another Id; keep the name that was asked
		}
		i++
		if name != "" {
			st := unitState{load: state(cur["LoadState"]), active: state(cur["ActiveState"]), sub: state(cur["SubState"])}
			if n, err := strconv.ParseInt(cur["MemoryCurrent"], 10, 64); err == nil && n >= 0 && n < 1<<50 {
				st.mem = &n
			}
			out[name] = st
		}
		cur = map[string]string{}
	}
	sc := bufio.NewScanner(bytes.NewReader(raw))
	for sc.Scan() {
		line := sc.Text()
		if strings.TrimSpace(line) == "" {
			flush()
			continue
		}
		if k, val, ok := strings.Cut(line, "="); ok {
			cur[k] = val
		}
	}
	flush()
	return out, nil
}

func state(s string) *string {
	if !stateRE.MatchString(s) {
		return nil
	}
	return &s
}
