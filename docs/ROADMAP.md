# Roadmap

| Stage | Status | Acceptance gate |
| --- | --- | --- |
| 0 — audit/baseline | Completed with stated hardware limitations | Real prefix/launcher, host/toolchain versions, HID access, observed application startup, private backup and regression inventory |
| 1 — minimal architecture | Implemented for first slice | Private versioned IPC, discovery/actions/diagnostics, no generic shell, explicit unsupported event support, reversible user installation |
| 2 — deep-links/native launch | OAuth passed; native process and rollback proven; physical GUI action pending | Original hardware action launches a selected native GUI app; hardware regression observed |
| 3 — Wayland hotkey/text | Not implemented | Approved harmless KDE window: Ctrl+A/C/V, Polish Unicode, Wine regression, permission revocation, no stuck modifiers |
| 4 — PipeWire/Volume Controller | Backend and pinned adapter installed; native discovery, CLI and physical fixture volume accepted; normal app control enabled by user | Real per-stream CLI read/write/mute/events; original unmodified Volume Controller lists/controls Fedora apps, or exact missing boundary documented |
| 5 — plugin compatibility | Audit only | Manifest scanner, UUID/version evidence registry, observed dependencies, per-version functional tests |

Marketplace OAuth acceptance passed on 2026-11-07 at 23:11 Europe/Warsaw and
continued into the original Volume Controller installation. The user's next
priority was Volume Controller. Its independently verified PipeWire backend and
observed Audio Router adapter now work with the unchanged original client.

The MK.2 dynamic Auto profile showed a native test stream, and a corrected physical
button test measured 100% → 95%. CLI 25%/mute/restore passed on that stream only.
The user then authorized normal control of other native apps. Remaining stage 4
gates include physical mute/manual actions and broader real-app acceptance; direct
PipeWire-only streams remain read-only. See the versioned plugin notes for limits.

Stage 2 native-GUI/hardware regression and stage 3 Wayland input remain separate.
Future capabilities should follow observed consumers, without speculative shims
or a replacement app/plugin UI. No broad Core Audio compatibility is implied.
