// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

// Repo is one restic repository as the agent uses it. *Restic implements it
// by running the pinned restic binary; tests use an in-memory fake.
type Repo interface {
	// Init creates the repository with the device key unless it exists.
	Init(ctx context.Context) error
	Backup(ctx context.Context, req BackupRequest) (BackupResult, error)
	// BackupStdin stores r as one file (fence records).
	BackupStdin(ctx context.Context, filename string, r io.Reader, tags []string, host string) (BackupResult, error)
	// Snapshots lists snapshots carrying every tag in filter.
	Snapshots(ctx context.Context, filter []string) ([]Snapshot, error)
	// Forget applies keep rules to the snapshots carrying every tag in filter,
	// treated as one group. It never prunes.
	Forget(ctx context.Context, filter []string, keep []string) error
	Prune(ctx context.Context) error
	// Check verifies the repository, reading readDataSubset ("n/m") of the data.
	Check(ctx context.Context, readDataSubset string) error
	// Ls lists dir in the snapshot: its direct children, or everything below
	// it when recursive. dir "/" means the whole snapshot.
	Ls(ctx context.Context, snapshotID, dir string, recursive bool) ([]Node, error)
	// Dump writes the content of one file of the snapshot to w.
	Dump(ctx context.Context, snapshotID, path string, w io.Writer) error
	// Restore restores subPath ("/" = everything) of the snapshot into
	// target. With subPath "/" files land at target/<absolute path>; with a
	// directory subPath its contents land directly in target.
	Restore(ctx context.Context, snapshotID, subPath, target string) error
	// AddKey adds the key in newKeyFile (owner recovery, escrow, rotation).
	AddKey(ctx context.Context, newKeyFile string) error
}

// BackupRequest is one `restic backup`.
type BackupRequest struct {
	Paths    []string
	Excludes []string
	Tags     []string
	Host     string
}

// BackupResult is the summary restic prints at the end of a backup.
type BackupResult struct {
	SnapshotID string `json:"snapshot_id"`
	DataAdded  int64  `json:"data_added"`
	TotalBytes int64  `json:"total_bytes_processed"`
	// Incomplete is set when restic made the snapshot but could not read
	// some source files (exit code 3).
	Incomplete bool `json:"-"`
}

// Snapshot is one entry of `restic snapshots --json`.
type Snapshot struct {
	ID       string    `json:"id"`
	ShortID  string    `json:"short_id"`
	Time     time.Time `json:"time"`
	Hostname string    `json:"hostname"`
	Paths    []string  `json:"paths"`
	Tags     []string  `json:"tags"`
}

// Tag returns the value of the key=value tag, or "".
func (s Snapshot) Tag(key string) string {
	for _, t := range s.Tags {
		if k, v, ok := strings.Cut(t, "="); ok && k == key {
			return v
		}
	}
	return ""
}

// Node is one entry of `restic ls --json`.
type Node struct {
	Name  string      `json:"name"`
	Type  string      `json:"type"` // file, dir, symlink, ...
	Path  string      `json:"path"`
	Size  int64       `json:"size"`
	Mode  os.FileMode `json:"mode"`
	Mtime time.Time   `json:"mtime"`
}

// Runner starts a subprocess. The real one is ExecRunner; tests script it.
type Runner interface {
	Run(ctx context.Context, bin string, args, env []string, stdin io.Reader, stdout io.Writer) (stderr []byte, exitCode int, err error)
}

// ExecRunner runs commands with os/exec.
type ExecRunner struct{}

// Run implements Runner. exitCode is -1 when the command did not start.
func (ExecRunner) Run(ctx context.Context, bin string, args, env []string, stdin io.Reader, stdout io.Writer) ([]byte, int, error) {
	cmd := exec.CommandContext(ctx, bin, args...)
	cmd.Env = env
	cmd.Stdin = stdin
	cmd.Stdout = stdout
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	err := cmd.Run()
	var ee *exec.ExitError
	if errors.As(err, &ee) {
		return stderr.Bytes(), ee.ExitCode(), err
	}
	if err != nil {
		return stderr.Bytes(), -1, err
	}
	return stderr.Bytes(), 0, nil
}

