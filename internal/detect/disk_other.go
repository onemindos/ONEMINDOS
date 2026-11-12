//go:build !unix

package detect

import (
	"errors"
	"os"
)

var readFile = os.ReadFile

func statfs(string) (uint64, uint64, error) { return 0, 0, errors.New("statfs unsupported") }
