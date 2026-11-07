# Roadmap

| Stage | Status | Acceptance gate |
| --- | --- | --- |
| 0 — audit/baseline | Completed with stated hardware limitations | Real prefix/launcher, host/toolchain versions, HID access, observed application startup, private backup and regression inventory |
| 1 — minimal architecture | Implemented for first slice | Private versioned IPC, discovery/actions/diagnostics, no generic shell, explicit unsupported event support, reversible user installation |
| 2 — deep-links/native launch | Partial; real application receipt and native process proven | Full OAuth callback continues the original flow; original hardware action launches a selected native GUI app; regression and rollback pass |
| 3 — Wayland hotkey/text | Not implemented | Approved harmless KDE window: Ctrl+A/C/V, Polish Unicode, Wine regression, permission revocation, no stuck modifiers |
| 4 — PipeWire/Volume Controller | Not implemented | Real per-stream CLI read/write/mute/events; original unmodified Volume Controller lists/controls Fedora apps, or exact missing boundary documented |
| 5 — plugin compatibility | Audit only | Manifest scanner, UUID/version evidence registry, observed dependencies, per-version functional tests |

Current smallest next step: collect the interactive Marketplace OAuth result and
physical MK.2 action result, then reproduce any remaining failure at its actual
boundary. See STATUS for evidence and outstanding tests. Do not start a Core Audio
shim before inspecting a real installed Volume Controller version and its imports/runtime.

After stage 2 acceptance, implement one approved Wayland input scenario through
KDE/portal/libei. Develop the independent PipeWire backend through host CLI before
attempting original plugin integration. Future capabilities must be added for
observed requirements rather than speculative abstractions.
