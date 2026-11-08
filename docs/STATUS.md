# Status — 2026-11-08, Europe/Warsaw

## Delivered scope

Installed: same-user capability daemon, diagnostic CLI, reversible desktop
`streamdeck://` ingress, explicit native launch providers and a reusable PipeWire
application-audio backend. Marketplace OAuth passed a real flow. The unchanged
**Volume Controller 2.0.5.201** now connects to its versioned Audio Router adapter,
lists native/Flatpak apps and controls a real native stream from the MK.2 dynamic
Auto profile. After the fixture test, the user separately authorized normal
control of other applications; that configuration is active. No automated volume
changes were made to those apps. System output control now has a separate opt-in gate, enabled at user request;
see the follow-up evidence below.

Acceptance is bounded: CLI volume/mute/restore and physical 100% → 95% passed on
the isolated native fixture. Hardware mute, manual actions, dials and other device
models remain untested. New bridge-native GUI actions and Wayland input remain
separate roadmap gates. No generic Windows Core Audio translation is claimed.

## Follow-up: system volume, icons and property inspectors

The user confirmed normal per-app control, and requested system control, native
icons with a display preference, event-sound filtering and missing inspector UI.
The previously deliberate global-write restriction is superseded by a separate
`audio.allow_system_write` gate (default false, enabled here for user-driven use).
The new setter selects the current named default sink, validates its server/
serial/index/default identity before the write, preserves channel balance and
never changes routing. No automatic global-volume test was performed.

Native icons are resolved through installed XDG desktop metadata and GTK/GdkPixbuf
in a bounded system-Python worker. Fluxer, Spotify and Helium produced valid
96×96 PNGs (3861/4021/4889 bytes); the actual original client subsequently received
two icons. `display = "icons"` uses the original client's icon plus label;
`display = "text"` uses its text fallback. `deckbridge volume-controller display
icons|text` edits only the private host preference, retains a backup and restarts
the bridge. No vendor assets or application profiles are patched.

`hide_event_streams = true` filters event/notification-role streams (including
libcanberra) from this plugin's view while leaving host discovery intact. The
new contract tests cover event churn, native PNG responses, text selection,
system action scope/races and the original client's post-enumeration System
rekey/synchronization boundary. That slice passed 72 tests; the current total after launch-mode coverage is 75.

The inspector boundary is now reproduced by a controlled normal/test/normal
comparison. A verified bounded backup of 19 registry/profile manifests (134380
bytes) preceded diagnosis. With normal sandboxing, browser CDP responded but
renderer/document commands stalled. The user then authorized **one test only**
without the renderer sandbox, scoped to the original process environment.
The unchanged original inspector rendered: its panel/slider were visible, range
1–25, displayed value 13. This did not change a slider setting. Private evidence:
`webview-oneoff-result.json` and `original-volume-inspector.png`.

The user quit the test and the normal original launcher returned. The test/debug
variables are absent and the debug listener is closed; the user confirmed the
controls are blank again. An initial ad-hoc restart observer aborted on a
transient matching-process change and did not restart the app. The corrected
cleanup tracked the exact main PID, waited for its helpers and verified the
normal returned process. No test mode remains active.

A reviewed optional launch route is installed in `compat/sdeck/webview/`:
`deckbridge streamdeck` delegates to the original audited launcher and defaults
to sandboxed mode. An explicit `--no-webview-sandbox` argument or a deliberate
`[compat.sdeck.webview] renderer_sandbox = false` host preference can select the
compatibility mode. Existing instances are preserved and require Quit first.
The audited configuration still defaults to true: daily-use authorization was
not included in the one-off test. No existing launcher/desktop, registry, vendor
asset or global environment was edited. Read [the scope](compat/sdeck/webview.md)
and [ADR 0003](adr/0003-opt-in-webview-launch.md) before changing that preference.
Current suite: **75 hardware-free tests pass**. The final synthetic encoded/
Unicode deep-link regression reached the same normal original instance, and
pinned vendor hashes still match.