// restic exit codes (restic docs, "Exit status codes", v0.17+).
const (
	exitIncomplete = 3  // backup: snapshot made, some files unreadable
	exitNoRepo     = 10 // repository does not exist
	exitLocked     = 11
	exitWrongKey   = 12
)

// Restic is a Repo backed by the restic binary.
type Restic struct {
	Binary  string
	KeyFile string // RESTIC_PASSWORD_FILE
	Repo    string // repository string (local path, rest:..., s3:...)
	Env     []string
	Flags   []string // global flags such as --cacert
	Runner  Runner
}

// NewRestic builds the client for target t. Credentials are read from their
// files into the child's environment only, never onto the command line, so
// they do not show up in process listings or logs.
func NewRestic(c *Config, t Target, r Runner) (*Restic, error) {
	if r == nil {
		r = ExecRunner{}
	}
	env := []string{"PATH=/usr/sbin:/usr/bin:/sbin:/bin", "RESTIC_PROGRESS_FPS=0.016"}
	rs := &Restic{Binary: c.Restic.Binary, KeyFile: c.DeviceKeyFile, Runner: r}
	if c.Restic.CacheDir != "" {
		env = append(env, "RESTIC_CACHE_DIR="+c.Restic.CacheDir)
	} else {
		rs.Flags = append(rs.Flags, "--no-cache")
	}
	if tmp := os.Getenv("TMPDIR"); tmp != "" {
		env = append(env, "TMPDIR="+tmp)
	}
	switch t.Kind {
	case KindUSB:
		mount := filepath.Join(t.MountRoot, t.USBUUID)
		rs.Repo = filepath.Join(mount, "onemind-restic")
	case KindNode:
		pw, err := readSecret(t.PasswordFile)
		if err != nil {
			return nil, err
		}
		rs.Repo = "rest:" + t.URL
		env = append(env, "RESTIC_REST_USERNAME="+t.User, "RESTIC_REST_PASSWORD="+pw)
		if t.CAFile != "" {
			rs.Flags = append(rs.Flags, "--cacert", t.CAFile)
		}
	case KindS3:
		ak, err := readSecret(t.AccessKeyFile)
		if err != nil {
			return nil, err
		}
		sk, err := readSecret(t.SecretKeyFile)
		if err != nil {
			return nil, err
		}
		rs.Repo = "s3:" + strings.TrimSuffix(t.Endpoint, "/") + "/" + t.Bucket
		if p := strings.Trim(t.Prefix, "/"); p != "" {
			rs.Repo += "/" + p
		}
		env = append(env, "AWS_ACCESS_KEY_ID="+ak, "AWS_SECRET_ACCESS_KEY="+sk)
		if t.Region != "" {
			env = append(env, "AWS_DEFAULT_REGION="+t.Region)
		}
	default:
		return nil, fmt.Errorf("unknown target kind %q", t.Kind)
	}
	rs.Env = append(env, "RESTIC_REPOSITORY="+rs.Repo, "RESTIC_PASSWORD_FILE="+c.DeviceKeyFile)
	return rs, nil
}

func readSecret(path string) (string, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("read secret: %w", err)
	}
	s := strings.TrimRight(string(b), "\r\n")
	if s == "" {
		return "", fmt.Errorf("secret file %s is empty", path)
	}
	return s, nil
}

// ResticError is a failed restic command. Stderr is the last line only:
// restic does not print secrets, but output is kept short for the ledger.
type ResticError struct {
	Op       string
	ExitCode int
	Stderr   string
}

