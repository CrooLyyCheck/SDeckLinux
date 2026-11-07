# Status — 2026-11-07, Europe/Warsaw

## Delivered scope

First functional slice implemented and installed: a same-user capability daemon,
diagnostic CLI, reversible desktop `streamdeck://` ingress and explicit native
launch providers. Stage 2 is **partial**, with real application URI receipt and
native ELF execution proven. Full OAuth and new bridge-backed physical actions
are not yet accepted. No Wayland input or Core Audio translation is claimed.

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
| `make check` | 29 tests pass, Ruff format/lint and Python byte compilation pass; no physical device required |
| IPC | Real AF_UNIX request/response, reconnect, malformed/oversized/partial frames, frame deadline, private path/lock/symlink protections |
| Helper deadline | A real hung Python child is killed and reaped; no indefinite launcher wait |
| Installer tests | Temporary filesystem: dry-run unchanged, repeated install/deactivate, prior MIME restoration, unrelated/user-modified files preserved |
| Actual installation/update | Applied repeatedly, unit/desktop validated, active `systemd --user` service, no failure restart observed; socket dir 0700/socket 0600 |
| Initial URI fault | No Linux handler (`xdg-mime` empty, `gio mime` no handler), despite correct prefix registry command `StreamDeck.exe "%1"` |
| KDE transport fault | `%u` decoded spaces and UTF-8; isolated synthetic custom-scheme probe reproduced it, then was completely removed |
| Actual deep-link | `tools/smoke.py deep-link ...` passed: fresh Elgato `openFile` receipt in the same running instance, `%26/%2F/%25/%2B`, query, fragment and `zażółć` observed |
| OAuth/plugin continuation | Untested; synthetic URI targets an absent diagnostic UUID; transport success does not prove this boundary |
| Native launch | Actual `/usr/bin/python3.14` ELF execution receipt through CLI and `wine start /unix ... deckbridge launch`; same Stream Deck instance remained |
| Native GUI/URL | New bridge-backed physical GUI action and browser launch untested; mappings restored to empty after headless fixture |
| HID | `tools/smoke.py inspect-hardware`: USB identity ioctl passed; rw ACL confirmed; zero input/output reports read/written |
| Physical buttons/display | Interactive user test pending; device connection alone is not acceptance |
| Profile regression | All 64 backed-up profile/resource files present and SHA256-identical after host tests; old launcher/desktop/installed installer identical |
| Wine fixes | Existing static audit passed RPM SHA256 checks and required implementation clues for user32, dnsapi, winebus, hidclass |
| Real-host deactivation | Dry-run inspected; full stop/remove/restore postponed during the user's interactive OAuth test |

Local safe test evidence is under `$XDG_STATE_HOME/deckbridge/diagnostics`;
`native-smoke.json` records observed native executable identity. Wine static audit
disassembly is local there too. No logs, identifiers or callback data are committed.

## Plugin inventory

- `com.elgato.tutorial`, `1.0.4.3`, HTML entrypoint `app.html`: **untested** functionally.
- Stream Deck Icon Library `2.2.0.175`: no plugin UUID or code entrypoint; asset bundle,
  not evidence of executable plugin compatibility.
- Original Elgato Volume Controller is not installed in the audited plugin directory;
  no private protocol, process model or Core Audio dependency is inferred.

The manifest scanner and versioned compatibility database are not implemented yet.

## Open limits and next smallest step

The user has agreed to perform Marketplace OAuth and the pre-existing Wine Test
**Linux OK** physical key check; awaiting their actual result. Keep the handler
available until that flow finishes. Then test real-host deactivation/reinstall
outside a callback flow and record the MIME/instance/profile observations.

If login still fails, locate whether the native browser invokes the handler,
whether the daemon forwards it, and whether Elgato continues the flow. Collect
only fixed-code/boolean observations, never real callback query values. Elgato's
own private application log can contain URIs; its logger is outside this bridge's
control and must not be exported without redaction.

The workstation's inotify user-instance limit is exhausted (`EMFILE`, limit 128,
only five process FDs in the diagnostic process). No sysctl/security changes were
made. The synthetic log observer uses documented bounded 100 ms sampling, not
callback retries. Keyboard and volume mutation tests have not been authorized or
run. Native action mapping tests were headless and their configuration was restored.

Implemented file groups: `deckbridge/` runtime/CLI, `tools/install.py`,
`tools/smoke.py`, `tools/native_probe.py`, `tests/`, local build configuration and
the architecture/protocol/ADR/roadmap/testing documents. Runtime installation is
separate from the checkout; after source changes, rerun the explicit installer
outside an ongoing OAuth flow.

Local branch: `codex/initial-bridge`. Runtime, installer and tests are committed
as `e817e51` (`feat: add bounded DeckBridge daemon and reversible Wine URL integration`).
Commits use the authenticated GitHub account's verified public noreply identity
through command-local Git options because no author identity was configured.
No global Git configuration was changed and no push/PR was performed.

Resume commands:

```bash
make check
deckbridge diagnose
python3 tools/smoke.py inspect-hardware
```

For real callback observations and rollback commands, follow TESTING.md. Do not
mark the entire project complete while later roadmap acceptance gates remain.
