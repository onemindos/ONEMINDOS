<!-- SPDX-License-Identifier: Apache-2.0 -->
# OneMind Go SDK

`github.com/onemindos/onemindos/sdk/go`, package `onemind`: the Go client for the OneMind gateway API, used by the `onemind` CLI. Standard library only; its own module, so importing it does not pull the rest of the repo.

```go
c, err := onemind.FromEnv()   // ONEMIND_HUB + ONEMIND_TOKEN, or the agent Secret's names
nodes, err := c.Nodes.List(ctx)
a, err := c.Actions.Request(ctx, onemind.ActionRequest{Type: onemind.ActionAppInstall, AppID: "ntfy"})
a, err = c.Actions.Wait(ctx, a.Id, 2*time.Second, nil)
err = c.Events.Subscribe(ctx, onemind.SubscribeOptions{Types: []string{"action.*"}}, func(e onemind.Event) error { ... })
res := onemind.VerifyChain(file) // offline audit check, same rule as core/onemind_core/audit.py
```

Errors are `*onemind.Error`; branch with `errors.Is(err, onemind.ErrExpired)` and friends. Types come from `internal/gen/types.gen.go` (oapi-codegen v2.8.1, Apache-2.0, types only); regenerate with `make -C sdk gen`. Tests: `make -C sdk test-go`.
