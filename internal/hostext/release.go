// SPDX-License-Identifier: Apache-2.0

package hostext

// The extension-release check. systemd-sysext(8) merges an image only when its extension-release
// ID matches the host's os-release ID (or is "_any"), its SYSEXT_LEVEL matches (or, without one,
// VERSION_ID does) and its ARCHITECTURE, when set, matches the kernel's. OneMind is stricter:
// "_any" is refused and the level key must be present on both sides and equal, so an extension is
// built for exactly one OneMind extension level (SYSEXT_LEVEL; CONFEXT_LEVEL for a confext).

import (
	"bufio"
	"bytes"
	"os"
	"strings"
)

// parseOSRelease reads the os-release(5) KEY=VALUE format.
func parseOSRelease(b []byte) map[string]string {
	out := map[string]string{}
	sc := bufio.NewScanner(bytes.NewReader(b))
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		k, v, ok := strings.Cut(line, "=")
		if !ok || strings.HasPrefix(line, "#") {
			continue
		}
		if len(v) >= 2 && (v[0] == '"' || v[0] == '\'') && v[len(v)-1] == v[0] {
			v = v[1 : len(v)-1]
		}
		out[strings.TrimSpace(k)] = v
	}
	return out
}

func readHostRelease(paths []string) (map[string]string, error) {
	var err error
	for _, p := range paths {
		var b []byte
		if b, err = os.ReadFile(p); err == nil {
			return parseOSRelease(b), nil
		}
	}
	return nil, err
}

func levelKey(k Kind) string {
	if k == Confext {
		return "CONFEXT_LEVEL"
	}
	return "SYSEXT_LEVEL"
}

// checkRelease applies the OneMind rule to an extension's release fields.
func checkRelease(ext, host map[string]string, k Kind, arch string) error {
	if host["ID"] == "" || ext["ID"] != host["ID"] {
		return refuse("wrong_os", "the extension is for OS %q, this host is %q", ext["ID"], host["ID"])
	}
	key := levelKey(k)
	if host[key] == "" {
		return refuse("wrong_level", "this host declares no %s: host extensions are off", key)
	}
	if ext[key] != host[key] {
		return refuse("wrong_level", "the extension is for %s %q, this host is %q", key, ext[key], host[key])
	}
	if a := ext["ARCHITECTURE"]; a != "" && a != "_any" && a != arch {
		return refuse("wrong_arch", "the extension is for %s, this host is %s", a, arch)
	}
	return nil
}
