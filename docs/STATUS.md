# Status — 2026-11-10, Europe/Warsaw

## Core Audio device-control implementation in progress

The native endpoint backend and private IPC/CLI are implemented:
`audio.devices.list`, `audio.device.volume`, `audio.device.mute`. Input/output
writes default off independently of the existing System/application gates.
Host inventory finds Virtuoso. The installed runtime exposes read-only inventory;
private configuration remains byte-identical and ordinary plugin behavior is
preserved. **141 hardware-free tests pass**.

The compiled Windows library implements the MMDevice enumerator factory,
collection/device/endpoint wrappers, scalar/mute API and exact Wine GUID-to-native
name mapping. A real COM probe read nine endpoints (including the isolated
fixture), observed actual levels down to about 60%, passed nine `IUnknown`
identity checks and balanced unload/refcount checks. Its transport saw 18 reads,
zero writes and zero rejected peers. A process-local activation context also let
the original unchanged Volume Controller addon read those actual levels. No
persistent COM registration or vendor-file change was needed.

Windows callback registration/removal and event delivery are now implemented.
The latest read-only COM run, after the fixture expired, passed seven identity
and callback-lifecycle checks with 21 reads and zero writes. A separate run
delivered a real Windows callback for a memory-only simulated native change;
no host volume setter was invoked. Hardware-free tests also verify setter context
GUIDs, default-alias notification, event deduplication and monitor-loss behavior.
Native reconnect acceptance, production loader/deactivation and ordinary
physical-key acceptance remain pending. Unsupported methods fail explicitly.
Details and
developer commands: [Core Audio scope](compat/windows/core-audio.md).
After separate explicit user approval, the original unchanged addon passed
25% → mute → restoration on a fresh isolated null output. Both its Windows
readback and the native channel/mute snapshot confirmed restoration. The backend
allowlist admitted only that output; every input and other output was blocked.
The run made four write requests and 33 reads. Surviving unrelated streams,
other sinks and default devices were unchanged, and the holder removed the
fixture afterwards. No automatic hardware/microphone volume test was performed.

## Manual Detection and device-list follow-up

Read-only calls through the unchanged Windows device addon enumerated seven
active Wine endpoints (four inputs, three outputs) and both default roles. An
isolated SDK fixture running the unchanged plugin received Manual Detection's
application data and both device lists. No key/dial/audio mutation was sent.
The real Manual inspector also contained valid application options; the user
confirmed that its expanded popup appeared blank.

Popup capture showed backgrounds/highlights without labels. A live DOM comparison
changing only Arial to Liberation Sans immediately rendered the original labels;
a color-only comparison did not. Selection indices were unchanged and temporary
styles restored. Additional Qt Quick software rendering was ineffective and is
not included. No new Core Audio shim or plugin protocol is required for this issue.

Shared Wine font fallback is now implemented in `compat/windows/fonts.py`, with
bounded registry helpers shared by the native surface preference manager.
Installation/update and deactivation own the single Arial alias reversibly, with
verified backups, journal recovery, explicit opt-out and user-override preservation.
The local installation passed, kept private configuration byte-identical and
verified readback. **114 hardware-free tests pass**. The user confirmed visible
names in normal use and supplied the Output Device Control panel. The normal
process has no debugger, Qt Quick trial or diagnostic flags. Manual audio actions
and individual input-list visual acceptance remain separate gates.

Output Device Control still does nothing, including with Virtuoso selected. In
Wine 11.20, `AEV_SetMasterVolumeLevelScalar` returns `E_NOTIMPL`, its getter returns
constant 1.0, and mute is stored only in the wrapper. Read-only original-addon
observations returned 1.0 on all seven endpoints. Enumeration does not establish
control; the Audio Router System setter uses a different boundary.
No device setter was invoked automatically. Shared Core Audio endpoint support
is the next implementation boundary; see [ADR 0004](adr/0004-core-audio-endpoint-boundary.md).
An isolated SHA-256-verified llvm-mingw compiler now builds the optional x64 COM
probe (`make native-probe`) without system packages. The real Wine run returned
seven readable endpoints with scalar minimum/maximum 1.0 and zero setters called.
This validates the development ABI path, not a working control shim.

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

## Built-in Wine startup and menu integration

The user confirmed the original panel became visible after restarting from the
ordinary menu through DeckBridge. The original fault was a menu entry bypassing
its renderer settings. The accepted process had both required flags and no remote
debugger.