func (e *ResticError) Error() string {
	return fmt.Sprintf("restic %s: exit %d: %s", e.Op, e.ExitCode, e.Stderr)
}

// IsLocked reports whether err is restic failing to lock the repository.
func IsLocked(err error) bool {
	var re *ResticError
	return errors.As(err, &re) && re.ExitCode == exitLocked
}

func (r *Restic) run(ctx context.Context, op string, stdin io.Reader, stdout io.Writer, args ...string) (int, error) {
	full := append(append([]string{}, r.Flags...), args...)
	stderr, code, err := r.Runner.Run(ctx, r.Binary, full, r.Env, stdin, stdout)
	if err != nil {
		if ctx.Err() != nil {
			return code, ctx.Err()
		}
		return code, &ResticError{Op: op, ExitCode: code, Stderr: lastLine(stderr)}
	}
	return 0, nil
}

func (r *Restic) output(ctx context.Context, op string, args ...string) ([]byte, error) {
	var out bytes.Buffer
	_, err := r.run(ctx, op, nil, &out, args...)
	return out.Bytes(), err
}

// Init implements Repo.
func (r *Restic) Init(ctx context.Context) error {
	_, err := r.output(ctx, "cat config", "cat", "config")
	if err == nil {
		return nil
	}
	var re *ResticError
	if !errors.As(err, &re) || re.ExitCode != exitNoRepo {
		return err
	}
	_, err = r.output(ctx, "init", "init")
	return err
}

// Backup implements Repo.
func (r *Restic) Backup(ctx context.Context, req BackupRequest) (BackupResult, error) {
	args := []string{"backup", "--json", "--host", req.Host}
	for _, t := range req.Tags {
		args = append(args, "--tag", t)
	}
	for _, e := range req.Excludes {
		args = append(args, "--exclude", e)
	}
	args = append(args, "--")
	args = append(args, req.Paths...)
	return r.backup(ctx, nil, args)
}

// BackupStdin implements Repo.
func (r *Restic) BackupStdin(ctx context.Context, filename string, in io.Reader, tags []string, host string) (BackupResult, error) {
	args := []string{"backup", "--json", "--host", host, "--stdin", "--stdin-filename", filename}
	for _, t := range tags {
		args = append(args, "--tag", t)
	}
	return r.backup(ctx, in, args)
}

func (r *Restic) backup(ctx context.Context, in io.Reader, args []string) (BackupResult, error) {
	var out bytes.Buffer
	code, err := r.run(ctx, "backup", in, &out, args...)
	res, perr := parseBackupSummary(out.Bytes())
	if err != nil {
		if code == exitIncomplete && perr == nil {
			res.Incomplete = true
			return res, nil
		}
		return BackupResult{}, err
	}
	return res, perr
}

// parseBackupSummary finds the summary line of `restic backup --json`.
func parseBackupSummary(out []byte) (BackupResult, error) {
	sc := bufio.NewScanner(bytes.NewReader(out))
	sc.Buffer(make([]byte, 64<<10), 4<<20)
	for sc.Scan() {
		var m struct {
			MessageType string `json:"message_type"`
			BackupResult
		}
		if json.Unmarshal(sc.Bytes(), &m) == nil && m.MessageType == "summary" && m.SnapshotID != "" {
			return m.BackupResult, nil
		}
	}
	return BackupResult{}, fmt.Errorf("restic backup: no summary with snapshot_id in output")
}

// Snapshots implements Repo. A single --tag with a comma list means "all of
// these tags"; several --tag flags would mean "any of them".
func (r *Restic) Snapshots(ctx context.Context, filter []string) ([]Snapshot, error) {
	args := []string{"snapshots", "--json"}
	if len(filter) > 0 {
		args = append(args, "--tag", strings.Join(filter, ","))
	}
	out, err := r.output(ctx, "snapshots", args...)
	if err != nil {
		return nil, err
	}
	var s []Snapshot
	if err := json.Unmarshal(out, &s); err != nil {
		return nil, fmt.Errorf("restic snapshots: %w", err)
	}
	return s, nil
}

