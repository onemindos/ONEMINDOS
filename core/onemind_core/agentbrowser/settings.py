# SPDX-License-Identifier: Apache-2.0
"""Settings of the agent browser (#694), from ONEMIND_AGENTBROWSER_<FIELD> (sections.py)."""

from __future__ import annotations

from dataclasses import dataclass

from ..sections import config_section


@config_section("agentbrowser")
@dataclass(frozen=True)
class AgentBrowserSettings:
    # Off until the box has the browser image: routes that start a session answer 409 agent_browser_off.
    enabled: bool = False
    image: str | None = None            # the browser pod image, pinned by digest (repo@sha256:...)
    namespace: str = "onemind-agent-browser"
    proxy_listen: str = "0.0.0.0"       # where the egress proxy listens on the hub
    proxy_port: int = 3129
    proxy_host: str | None = None       # the address pods dial for the proxy; unset = the hub's first pod-network address
    hub_cidrs: tuple[str, ...] = ()     # the hub's addresses as pods see them; unset = read from the flannel interfaces
    control_port: int = 9300
    max_pages: int = 30                 # page budget of a session unless the caller asks for less
    max_pages_cap: int = 200
    session_ttl_s: int = 900
    max_sessions_per_agent: int = 2

    def validate(self) -> None:
        if self.enabled and (not self.image or "@sha256:" not in self.image):
            raise ValueError("ONEMIND_AGENTBROWSER_IMAGE must be pinned by digest (name@sha256:...) when the agent browser is on")
        if not self.namespace.startswith("onemind-"):
            raise ValueError("ONEMIND_AGENTBROWSER_NAMESPACE must start with onemind-")
        if not 1 <= self.max_pages <= self.max_pages_cap <= 1000:
            raise ValueError("ONEMIND_AGENTBROWSER_MAX_PAGES must be between 1 and MAX_PAGES_CAP (at most 1000)")
        if not 60 <= self.session_ttl_s <= 4 * 3600:
            raise ValueError("ONEMIND_AGENTBROWSER_SESSION_TTL_S must be between 60 and 14400")
        if not 1 <= self.max_sessions_per_agent <= 10:
            raise ValueError("ONEMIND_AGENTBROWSER_MAX_SESSIONS_PER_AGENT must be between 1 and 10")
        for port in (self.proxy_port, self.control_port):
            if not 0 <= port <= 65535:
                raise ValueError("agent browser ports must be between 0 and 65535")
