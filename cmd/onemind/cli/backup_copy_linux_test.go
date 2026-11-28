// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"io"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/spf13/cobra"
	"golang.org/x/sys/unix"
)

func TestSovereignCopyTerminalDoesNotEcho(t *testing.T) {
	for _, prompt := range []string{"Recovery key", "S3 credentials JSON"} {
		t.Run(prompt, func(t *testing.T) {
			master, err := os.OpenFile("/dev/ptmx", os.O_RDWR|unix.O_NOCTTY|unix.O_NONBLOCK, 0)
			if err != nil {
				t.Fatal(err)
			}
			defer master.Close()
			masterFD := int(master.Fd())
			if err := unix.SetNonblock(masterFD, true); err != nil {
				t.Fatal(err)
			}
			if err := unix.IoctlSetPointerInt(masterFD, unix.TIOCSPTLCK, 0); err != nil {
				t.Fatal(err)
			}
			n, err := unix.IoctlGetInt(masterFD, unix.TIOCGPTN)
			if err != nil {
				t.Fatal(err)
			}
			slave, err := os.OpenFile(fmt.Sprintf("/dev/pts/%d", n), os.O_RDWR|unix.O_NOCTTY, 0)
			if err != nil {
				t.Fatal(err)
			}
			defer slave.Close()
			slaveFD := int(slave.Fd())
			settings, err := unix.IoctlGetTermios(slaveFD, unix.TCGETS)
			if err != nil || settings.Lflag&unix.ECHO == 0 {
				t.Fatalf("expected an echoing terminal before the prompt: %v", err)
			}
			_, app := NewRoot(Env{Stdin: slave, Stderr: io.Discard})
			secret := "synthetic-input-for-terminal-test"
			result := make(chan error, 1)
			go func() {
				got, err := readCopySecret(&cobra.Command{}, app, prompt, 256)
				if err == nil && string(got) != secret {
					err = fmt.Errorf("the terminal reader did not return the input")
				}
				result <- err
			}()
			deadline := time.Now().Add(2 * time.Second)
			for settings.Lflag&unix.ECHO != 0 && time.Now().Before(deadline) {
				time.Sleep(time.Millisecond)
				settings, err = unix.IoctlGetTermios(slaveFD, unix.TCGETS)
				if err != nil {
					t.Fatal(err)
				}
			}
			if settings.Lflag&unix.ECHO != 0 {
				t.Fatal("the credential prompt left terminal echo enabled")
			}
			if _, err := master.WriteString(secret + "\n"); err != nil {
				t.Fatal(err)
			}
			select {
			case err := <-result:
				if err != nil {
					t.Fatal(err)
				}
			case <-time.After(2 * time.Second):
				t.Fatal("credential prompt did not read the terminal input")
			}
			var echoed [256]byte
			n, err = unix.Read(masterFD, echoed[:])
			if err != nil && err != unix.EAGAIN {
				t.Fatal(err)
			}
			if n > 0 && strings.Contains(string(echoed[:n]), secret) {
				t.Fatal("terminal echoed the credential")
			}
			settings, err = unix.IoctlGetTermios(slaveFD, unix.TCGETS)
			if err != nil || settings.Lflag&unix.ECHO == 0 {
				t.Fatalf("the credential reader did not restore terminal echo: %v", err)
			}
		})
	}
}
