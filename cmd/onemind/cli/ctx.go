// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"context"
	"net/url"
	"time"
)

func ctxTimeout(d time.Duration) (context.Context, context.CancelFunc) {
	if d <= 0 {
		return context.WithCancel(context.Background())
	}
	return context.WithTimeout(context.Background(), d)
}

func urlq(s string) string { return url.QueryEscape(s) }
