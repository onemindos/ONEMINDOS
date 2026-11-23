// SPDX-License-Identifier: Apache-2.0

package rescue

import (
	"net/http"
	"os"
	"path"
	"strings"
)

// The offline help pack (#504, FD-07): plain HTML pages with no JavaScript, shipped read-only in the image
// at DefaultHelpDir. The rescue console serves the same pack under /help/ so the owner can read the
// recovery steps when k3s and the gateway are down. It sits behind the same LAN and owner check as every
// other page here (ServeHTTP runs before the mux), and it only ever reads files: no listing, no upload.

// DefaultHelpDir is where the image installs the pack (os/rootfs/layers/onemind/usr/share/onemind/help).
const DefaultHelpDir = "/usr/share/onemind/help"

// MaxHelpFileBytes bounds one served file; the pack is a few small pages.
const MaxHelpFileBytes = 4 << 20

// helpCSP has no script-src, so nothing in the pack can run script even if a page carried some.
const helpCSP = "default-src 'none'; style-src 'self'; img-src 'self'; form-action 'none'; " +
	"frame-ancestors 'none'; base-uri 'none'"

// helpTypes is the only file kinds the pack may hold. Everything else (scripts included) is a 404.
var helpTypes = map[string]string{
	".html": "text/html; charset=utf-8",
	".css":  "text/css; charset=utf-8",
	".txt":  "text/plain; charset=utf-8",
	".svg":  "image/svg+xml",
	".png":  "image/png",
	".jpg":  "image/jpeg",
	".webp": "image/webp",
}

// helpFile opens a pack file inside HelpDir. os.Root refuses "..", absolute paths and symlinks that leave
// the directory, so nothing outside the pack can be read through it.
func (s *Server) helpFile(rel string) (*os.File, os.FileInfo, bool) {
	if s.cfg.HelpDir == "" {
		return nil, nil, false
	}
	root, err := os.OpenRoot(s.cfg.HelpDir)
	if err != nil {
		return nil, nil, false
	}
	defer root.Close()
	f, err := root.Open(rel)
	if err != nil {
		return nil, nil, false
	}
	fi, err := f.Stat()
	if err != nil || !fi.Mode().IsRegular() || fi.Size() > MaxHelpFileBytes {
		_ = f.Close()
		return nil, nil, false
	}
	return f, fi, true
}

// hasHelp reports whether a pack with an index page is installed, so the console links to it.
func (s *Server) hasHelp() bool {
	f, _, ok := s.helpFile("index.html")
	if ok {
		_ = f.Close()
	}
	return ok
}

func (s *Server) help(w http.ResponseWriter, r *http.Request) {
	rel := r.PathValue("path")
	if rel == "" || strings.HasSuffix(rel, "/") {
		rel += "index.html" // a folder shows its index page, never a listing
	}
	ctype, allowed := helpTypes[strings.ToLower(path.Ext(rel))]
	if !allowed {
		http.NotFound(w, r)
		return
	}
	f, fi, ok := s.helpFile(rel)
	if !ok {
		if rel == "index.html" {
			http.Error(w, "no offline help pack is installed on this box", http.StatusNotFound)
			return
		}
		http.NotFound(w, r)
		return
	}
	defer f.Close()
	h := w.Header()
	h.Set("Content-Type", ctype)
	h.Set("Content-Security-Policy", helpCSP)
	http.ServeContent(w, r, "", fi.ModTime(), f)
}