The fixes are now runtime defaults and part of ordinary installation/update:
software rendering on, renderer sandbox off. Fresh config templates include both
settings; older config files without this section inherit them without rewriting
unrelated preferences. Explicit opt-outs remain respected. `make install`
detects the existing Wine app and installs dependencies, runtime and menu handoff
in one flow. The earlier separate mode-selection dialog has been removed.

Hardware-free acceptance executes the generated menu from a fresh ordinary
installation, with no mode flag or config editing, and observes both flags at a
fixture launcher. Tests also cover older config migration, explicit opt-out
preservation, custom entries, reinstall and menu restoration. Current suite:
**106 hardware-free tests**, including native renderer ownership/rollback coverage.
No audio mutation or new OAuth flow is involved.

The prior installer was already applied on the audited workstation; its private
configuration remained byte-identical, including audio preferences. Safe evidence
is private in `guided-menu-install.json`. The unchanged menu integration and
previously accepted native-panel result remain separate from the automated
fixture coverage. No new physical interaction is inferred from test exit status.

The standard `make install` flow was subsequently run without a mode flag or
interaction. It completed menu/runtime integration, kept private configuration
byte-identical and left the audio backend ready with one original plugin client
connected. Installed module hashes match ownership records. Safe evidence is
private in `builtin-startup-install.json`.

## Follow-up: system volume, icons and property inspectors

### Resolved: notification rendering after Windows backup import

The user reported a large blank secondary window and a blank notification popup
after importing an expanded Windows profile backup. The main key-grid interface
still renders. The secondary Stream Deck window was captured as a white,
frameless surface. Wine repeatedly reports DirectComposition RGBA-to-BGRA surface
conversion failures. Earlier QtWebEngine child crashes were also observed.

Three process-local trials did not fix the reported windows: Qt Quick software
backend, Qt's legacy D3D swapchain, and disabling Chromium DirectComposition.
The ineffective flags and temporary logging rules were removed from the launch
helper; these trials were not published as working compatibility.

Inspection of the original application's startup code identified its own
QSettings boolean `platform_render_surface_enabled`, defaulting to true. Its
enabled branch sets QWidget RHI/Direct3D and the disabled branch selects the
software graphics API. The setting was absent in the existing application key.
After a verified private registry/application-settings backup, a scoped
`REG_DWORD 0` was written under
`HKCU\Software\Elgato Systems GmbH\StreamDeck` and read back through Wine.
After restarting, the user confirmed the result was correct and identified the
large extra window as **Virtual Stream Deck**. It is an application feature, not
an unwanted process/window to suppress. Virtual Deck actions remain untested.
The original application now reports `RasterSurface`; the new Wine log contains
no DirectComposition errors. Native-window acceptance is recorded separately
from the earlier failed flag trials.

Normal installation/update now manages this single preference for the audited
application version/hash, under `compat/sdeck/webview/native_renderer.py`.
Bounded verified registry backups precede Wine access; a journal retains the
original typed value or absence before writing. Deactivation or installation
with `software_rendering = false` restores that original state if still owned.
User changes are preserved, and unrecognized application builds are not modified.
Vendor binaries, profiles and plugins remain unchanged.

The standard `make install` flow passed on the audited workstation with this
manager included. Private configuration, original launcher, vendor executable
and profile JSON hashes stayed unchanged; managed runtime hashes match and the
bridge service is active. The original absent value from the accepted trial is
retained in installation ownership for eventual rollback.

The separate missing-plugin dialog names SimHub Input Trigger from the imported
profile; its content renders normally and has not been removed or patched.

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
rekey/synchronization boundary. That slice passed 72 tests; the current total with launch/render coverage is 76.

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

An optional launch route is installed in `compat/sdeck/webview/`:
`deckbridge streamdeck` delegates to the original audited launcher. At that milestone, repository
defaults retained sandboxing and automatic GPU selection. The user separately
approved daily use with `renderer_sandbox = false` for this route. A subsequent
native-window screenshot still showed the correct main Auto action selected
with a blank inspector, despite healthy renderers. The earlier CDP screenshot
proved HTML rendering only; it was not sufficient native-window acceptance.