// Forget implements Repo.
func (r *Restic) Forget(ctx context.Context, filter []string, keep []string) error {
	if len(filter) == 0 {
		return fmt.Errorf("forget without a tag filter is refused")
	}
	args := append([]string{"forget", "--tag", strings.Join(filter, ","), "--group-by", ""}, keep...)
	_, err := r.output(ctx, "forget", args...)
	return err
}

// Prune implements Repo.
func (r *Restic) Prune(ctx context.Context) error {
	_, err := r.output(ctx, "prune", "prune")
	return err
}

// Check implements Repo.
func (r *Restic) Check(ctx context.Context, subset string) error {
	args := []string{"check"}
	if subset != "" {
		args = append(args, "--read-data-subset", subset)
	}
	_, err := r.output(ctx, "check", args...)
	return err
}

// Ls implements Repo.
func (r *Restic) Ls(ctx context.Context, id, dir string, recursive bool) ([]Node, error) {
	dir = cleanSnapPath(dir)
	args := []string{"ls", "--json", id}
	if dir != "/" {
		args = append(args, "--recursive", dir)
	}
	out, err := r.output(ctx, "ls", args...)
	if err != nil {
		return nil, err
	}
	return filterNodes(parseLs(out), dir, recursive), nil
}

func parseLs(out []byte) []Node {
	var nodes []Node
	sc := bufio.NewScanner(bytes.NewReader(out))
	sc.Buffer(make([]byte, 64<<10), 4<<20)
	for sc.Scan() {
		var m struct {
			StructType string `json:"struct_type"`
			Node
		}
		if json.Unmarshal(sc.Bytes(), &m) == nil && m.StructType == "node" {
			nodes = append(nodes, m.Node)
		}
	}
	return nodes
}

// filterNodes keeps the entries below dir (direct children only unless
// recursive). It does not rely on how restic interprets dir arguments.
func filterNodes(in []Node, dir string, recursive bool) []Node {
	var out []Node
	for _, n := range in {
		p := cleanSnapPath(n.Path)
		if p == dir || !isUnder(p, dir) {
			continue
		}
		if !recursive && pathDir(p) != dir {
			continue
		}
		out = append(out, n)
	}
	return out
}

// Dump implements Repo.
func (r *Restic) Dump(ctx context.Context, id, path string, w io.Writer) error {
	_, err := r.run(ctx, "dump", nil, w, "dump", "--", id, cleanSnapPath(path))
	return err
}

// Restore implements Repo.
func (r *Restic) Restore(ctx context.Context, id, subPath, target string) error {
	src := id
	if p := cleanSnapPath(subPath); p != "/" {
		src = id + ":" + p
	}
	_, err := r.output(ctx, "restore", "restore", "--target", target, "--", src)
	return err
}

// AddKey implements Repo.
func (r *Restic) AddKey(ctx context.Context, newKeyFile string) error {
	_, err := r.output(ctx, "key add", "key", "add", "--new-password-file", newKeyFile)
	return err
}

func lastLine(b []byte) string {
	s := strings.TrimSpace(string(b))
	if i := strings.LastIndexByte(s, '\n'); i >= 0 {
		s = s[i+1:]
	}
	if len(s) > 300 {
		s = s[:300]
	}
	return s
}

// cleanSnapPath normalises a path inside a snapshot: always absolute, '/'
// separated, no "..".
func cleanSnapPath(p string) string {
	p = filepath.ToSlash(filepath.Clean("/" + p))
	return p
}

func isUnder(p, dir string) bool {
	if dir == "/" {
		return strings.HasPrefix(p, "/")
	}
	return p == dir || strings.HasPrefix(p, dir+"/")
}

func pathDir(p string) string { return filepath.ToSlash(filepath.Dir(p)) }
