// SPDX-License-Identifier: Apache-2.0

package main

import (
	"context"
	"flag"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/onemindos/onemindos/internal/heartbeat"
	"github.com/onemindos/onemindos/internal/imagegc"
)

// runImages is `onemindd images` (NMD-08, #133): the offline-aware image cleanup
// and disk budget, in its own unit (onemind-images.service) because removing an
// image needs the container runtime, and the heartbeat agent stays read-only.
// It removes only superseded images (internal/imagegc), never those of an
// installed app, stopped or not, and writes the heartbeat's "images" object to
// -report for the agent to publish.
//
//	onemindd images [-report FILE] [-disk PATH] [-once]
//
// Budget: ONEMIND_IMAGES_BUDGET_PCT (default 80) and ONEMIND_IMAGES_WARN_PCT
// (default budget - 10), read from the unit's environment.
func runImages(args []string) int {
	fs := flag.NewFlagSet("onemindd images", flag.ContinueOnError)
	report := fs.String("report", env("ONEMIND_IMAGES_REPORT", imagegc.DefaultReportPath), "where the heartbeat's images object is written")
	disk := fs.String("disk", env("ONEMIND_IMAGES_DISK", "/var/lib/rancher"), "a path on the filesystem holding the image store")
	crictl := fs.String("crictl", env("ONEMIND_CRICTL", "crictl"), "crictl command, space-separated (a k3s link, or \"k3s crictl\")")
	kubectl := fs.String("kubectl", env("ONEMIND_KUBECTL", "kubectl"), "kubectl command, space-separated (a k3s link, or \"k3s kubectl\")")
	once := fs.Bool("once", false, "clean once, write the report and exit")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	log := newLogger().With("service", "images")
	c := imagegc.New(imagegc.Exec{Crictl: strings.Fields(*crictl), Kubectl: strings.Fields(*kubectl), Timeout: 2 * time.Minute},
		imagegc.ConfigFromEnv(), func() (float64, bool) { return imagegc.DiskUsedPct(*disk) })
	publish := func(r *imagegc.Report) error { return imagegc.WriteReport(*report, r) }
	if *once {
		res := c.Clean(context.Background())
		log.Info("image cleanup", "outcome", res.Outcome, "removed", len(res.Removed), "freed_bytes", res.Freed, "reason", res.Reason)
		if err := publish(c.Report()); err != nil {
			log.Error("image report not written", "err", err)
			return 1
		}
		if res.Outcome == "failed" {
			return 1
		}
		return 0
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if err := c.Run(ctx, log, publish); err != nil {
		log.Error("image cleaner stopped", "err", err)
		return 1
	}
	return 0
}

// imagesReport is the heartbeat's "images" source: the cleaner's report file,
// or nothing when this node runs no cleaner.
func imagesReport(path string) func() *heartbeat.Images {
	return func() *heartbeat.Images { return imagegc.ReadReport(path) }
}
