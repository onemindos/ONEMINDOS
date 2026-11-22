---
pr: pending
branch: claude/p0-metrics-history-log-follow
---
The gateway now serves a Prometheus metrics page at GET /v1/metrics (node CPU, memory, disk, temperature and load, node liveness counts, app health states and open alerts), readable with the monitoring:read scope and filtered by app sharing, so Prometheus can keep the 30-day history the in-memory 24 h graph cannot. Adds a monitoring bundle note on how to scrape it with the Prometheus and Grafana Market apps.
