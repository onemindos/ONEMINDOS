# Refuter (security lens): DC-16 trust root (E9)

**Refuter:** independent, security lens · **Date:** 2026-11-11 · **Read:** the conclusion and claims C-W19-011, -012, -015, -021, -022, -023, -025, -026, -028 and -033. The conclusion has no claim ID of its own, so this file is named after the extension point, E9.

## Target

OneMind installs only digest-pinned, publisher-signed, OneMind-countersigned plugins and publishes them from CI only. It keeps a signed revocation list that disables a plugin to a safe state and never substitutes code.

## Strongest counter-argument

Signing proves *who* published a plugin, not *whether it is safe*. The cited model has kept failing.

- **VS Code, the cited model, kept shipping malware.** The VS Code Marketplace signs every extension and scans each publish (C-W19-023), yet credential stealers kept getting through:
  - In May 2025, three wallet stealers were found. The actor kept editing payloads after removal (C-REF-W19-security-010).
  - In August 2025, ReversingLabs showed that names of *removed* extensions can be reclaimed by anyone. Malicious "shiba" extensions were republished that way (C-REF-W19-security-009). A revocation list keyed by name or ID can be sidestepped by re-registering the identity.
- **Valid credentials sign malware.** Shai-Hulud 2.0 (November 2025) used *legitimate stolen maintainer tokens* to republish up to 100 of each victim's packages, and planted persistent CI runners (C-REF-W19-security-011). A publisher signature from a compromised account is a valid signature. "Publishes from CI only" moves the target to the CI system, which the worm attacked directly.
- **Offline devices miss revocations.** A signed revocation list with no expiry or freshness check can be withheld. TUF calls this an *indefinite freeze attack*; serving an older list is a *rollback attack* (C-REF-W19-security-008). OneMind targets off-grid devices, which will often go without the list. HACS polls every 6 h (C-W19-015) and VS Code depends on connectivity, so neither shows what happens offline.
- **One countersigning key is a single point of failure.** TUF recommends threshold or quorum signatures and separated roles (C-REF-W19-security-008).

## New sources (failure, abandonment)

| ID | Source | Opened |
|---|---|---|
| C-REF-W19-security-009 | ReversingLabs name-reuse loophole (Techworm, SECONDARY), https://www.techworm.net/2025/08/malicious-vs-code-extensions-exploit-marketplace-loophole.html | yes |
| C-REF-W19-security-010 | Datadog Solidity stealers (Help Net Security, SECONDARY), https://www.helpnetsecurity.com/2025/05/21/data-stealing-vs-code-extensions-removed-from-official-marketplace/ | yes |
| C-REF-W19-security-011 | Trend Micro, Shai-Hulud 2.0, https://www.trendaisecurity.com/en-us/resources-insights/trendai-security-blog/shai-hulud-2-0-targets-cloud-and-developer-systems | yes |
| C-REF-W19-security-008 | TUF security model, https://theupdateframework.io/docs/security/ | yes |

## Verdict: **WEAKENED**

The direction is right, and it is far stronger than git-clone `HEAD` (C-W19-012, C-W19-033). As written, though, E9 is a signing scheme, not a trust root. To earn the name, release 1 needs:

- **Freshness.** Signed metadata with an expiry and a monotonic version (TUF or an equivalent such as RAUC-style signed bundles plus a timestamp role). Devices that are offline past the expiry fall back to a declared policy: keep running, but refuse new installs and host grants.
- **Key roles.** An offline root, threshold signing for the countersignature, and separate keys for plugins, driver packs (see the C-W19-048 file) and revocation.
- **Identity revocation.** Revoked plugin IDs and publisher namespaces are never released for reuse.
- **Provenance tied to the build.** The countersignature binds an attested CI build (for example SLSA provenance) of a reviewed commit, and covers the declared E2 grants. A stolen publisher token alone cannot produce an installable plugin.
- **Risk tiers.** Plugins that request host grants (E2, E3, E4) get human review before countersigning. A scan alone is not enough.

## What would flip it

- **To upheld:** an E9 spec that defines expiry and rollback protection for the revocation list, threshold countersigning and permanent ID reservation. A lab would also need to show that a device offline past expiry refuses new host grants, and that a replayed old revocation list is rejected.
- **To refuted:** evidence that OneMind cannot run human review for host-grant plugins at the expected volume. The countersignature would then be a rubber stamp, and host-level third-party plugins should be dropped from release 1.
