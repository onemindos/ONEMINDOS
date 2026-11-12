// SPDX-License-Identifier: Apache-2.0

package service

import (
	"context"
	"net/http"
	"testing"
)

func TestMounts(t *testing.T) {
	h := http.NotFoundHandler()
	got := Mounts(context.Background(), []Service{
		{Name: "a", Mount: "/api/v1/a/", Handler: func(context.Context) http.Handler { return h }},
		{Name: "off", Mount: "/api/v1/off/", Enabled: func() bool { return false }, Handler: func(context.Context) http.Handler { return h }},
		{Name: "nohandler", Mount: "/api/v1/x/"},
	})
	if len(got) != 1 || got["/api/v1/a/"] == nil {
		t.Fatalf("mounts = %v", got)
	}
}