The user confirmed System control, native icons and no libcanberra flicker.
The observed default level changed from about 43% to 48% during that user-driven
window; do not infer one exact button/direction from the net change. Local
metadata evidence is `system-icons-event-filter-smoke.json`. No automatic global
write was issued. Remaining action: a deliberate user choice about daily use of
the now-demonstrated renderer compatibility mode. Until then the normal launch
retains its known blank-inspector limitation.

Historical evidence below describes the preceding accepted milestone; global
writes/icon availability have changed as detailed above.

## Audited baseline

| Item | Observed state |
| --- | --- |
| Selected checkout | Empty Git repository on `master`, no commits/remotes, no user files or applicable existing AGENTS |
| Previous project | `../streamdeck-linux`, Bash installer plus Python helpers and udev fallback; all files untracked, no commits/remotes; preserved |
| Installed launcher | `$HOME/.local/bin/streamdeck-wine` → `$HOME/.local/share/streamdeck-wine/tools/streamdeck-wine.sh launch` |
| Exact prefix | `$HOME/.local/share/streamdeck-wine/prefix`, installer-owned x64, Windows 11 |
| Application | Official Stream Deck `7.6.1.23033`, Qt `6.11.1`; original EXE unmodified by this work |
| Host | Fedora 44 KDE, kernel `7.2.15-200.fc44.x86_64`, Plasma/KWin `6.7.5`, Wayland session |
| Wine | Fedora `11.20-1.fc44` Staging, x86_64/i686; existing XWayland path retained |
| Audio | PipeWire `1.6.10`, WirePlumber `0.5.18`; `pw-cli info 0` reached the real server without mutation |
| Portals | xdg-desktop-portal `1.22.1`, KDE backend `6.7.5`; running user services |
| Device | MK.2 `0fd9:0080`, firmware `1.02.004`, `usbhid`, currently `/dev/hidraw0`; user rw ACL present |
| Build tools | Python `3.14.8`, GCC `16.2.1`, make, venv/ensurepip available; Rust/Cargo/MinGW absent |
| Other libraries | Python gi/dbus and libei `1.6.0` available; libei/PipeWire/Python devel packages absent |
| GitHub | `gh auth status` succeeded; no configured remote, so repository issues/PR context unavailable; nothing published |

At first inspection Stream Deck was not running. Started through the unchanged
launcher at 22:23:46; its own log reported version 7.6.1.23033 and MK.2 connection
at 22:23:50. The renamed `CrBrowserMain` main process was matched by executable
argv **and** `WINEPREFIX`; initial main PID 49044.

The old installed installer differs from its sibling source in uninstall backup
handling; neither copy was overwritten. The original prefix's Liberation Sans
font fix and disabled `winemenubuilder` remain. The previous installer documents
an already-used MSI Firewall metadata workaround; it was not rerun or extended.

Before starting Wine, checked 244 GiB available and copied/verified 70 selected
registry/settings/profile/resource files, 5,070,634 bytes. Private backup:
`$XDG_STATE_HOME/deckbridge/backups/baseline-20261107-222346`, with SHA256 manifest;
the pointer is `$XDG_STATE_HOME/deckbridge/baseline-backup-path`.
Plugins, binaries, logs, Sentry and browser caches were excluded. A separate
private snapshot covers the old host launcher/desktop/installed installer.

## Evidence