A process-local Chromium `--disable-gpu` comparison then made the actual panel
visible, confirmed by the user. The independent `software_rendering = true`
preference now preserves that result for future `deckbridge streamdeck` starts.
The current app already runs with these two settings and no remote debugger.
No additional restart is needed. Private evidence:
`webview-composition-smoke.json`; native window images remain private.
No existing launcher/desktop, registry, vendor asset or global environment was
edited. Read [the scope](compat/sdeck/webview.md) and
[ADR 0003](adr/0003-opt-in-webview-launch.md). Current suite: **76 hardware-free
tests pass**. The final synthetic encoded/Unicode callback regression also
reached the original instance; pinned vendor hashes still match.

The user confirmed System control, native icons and no libcanberra flicker.
The observed default level changed from about 43% to 48% during that user-driven
window; do not infer one exact button/direction from the net change. Evidence:
`system-icons-event-filter-smoke.json`. No automatic global write was issued.
The main Auto/Manual inspector panel is now accepted as visible. The effect of
changing the Step Size and every per-action/manual/dial variation remains its
own behavioral acceptance gate, rather than being inferred from panel visibility.

Historical evidence below describes the preceding accepted milestone; global
writes/icon availability have changed as detailed above.

## Deferred volume-feedback sound

The optional `canberra-gtk-play` feedback experiment was stopped at the user's
request. Helper completion did not establish audibility; the user reported no
sound. The experimental code, tests, live preference and installed module were
removed, restoring the previously verified runtime. Existing volume control,
icons, event-stream filtering and accepted WebEngine preferences are preserved.
Do not resume this experiment without a new user request.

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
| `make check` | 76 tests pass, Ruff format/lint and Python byte compilation pass; no physical device required |
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
| Default suite | 76 tests: model/channel balance, stale IDs/server epoch, write allowlists, scalar contract/events, transport/process attribution, recursive install/obsolete-file preservation, bounded oversized replies and prior regressions |
| Regression | Synthetic encoded/Unicode deep-link reached the same original instance after module reorganization; pinned vendor hashes still match; original app was not restarted for audio integration |
| Normal use | User explicitly approved broadening fixture-only writes to other application streams. Live `[audio]` enabled/write true, empty allowed_apps; private pre-change config backup retained |

The physical evidence's longer comparison window also observed a default sink
volume change from 64% to 69%; the source was not attributed. Do not claim global
volume stayed constant across the entire interactive session. The immediate CLI
test did preserve sink state. At that milestone the adapter had no global mutation
path; the later opt-in System setter is documented above. No attempt was made to
restore desktop changes. A later external link to the test
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

At the local acceptance snapshot, one exact-prefix original instance was active,
with the original Volume Controller Node client connected. Do not infer physical
Linux OK/native-GUI acceptance from the Volume Controller test. OAuth was not
repeated; its previous acceptance and a fresh synthetic transport regression are
separate evidence. For future OAuth regressions, collect only fixed-code/boolean
observations; the application's own private logs can contain real callback data.

The inspector panel is visible with the approved scoped launch and software
rendering preferences. Normal
app/System/icon/event-filter behavior was confirmed by the user; physical mute
and manual-detection acceptance remain separate. No additional automatic real-app mutation is
authorized by the fixture test. Native-only PipeWire stream control, generic Core Audio and Wayland input are
not implemented. Native named icons are now available as described above. Host IPC snapshots over
16 KiB fail explicitly; there is no pagination. External Pulse control has a
small non-atomic identity-check/use window; there are no side-effect retries.

The previously observed inotify instance exhaustion was not repaired with global
sysctl changes. Synthetic receipt tests use bounded 100 ms log sampling. No root,
new DLL overrides, global Wine/KDE/security changes or external CI were added.

The source project is named **SDeckLinux**. The runtime package, commands,
configuration paths and service retain the name **DeckBridge** to preserve the
working installation. The README links to the dedicated compatibility page,
which separates application, basic device-function and plugin status. Each table
starts with a dots-only Status column explained by a shared legend. Source
publication excludes the Wine prefix, vendor
software, private state and test captures. No GitHub Actions or external CI is
configured. Command-local verified public noreply Git identity is used; no global
Git configuration is changed.

Resume commands:

```bash
make check
deckbridge diagnose
deckbridge audio list
```

After source changes, apply the explicit installer outside an active OAuth flow.
Audio safety/disable options and opt-in test commands are in TESTING.md. Do not
mark all roadmap stages complete based on this plugin slice.
