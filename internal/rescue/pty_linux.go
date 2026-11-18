// SPDX-License-Identifier: Apache-2.0

//go:build linux

package rescue

import (
	"fmt"
	"os"
	"os/exec"
	"sync"
	"syscall"

	"golang.org/x/sys/unix"
)

// PTY starts a login-less shell on a pseudo-terminal. No new dependency: the
// pty is opened with /dev/ptmx and two ioctls (x/sys/unix is already used).
type PTY struct {
	Shell string   // default /bin/sh
	Env   []string // default: a minimal environment
}

type ptySession struct {
	master *os.File
	cmd    *exec.Cmd
	done   chan struct{}
	once   sync.Once
}

// Spawn implements Spawner.
func (p PTY) Spawn() (Session, error) {
	m, err := os.OpenFile("/dev/ptmx", os.O_RDWR|unix.O_NOCTTY|unix.O_CLOEXEC, 0)
	if err != nil {
		return nil, fmt.Errorf("open /dev/ptmx: %w", err)
	}
	fail := func(e error) (Session, error) { _ = m.Close(); return nil, e }
	n, err := unix.IoctlGetInt(int(m.Fd()), unix.TIOCGPTN)
	if err != nil {
		return fail(err)
	}
	if err := unix.IoctlSetPointerInt(int(m.Fd()), unix.TIOCSPTLCK, 0); err != nil {
		return fail(err)
	}
	_ = unix.IoctlSetWinsize(int(m.Fd()), unix.TIOCSWINSZ, &unix.Winsize{Row: 30, Col: 110})
	slave, err := os.OpenFile(fmt.Sprintf("/dev/pts/%d", n), os.O_RDWR|unix.O_NOCTTY, 0)
	if err != nil {
		return fail(err)
	}
	defer slave.Close()
	shell := p.Shell
	if shell == "" {
		shell = "/bin/sh"
	}
	env := p.Env
	if env == nil {
		env = []string{"TERM=dumb", "HOME=/root", "PATH=/usr/sbin:/usr/bin:/sbin:/bin", "PS1=rescue# "}
	}
	cmd := exec.Command(shell)
	cmd.Env = env
	cmd.Stdin, cmd.Stdout, cmd.Stderr = slave, slave, slave
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true, Setctty: true, Ctty: 0}
	if err := cmd.Start(); err != nil {
		return fail(err)
	}
	s := &ptySession{master: m, cmd: cmd, done: make(chan struct{})}
	go func() { _ = cmd.Wait(); close(s.done) }()
	return s, nil
}

func (s *ptySession) Read(b []byte) (int, error)  { return s.master.Read(b) }
func (s *ptySession) Write(b []byte) (int, error) { return s.master.Write(b) }
func (s *ptySession) Done() <-chan struct{}       { return s.done }

// Close hangs the shell up: the whole session (process group) gets SIGHUP, then SIGKILL.
func (s *ptySession) Close() error {
	s.once.Do(func() {
		if s.cmd.Process != nil {
			_ = syscall.Kill(-s.cmd.Process.Pid, syscall.SIGHUP)
			_ = syscall.Kill(-s.cmd.Process.Pid, syscall.SIGKILL)
		}
		_ = s.master.Close()
	})
	return nil
}
