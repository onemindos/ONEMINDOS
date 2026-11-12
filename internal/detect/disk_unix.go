//go:build unix

package detect

import (
	"os"
	"syscall"
)

var readFile = os.ReadFile

// statfs returns total and available bytes of the filesystem holding path.
func statfs(path string) (total, free uint64, err error) {
	var st syscall.Statfs_t
	if err := syscall.Statfs(path, &st); err != nil {
		return 0, 0, err
	}
	bs := uint64(st.Bsize) //nolint:unconvert // int64 on linux, uint32 on darwin
	return st.Blocks * bs, st.Bavail * bs, nil
}
