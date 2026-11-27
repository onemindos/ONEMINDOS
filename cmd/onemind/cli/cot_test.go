// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"os"
	"strings"
	"testing"

	"github.com/onemindos/onemindos/internal/cot"
)

func TestCoTValidate(t *testing.T) {
	valid, err := os.ReadFile("../../../internal/cot/testdata/sa-team-member.xml")
	if err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct {
		name, input string
		code        int
		output      string
	}{
		{"valid", string(valid), ExitOK, `"valid": true`},
		{"malformed", "<event", ExitVerifyFailed, `"error":"cot_invalid"`},
		{"oversized", strings.Repeat(" ", cot.MaxEventBytes+1), ExitVerifyFailed, cot.ErrTooLarge.Error()},
	} {
		t.Run(tc.name, func(t *testing.T) {
			var stdout, stderr bytes.Buffer
			code := Run([]string{"cot", "validate", "--json"}, Env{
				Stdout: &stdout, Stderr: &stderr, Stdin: strings.NewReader(tc.input),
			})
			if code != tc.code {
				t.Fatalf("exit code = %d, want %d; stderr: %s", code, tc.code, &stderr)
			}
			output, other := &stdout, &stderr
			if code != ExitOK {
				output, other = other, output
			}
			if !strings.Contains(output.String(), tc.output) || other.Len() != 0 {
				t.Fatalf("wanted %q; stdout: %q, stderr: %q", tc.output, &stdout, &stderr)
			}
		})
	}
}