| Check | Result and limit |
| --- | --- |
| `make check` | 75 tests pass, Ruff format/lint and Python byte compilation pass; no physical device required |
| IPC | Real AF_UNIX request/response, reconnect, malformed/oversized/partial frames, frame deadline, private path/lock/symlink protections |
| Helper deadline | A real hung Python child is killed and reaped; no indefinite launcher wait |
| Installer tests | Temporary filesystem: dry-run unchanged, repeated install/deactivate, prior MIME restoration, unrelated/user-modified files preserved |
| Actual installation/update | Applied repeatedly, unit/desktop validated, active `systemd --user` service, no failure restart observed; socket dir 0700/socket 0600 |
| Initial URI fault | No Linux handler (`xdg-mime` empty, `gio mime` no handler), despite correct prefix registry command `StreamDeck.exe "%1"` |
| KDE transport fault | `%u` decoded spaces and UTF-8; isolated synthetic custom-scheme probe reproduced it, then was completely removed |
| Actual deep-link | `tools/smoke.py deep-link ...` passed: fresh Elgato `openFile` receipt in the same running instance, `%26/%2F/%25/%2B`, query, fragment and `zażółć` observed |
| Real OAuth | Passed after portal repair: login began 23:11:15, real `marketplace/auth` with code/state arrived 23:11:28, `onLinkingSucceeded` at 23:11:29, Marketplace continued installation; user supplied successful plugin-installation screenshot |
| Portal/authentication consumer | Actual OpenURI portal delivered synthetic `marketplace/auth?code=...&state=...` into Elgato's OAuth handler, which rejected the synthetic state as expected; same original instance, no legacy launcher invocation |
| Native launch | Actual `/usr/bin/python3.14` ELF execution receipt through CLI and `wine start /unix ... deckbridge launch`; same Stream Deck instance remained |
| Native GUI/URL | New bridge-backed physical GUI action and browser launch untested; mappings restored to empty after headless fixture |
| HID | `tools/smoke.py inspect-hardware`: USB identity ioctl passed; rw ACL confirmed; zero input/output reports read/written |
| Physical buttons/display | User observed dynamic Volume Controller Auto profile/test column and pressed Volume Down; measured native fixture changed 100% → 95.00%; other actions remain untested |
| Profile regression | All 64 baseline files remain present; after interactive profile use 62 are SHA256-identical and two JSON manifests differ at `Pages.Current` / `Controllers`. No bridge-side profile edits or restoration; backups retained. Earlier pre-audio rollback check had all 64 identical |
| Wine fixes | Existing static audit passed RPM SHA256 checks and required implementation clues for user32, dnsapi, winebus, hidclass |
| Real-host deactivation | Actual stop/remove/restore/reinstall passed including portal-choice restoration after OAuth completion: previous handler/counters and opaque portal data restored, MIME restored, application PID/profiles/private config preserved; bridge reactivated and runtime matches checkout |

Local safe test evidence is under `$XDG_STATE_HOME/deckbridge/diagnostics`;
`native-smoke.json` records observed native executable identity;
`oauth-success.json` records timestamps and success booleans;
`portal-rollback-smoke.json` records actual scoped restoration/reactivation.
Wine static audit disassembly is local there too. No logs, identifiers or callback
data are committed.

## Volume Controller and audio evidence

| Check | Observed result |
| --- | --- |
| Version/API audit | Exact SDK metadata: `com.elgato.volume-controller` 2.0.5.201; readable JS uses Audio Router JSON-RPC at loopback port 1844. Device NAPI addon enumerated Wine devices. No vendor files modified or protected manifest decoded |
| Native discovery | Real PipeWire 1.6.10 graph: Helium (multiple streams), Flatpak Fluxer Canary (namespaced PID) and temporary native test app; stable server-cookie/serial IDs and application grouping |
| Original client | Exact-prefix Windows Node process authenticated and connected; enumerated apps and responded to real add/remove notifications; currently connected after final deployment |
| Authorized CLI write | On DeckBridge Test only: 25% observed, mute observed, original volume/mute restored; immediate CLI window preserved other streams, sinks and default devices |
| Physical integration | User confirmed dynamic test column/up/down. Initial scalar-unit bug was corrected and regression-tested. Fresh single Volume Down changed 1.0 to 0.9499969482421875, within one Pulse unit of 95% |
| Isolation/cleanup | Unlinked pacat timed out, correctly explaining the disappearing column. Replaced with zero samples into an owned low-priority null sink. Fixture process, descriptor and module removed after acceptance |
| Security | Real unrelated native WebSocket client rejected HTTP 403; temporary transport tests also cover browser Origin rejection, disabled writes and backend-failure disconnect |
| Default suite | 75 tests: model/channel balance, stale IDs/server epoch, write allowlists, scalar contract/events, transport/process attribution, recursive install/obsolete-file preservation, bounded oversized replies and prior regressions |
| Regression | Synthetic encoded/Unicode deep-link reached the same original instance after module reorganization; pinned vendor hashes still match; original app was not restarted for audio integration |
| Normal use | User explicitly approved broadening fixture-only writes to other application streams. Live `[audio]` enabled/write true, empty allowed_apps; private pre-change config backup retained |

