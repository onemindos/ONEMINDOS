---
pr: pending
branch: claude/p0-starting-page-fast-gateway
status_rows:
---
Starting page and faster gateway start: a tiny early unit (onemind-starting) answers "OneMind is starting" (HTTP 503, self-reloading page) on the gateway's HTTPS ports with the box certificate until the gateway is ready, then hands the ports over without a refused connection (both bind with SO_REUSEPORT). The gateway unit no longer waits for network-online or for NATS. New QEMU criterion F10 (pre-registered) and a time_to_dashboard_s budget; first run is CI's image workflow.
