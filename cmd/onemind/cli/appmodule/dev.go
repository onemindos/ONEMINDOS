// SPDX-License-Identifier: Apache-2.0

package appmodule

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

// One sink may be shared by concurrent child processes (including piped CLI output).
type output struct {
	mu *sync.Mutex
	w  io.Writer
}

func (w output) Write(p []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	return w.w.Write(p)
}

// Dev runs both development servers with the real catalog, loopback transport, a dedicated
// SQLite database and the noop executor. Cancel the whole child group (make/uv and npm/vite).
func Dev(parent context.Context, directory string, stdout, stderr io.Writer) error {
	root, err := os.OpenRoot(directory)
	if err != nil {
		return err
	}
	defer root.Close()
	if err := checkRoot(root); err != nil {
		return err
	}
	dir, err := filepath.Abs(directory)
	if err != nil {
		return err
	}
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		return err
	}
	port := strconv.Itoa(listener.Addr().(*net.TCPAddr).Port)
	if err := listener.Close(); err != nil {
		return err
	}
	env := []string{
		"ONEMIND_HOST=127.0.0.1", "ONEMIND_PORT=" + port, "ONEMIND_EXECUTOR=noop", "ONEMIND_NATS_URL=",
		"ONEMIND_DATA_DIR=" + filepath.Join(dir, "core", "data", "app-dev"),
		"ONEMIND_APPS_DIR=" + filepath.Join(dir, "apps"),
		"ONEMIND_DASHBOARD_DIST=" + filepath.Join(dir, "dashboard", "dist"), "VITE_MOCK=0",
	}
	for _, s := range os.Environ() {
		if !strings.HasPrefix(s, "ONEMIND_") && !strings.HasPrefix(s, "VITE_") {
			env = append(env, s)
		}
	}
	ctx, stop := signal.NotifyContext(parent, os.Interrupt, syscall.SIGTERM)
	defer stop()
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	var mu sync.Mutex
	command := func(name string, args ...string) *exec.Cmd {
		cmd := exec.CommandContext(ctx, name, args...)
		cmd.Dir, cmd.Env = dir, env
		cmd.Stdout, cmd.Stderr = output{&mu, stdout}, output{&mu, stderr}
		setGroupCancel(cmd)
		cmd.WaitDelay = 2 * time.Second
		return cmd
	}
	if err := command("make", "-C", "sdk", "openapi", "gen-ts").Run(); err != nil {
		return fmt.Errorf("generate the module's public API: %w", err)
	}
	if _, err := root.Stat("dashboard/node_modules/.bin/vite"); errors.Is(err, os.ErrNotExist) {
		if err := command("npm", "--prefix", "dashboard", "ci").Run(); err != nil {
			return fmt.Errorf("install dashboard dependencies: %w", err)
		}
	} else if err != nil {
		return err
	}
	fmt.Fprintln(stdout, "For local sign-in, use the adult development credential in core/examples/tokens.example.yaml. Open the module in All screens and apps.")
	gateway := command("make", "-C", "core", "run")
	web := command("npm", "--prefix", "dashboard", "run", "dev", "--", "--config", "app-dev/vite.config.ts", "--host", "127.0.0.1")
	if err := gateway.Start(); err != nil {
		return err
	}
	if err := web.Start(); err != nil {
		cancel()
		_ = gateway.Wait()
		return err
	}
	done := make(chan error, 2)
	go func() { done <- gateway.Wait() }()
	go func() { done <- web.Wait() }()
	err = <-done
	cancel()
	<-done
	return err
}