The physical evidence's longer comparison window also observed a default sink
volume change from 64% to 69%; the source was not attributed. Do not claim global
volume stayed constant across the entire interactive session. The immediate CLI
test did preserve sink state. The adapter has no global mutation path and no
attempt was made to restore desktop changes. A later external link to the test
sink monitor made the strict fixture-isolation check stop another test before
mutation. The helper was corrected to compare sink state around each exercise,
rather than treating the fixture's entire lifetime as an exclusive test window.
Its old running instance needed an explicitly ownership-checked module cleanup;
the cleanup helper now handles pactl module JSON without assuming an index field.

Local evidence is private under `$XDG_STATE_HOME/deckbridge/diagnostics`, including
`audio-write-smoke.json` and `volume-controller-hardware-smoke.json`. These contain
observations/booleans, not exported vendor logs or OAuth payloads. A failed later
smoke attempt does not overwrite the earlier successful evidence. Code layout
and exact contract/limits are in [the plugin notes](compat/plugins/volume-controller.md)
and [ADR 0002](adr/0002-volume-controller-service-adapter.md).

## Plugin inventory

- `com.elgato.tutorial`, `1.0.4.3`, HTML entrypoint `app.html`: **untested** functionally.
- Stream Deck Icon Library `2.2.0.175`: an asset bundle, not executable-plugin acceptance.
- `com.elgato.volume-controller`, `2.0.5.201`: **plugin-adapter**, automatic MK.2
  discovery and fixture volume control accepted; other boundaries listed above.

A generic manifest scanner is still absent. The installed Volume Controller
manifest is not plain JSON, and only observed public runtime metadata/readable
client behavior was used. The version/hash contract is deliberately narrow.

## Current deployment and next smallest step

Runtime is installed separately from the checkout and matches its Python/JSON
modules. The installer now copies nested modules/contracts, includes the pinned
portable WebSocket dependency and preflights modified obsolete files before any
managed write. New optional audio configuration is backward-compatible with v1.

Folder ownership:

- `deckbridge/compat/sdeck/oauth/`: original callback/portal/forwarding logic.
- `deckbridge/compat/plugins/volume_controller/`: observed plugin contract and adapter.
- `deckbridge/backends/audio/`: reusable Linux model and PipeWire/Pulse control.
- `tools/audio_smoke.py`, `tests/test_audio.py`, `tests/test_volume_*.py`: explicit
  host fixture and hardware-free contract/transport regression coverage.

One exact-prefix original instance remains active (PID 58761 in this session),
with the original Volume Controller Node client connected. Do not infer physical
Linux OK/native-GUI acceptance from the Volume Controller test. OAuth was not
repeated; its previous acceptance and a fresh synthetic transport regression are
separate evidence. For future OAuth regressions, collect only fixed-code/boolean
observations; the application's own private logs can contain real callback data.

The inspector boundary is reproduced; its optional launch mode remains disabled
pending a daily-use decision. Normal
app/System/icon/event-filter behavior was confirmed by the user; physical mute
and manual-detection acceptance remain separate. No additional automatic real-app mutation is
authorized by the fixture test. Native-only PipeWire stream control, generic Core Audio and Wayland input are
not implemented. Native named icons are now available as described above. Host IPC snapshots over
16 KiB fail explicitly; there is no pagination. External Pulse control has a
small non-atomic identity-check/use window; there are no side-effect retries.

The previously observed inotify instance exhaustion was not repaired with global
sysctl changes. Synthetic receipt tests use bounded 100 ms log sampling. No root,
new DLL overrides, global Wine/KDE/security changes or external CI were added.

Local branch: `codex/initial-bridge`. Work is committed locally in thematic
changes after checks; no remote, push or PR. Command-local verified public noreply
Git identity is used; no global Git configuration is changed.

Resume commands:

```bash
make check
deckbridge diagnose
deckbridge audio list
```

After source changes, apply the explicit installer outside an active OAuth flow.
Audio safety/disable options and opt-in test commands are in TESTING.md. Do not
mark all roadmap stages complete based on this plugin slice.
