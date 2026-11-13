// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"sync"

	"github.com/onemindos/onemindos/internal/service"
)

// DefaultConfigPath is where the gateway coordinator writes the agent's settings.
const DefaultConfigPath = "/data/onemind/backup/agent.json"

// ConfigPath is the settings file: ONEMIND_BACKUP_CONF or the default.
func ConfigPath() string {
	if p := os.Getenv("ONEMIND_BACKUP_CONF"); p != "" {
		return p
	}
	return DefaultConfigPath
}

// Service runs the backup agent inside onemindd (docs/leap/core/PLUMBING.md section 7). It is
// enabled only when the settings file exists, so a box without backups is unchanged. It mounts
// the loopback API under /api/v1/backup/ on the agent's :7480 mux. A broken settings file is
// logged and answered with 503; it never takes the heartbeat down.
func Service() service.Service {
	var (
		once sync.Once
		ag   *Agent
		err  error
	)
	get := func() (*Agent, error) {
		once.Do(func() {
			var c Config
			if c, err = LoadConfig(ConfigPath()); err != nil {
				return
			}
			ag, err = New(c)
		})
		return ag, err
	}
	return service.Service{
		Name: "backup",
		Enabled: func() bool {
			_, statErr := os.Stat(ConfigPath())
			return statErr == nil
		},
		Mount: "/api/v1/backup/",
		Handler: func(ctx context.Context) http.Handler {
			a, gerr := get()
			if gerr != nil {
				return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": "unavailable", "detail": "backup agent not configured correctly; see the onemindd log"})
				})
			}
			return a.Handler(ctx)
		},
		Run: func(ctx context.Context, log *slog.Logger) error {
			a, gerr := get()
			if gerr != nil {
				return gerr
			}
			if a == nil {
				return errors.New("backup agent not built")
			}
			a.Log = log
			a.Loop(ctx)
			return nil
		},
	}
}
