// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"net/http"

	"github.com/onemindos/onemindos/internal/flatpak"
)

// FlatpakManager is the desktop-apps side (internal/flatpak.Manager). Nil on a Service means the box has none:
// GET /v1/flatpak says so and the rest refuse.
type FlatpakManager interface {
	Unavailable() string
	Search(ctx context.Context, q string) ([]flatpak.App, error)
	Installed(ctx context.Context) ([]flatpak.App, error)
	Install(ctx context.Context, id string) error
	Update(ctx context.Context, id string) error
	Remove(ctx context.Context, id string) error
	Launch(ctx context.Context, id string) error
}

// flatpakRoutes adds the Flathub desktop-app calls (issue #1097). The gateway calls them only after an owner
// approved the install, update or removal (D-026, D-027); the host decides nothing itself.
//
//	GET    /v1/flatpak                       available, why not, installed apps
//	GET    /v1/flatpak/search?q=             Flathub apps matching q
//	POST   /v1/flatpak/apps/{id}/install     install and sandbox
//	POST   /v1/flatpak/apps/{id}/update      update and sandbox again
//	DELETE /v1/flatpak/apps/{id}             remove the app (its granted folder stays)
//	POST   /v1/flatpak/apps/{id}/launch      tell the streaming runtime to start it
func (s *Server) flatpakRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /v1/flatpak", func(w http.ResponseWriter, r *http.Request) {
		out := map[string]any{"available": false, "unavailable_reason": nil, "installed": []flatpak.App{}}
		switch why := s.flatpakWhy(); {
		case why != "":
			out["unavailable_reason"] = why
		default:
			apps, err := s.S.Flatpak.Installed(r.Context())
			if err != nil {
				s.flatpakError(w, "list", err)
				return
			}
			out["available"], out["installed"] = true, apps
		}
		writeJSON(w, http.StatusOK, out)
	})
	mux.HandleFunc("GET /v1/flatpak/search", func(w http.ResponseWriter, r *http.Request) {
		if !s.flatpakReady(w) {
			return
		}
		apps, err := s.S.Flatpak.Search(r.Context(), r.URL.Query().Get("q"))
		if err != nil {
			s.flatpakError(w, "search", err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"results": apps})
	})
	do := func(what string, f func(FlatpakManager, context.Context, string) error) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			if !s.flatpakReady(w) {
				return
			}
			if err := f(s.S.Flatpak, r.Context(), r.PathValue("id")); err != nil {
				s.flatpakError(w, what, err)
				return
			}
			writeJSON(w, http.StatusOK, map[string]string{"ok": "true", "app_id": r.PathValue("id")})
		}
	}
	mux.HandleFunc("POST /v1/flatpak/apps/{id}/install", do("install", FlatpakManager.Install))
	mux.HandleFunc("POST /v1/flatpak/apps/{id}/update", do("update", FlatpakManager.Update))
	mux.HandleFunc("DELETE /v1/flatpak/apps/{id}", do("remove", FlatpakManager.Remove))
	mux.HandleFunc("POST /v1/flatpak/apps/{id}/launch", do("launch", FlatpakManager.Launch))
}

func (s *Server) flatpakWhy() string {
	if s.S.Flatpak == nil {
		return "this host service has no desktop apps"
	}
	return s.S.Flatpak.Unavailable()
}

func (s *Server) flatpakReady(w http.ResponseWriter) bool {
	if why := s.flatpakWhy(); why != "" {
		apiError(w, http.StatusConflict, "refused", "flatpak_unavailable", why)
		return false
	}
	return true
}

func (s *Server) flatpakError(w http.ResponseWriter, what string, err error) {
	if ref, ok := flatpak.IsRefusal(err); ok {
		apiError(w, http.StatusConflict, "refused", ref.Reason, ref.Message)
		return
	}
	// The error carries the tail of flatpak's own output: it goes to the journal, not to the caller.
	s.S.log().Error("flatpak "+what+" failed", "err", err)
	apiError(w, http.StatusInternalServerError, "internal", "flatpak_"+what, "the desktop app change failed on the box; see its journal")
}
