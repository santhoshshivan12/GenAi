Maintainer: this demo treats package-registry as a third-party DevRel service, so ownership must be verified before production.
Reach: it should reach only package metadata; it must not access source files, credentials, or arbitrary network targets.
Logs: assume package names, versions, caller identity, and timestamps may be logged for audit.
Stolen token: an attacker could read metadata, enumerate packages, or invoke any granted registry capability.
Ship decision: do not ship until provenance, least-privilege auth, logging retention, and tool allow-lists are reviewed.
