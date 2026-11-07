# Roadmap

| Stage | Status | Acceptance gate |
| --- | --- | --- |
| 0 — audit/baseline | Completed with stated hardware limitations | Real prefix/launcher, host/toolchain versions, HID access, observed application startup, private backup and regression inventory |
| 1 — minimal architecture | Implemented for first slice | Private versioned IPC, discovery/actions/diagnostics, no generic shell, explicit unsupported event support, reversible user installation |
| 2 — deep-links/native launch | OAuth passed; native process and rollback proven; physical GUI action pending | Original hardware action launches a selected native GUI app; hardware regression observed |
| 3 — Wayland hotkey/text | Not implemented | Approved harmless KDE window: Ctrl+A/C/V, Polish Unicode, Wine regression, permission revocation, no stuck modifiers |
| 4 — PipeWire/Volume Controller | Original plugin installed and SDK connected; audio backend not implemented | Real per-stream CLI read/write/mute/events; original unmodified Volume Controller lists/controls Fedora apps, or exact missing boundary documented |
| 5 — plugin compatibility | Audit only | Manifest scanner, UUID/version evidence registry, observed dependencies, per-version functional tests |

Marketplace OAuth acceptance passed on 2026-11-07 at 23:11 Europe/Warsaw and
continued into the original Volume Controller installation. Current smallest
safe step: inspect that installed plugin's real entrypoint/API boundary without
decoding protected packaging, then build the independent host audio backend.
Physical MK.2 native-action acceptance remains outstanding. Do not start a Core
Audio shim before confirming plugin version and actual imports/runtime.

After stage 2 acceptance, implement one approved Wayland input scenario through
KDE/portal/libei. Develop the independent PipeWire backend through host CLI before
attempting original plugin integration. Future capabilities must be added for
observed requirements rather than speculative abstractions.
