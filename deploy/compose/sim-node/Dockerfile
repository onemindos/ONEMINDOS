# SPDX-License-Identifier: Apache-2.0
# Tiny simulated node for the Mac demo: Python standard library only.
FROM python:3.13.18-alpine@sha256:9ef1a599f863231c3d91e941389bfdc4a2d6070557243d54df1a4e57015b960e
COPY heartbeat.py /app/heartbeat.py
USER 65534:65534
EXPOSE 7480
ENTRYPOINT ["python3", "-I", "/app/heartbeat.py"]
