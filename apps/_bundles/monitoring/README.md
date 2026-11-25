<!-- SPDX-License-Identifier: Apache-2.0 -->
# Monitoring bundle: Prometheus + Grafana

**Why.** The gateway keeps node numbers for 24 hours in memory. To see a month, something has to
scrape them and store them. That is Prometheus (storage) with Grafana (charts). Both are Market
apps already; this folder says how to wire them to the gateway's `GET /v1/metrics`.

**Status: first slice.** The endpoint exists. One-approval install, a pre-baked scrape config and
30-day retention are not built yet (see the PR description).

## Wire it by hand today

1. Create a read-only token with the `monitoring:read` scope (Settings, Tokens).
2. Put the token in a Prometheus config (never in git):

```yaml
scrape_configs:
  - job_name: onemind
    scheme: https
    metrics_path: /v1/metrics
    authorization: {credentials_file: /etc/prometheus/onemind.token}
    tls_config: {ca_file: /etc/prometheus/onemind-ca.pem}
    static_configs: [{targets: ["<your-box>:8443"]}]
```

3. Start Prometheus with `--storage.tsdb.retention.time=30d`.
4. In Grafana add Prometheus as a data source and chart `onemind_node_cpu_percent`,
   `onemind_node_disk_free_bytes`, `onemind_app_health` and `onemind_alerts_open`.
