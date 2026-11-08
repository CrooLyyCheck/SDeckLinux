# SDeckLinux

An experimental Linux compatibility layer for the **original Elgato Stream Deck
Windows application and unmodified plugins under Wine**. It adds reversible
OAuth/deep-link integration, explicit native application mappings and Linux audio
support for **Volume Controller 2.0.5.201**.

The runtime is called **DeckBridge**: the Python package, `deckbridge` commands,
configuration paths and user service retain that name. SDeckLinux is an independent
community project and is not affiliated with Elgato. Vendor applications, plugins
and binaries are not distributed here.

## Current compatibility

Evidence as of **2026-11-08** comes from one workstation: **Fedora 44, KDE Plasma
6.7.5 on Wayland, Wine 11.20 Staging, Stream Deck 7.6.1.23033, PipeWire 1.6.10 /
WirePlumber 0.5.18, and Stream Deck MK.2**. Other combinations are untested.

**Verified** means an observable result on that setup. **Partial** means only the
listed paths passed acceptance. **Untested** is not a compatibility claim.
See [detailed evidence and limits](docs/STATUS.md).

### Stream Deck application

| Area | Status | Observed behavior / limit |
| --- | --- | --- |
| Startup and main GUI | Verified | Original application runs through the existing Wine installation; its fixes are preserved. |
| `streamdeck://` callbacks | Verified | Browser/portal delivery reaches the existing same-prefix instance, including encoded and Unicode data. |
| Marketplace OAuth | Verified | A real login completed inside Stream Deck and Marketplace continued plugin installation. |
| Marketplace installation | Partial | Original Volume Controller installed successfully; other downloads and updates are untested. |
| Existing profiles and resources | Verified | Baseline files remain present; normal UI changes were observed, with no bridge-side profile rewrite. |
| Plugin settings / property inspector | Partial | The original Auto Detection panel and Step Size slider are visible with the [opt-in WebEngine workaround](#original-plugin-settings-under-wine). This disables the renderer sandbox and enables software rendering. |
| Bridge installation and removal | Verified | User-only install, scoped MIME/portal changes and real-host reversible deactivation were exercised. This is not an Elgato installer. |
| Stream Deck application updates | Untested | Updater behavior and compatibility after an upgrade have not been accepted. |

### Basic Stream Deck functions

| Function | Status | Observed behavior / limit |
| --- | --- | --- |
| MK.2 USB/HID connection | Verified | Device access and the original application's connection were observed on one MK.2. |
| Key images and physical buttons | Partial | Dynamic Volume Controller keys display and adjust volume; other actions are not covered by that test. |
| Profile loading | Partial | Existing profiles and the plugin's dynamic Auto profile work; navigation, folders and switching are not exhaustively tested. |
| Launching native Linux applications | Partial | Allowlisted native ELF execution passed through CLI and Wine; a new physical GUI-launch action still needs acceptance. |
| Opening allowlisted URLs | Untested | Provider implemented; physical action/browser acceptance remains open. Marketplace OAuth is a separate tested path. |
| Original Wine hotkey actions | Untested | No acceptance claim for desktop-wide keyboard shortcuts. |
| Native Wayland hotkeys, text and clipboard injection | Not implemented | No native input backend. |
| Multi Actions, media keys and automatic profile switching | Untested | No functional acceptance recorded. |
| Other device models, dials, touchscreens and hotplug scenarios | Untested | MK.2 evidence does not establish support for other hardware. |
| Volume-change feedback sound | Unavailable | The inaudible experiment was removed; further work was deferred. |

### Plugins

| Plugin | Version | Status | Working paths / limits |
| --- | --- | --- | --- |
| Elgato Volume Controller | `2.0.5.201` | Partial | Auto discovery of native/Flatpak audio apps, per-app and System output volume, native icons or text, and libcanberra/event-stream filtering are confirmed. Original settings panel is visible with the WebEngine workaround. Physical mute, Manual Detection, dials and the effect of changing Step Size are not fully accepted; direct PipeWire streams without Pulse handles remain read-only. |
| Elgato Tutorial | `1.0.4.3` | Untested | Installed inventory only; starting a process does not prove plugin behavior. |
| Other plugins / other versions | — | Untested | No generic Windows Core Audio shim or universal plugin compatibility layer. The Volume Controller adapter checks an exact version/hash contract. |

Stream Deck Icon Library `2.2.0.175` was present as an asset bundle; it is not an
executable-plugin acceptance result. Volume Controller's known startup edge with
no enumerated applications and its other protocol limits are recorded in the
[versioned compatibility notes](docs/compat/plugins/volume-controller.md).

## Requirements and scope

This repository integrates with an **existing, separately installed official
Stream Deck application under Wine**. It does not download Elgato software,
create a fresh Wine prefix or include the original `streamdeck-wine` installer.
The audited installation used that installer layout. The optional
`deckbridge streamdeck` launcher requires its owned prefix/launcher; unsupported
layouts fail explicitly. Bridge installation still requires an explicitly
selected, audited prefix.

Runtime uses Python >= 3.11. The optional Volume Controller adapter uses pinned
`websockets` 17.4; the core uses the standard library. Host audio requires
`pw-dump`, `pactl` and PipeWire-Pulse. Native icons use existing system-Python
GI/GTK3/GdkPixbuf packages, with text fallback. Desktop integration uses existing
user tools including systemd, XDG tools and the KDE portal interface tested here.
No system packages are installed automatically.

```bash
git clone https://github.com/CrooLyyCheck/SDeckLinux.git
cd SDeckLinux
make setup
make check
```

`make setup` creates an isolated development environment and verifies hash-pinned
dependencies, including a separate portable runtime dependency tree. `make check`
runs formatting, lint, byte compilation and hardware-free tests. Hardware/input/
audio mutation tests are separate and opt-in; see [TESTING.md](docs/TESTING.md).
No GitHub Actions or external CI is configured.

## Install beside an audited installation

Supply the prefix you actually audited. This is the tested installer's layout,
not a universal default:

```bash
python3 tools/install.py --prefix "$HOME/.local/share/streamdeck-wine/prefix"
python3 tools/install.py --prefix "$HOME/.local/share/streamdeck-wine/prefix" --apply
deckbridge diagnose
deckbridge capabilities
```

The default is a dry-run. Applying creates user-owned runtime files, a private
`$XDG_CONFIG_HOME/deckbridge/config.toml`, a `systemd --user` service, a hidden
desktop entry and one MIME default key. Existing configuration is retained.
Remembered portal choices pointing to the old `streamdeck-wine` launcher are
updated for this scheme only, with their previous values saved in the private
installation manifest. Counters, thresholds and browser consent are preserved.
The previous MIME key and a private full-file backup are kept in
`$XDG_STATE_HOME/deckbridge`. Unowned or modified managed files block updates.
Updating restarts the daemon; do this outside an ongoing OAuth flow.

For callback forwarding, the original application must already be running in
the configured prefix. Forwarding requires exactly one instance; it never starts
a new instance when none is found. Use your browser's ordinary
external-application confirmation for `streamdeck://`. Never put real callback
URIs into shell history or diagnostic reports.

## Explicit native actions

Mappings start empty. Edit the private configuration to enable selected targets:

```toml
[applications]
editor = ["/usr/bin/kwrite"]

[urls]
elgato-docs = "https://docs.elgato.com/streamdeck/"
```

Use the absolute executable actually installed on your host. Then:

```bash
systemctl --user restart deckbridge
deckbridge launch editor
deckbridge open-url elgato-docs
```

The endpoint takes an alias, never plugin-supplied argv or a shell command.
Windows programs retain their existing Wine actions. For an **explicit new**
Stream Deck System → Open action, an individual `.cmd` can invoke an allowlisted
alias using Wine's existing Unix launcher:

```bat
@echo off
start /unix /home/YOUR_USER/.local/bin/deckbridge launch editor
```

Create that file in a dedicated prefix directory after a bounded backup, and
select it through the original application's UI. No existing profile or
`notepad.exe` association is changed by installation. This recipe is tested at
the Wine/host command boundary; physical-button acceptance is tracked separately.

## Volume Controller

See the [versioned compatibility notes](docs/compat/plugins/volume-controller.md).
The original plugin and its dynamic profile remain unchanged. The adapter serves
its observed Audio Router protocol and lists native Linux applications, including
Flatpak streams. Configuration is opt-in; add these tables to the existing
private TOML file, then restart DeckBridge:

```toml
[audio]
enabled = true
allow_write = false
allow_system_write = false
allowed_apps = []

[compat.volume_controller]
enabled = true
display = "icons"
hide_event_streams = true
```

This example enables discovery with both write gates off. Set `allow_write = true`
to enable application control. `allowed_apps` restricts writes to the listed
application keys; an empty list allows all discovered writable applications.
Use `deckbridge audio list` to find actual keys. System output volume/mute has a
separate opt-in gate: `allow_system_write = true`. It controls only the current
default output and never changes routing. Input-device controls are outside this
adapter. Restart the bridge after editing configuration.

```bash
deckbridge audio list
```

Direct PipeWire streams without a PipeWire-Pulse control handle are visible but
read-only. Native application icons use existing Fedora GI/GTK3/GdkPixbuf packages
in a bounded worker, with the original text fallback if no named icon is found.
The original Auto profile adds its own label to an icon. Choose icon plus label
or text only, without changing vendor files:

```bash
deckbridge volume-controller display icons
deckbridge volume-controller display text
```

The command retains a private config backup and restarts the bridge. Event and
notification sounds such as libcanberra are hidden by default from this plugin;
set `hide_event_streams = false` to show them again. Host audio listing remains
complete. Automatic MK.2 profile discovery and one physical 100% → 95% adjustment
passed on an isolated native test stream. The user subsequently confirmed normal
app control, System control,
native icons and removal of event-stream flicker. No automatic global-volume
test was performed. Property-inspector UI acceptance is tracked separately.

## Original plugin settings under Wine

The blank inspector involved two WebEngine boundaries: renderer sandbox startup
and native GPU composition. The original Auto Detection settings and Step Size
1–25 slider became visible with the approved renderer mode plus software
rendering; the user confirmed the native panel.
See the [controlled result and opt-in launch mode](docs/compat/sdeck/webview.md).

`deckbridge streamdeck` delegates to the existing installer launcher and keeps
the sandbox enabled by default. The optional `--no-webview-sandbox` flag or
`[compat.sdeck.webview] renderer_sandbox = false` changes only that app's child
environment. It reduces renderer isolation and requires a deliberate user
choice. `software_rendering = true` (or `--software-webview`) independently adds
`--disable-gpu`. These are the two preferences used by the accepted configuration:

```toml
[compat.sdeck.webview]
renderer_sandbox = false
software_rendering = true
```

**Disabling the renderer sandbox removes an isolation layer for HTML plugin
pages; they run with your account's permissions.** Repository defaults keep
`renderer_sandbox = true` and `software_rendering = false`. Enable the workaround
only if you accept that tradeoff. Start with **`deckbridge streamdeck`** to apply
these preferences. Quit an existing instance before changing modes; the original
launcher remains independent. No remote debugger is enabled. Settings belong to
the main Auto/Manual Detection action; generated +/- keys do not each have their
own settings panel in this plugin build.

## Code organization

Compatibility is separated by service and plugin; Linux backends do not contain
plugin wire fields:

```text
deckbridge/compat/sdeck/oauth/                # Stream Deck URL/OAuth transport
deckbridge/compat/sdeck/webview/              # Scoped embedded-renderer launch mode
deckbridge/compat/plugins/volume_controller/ # Versioned plugin protocol/peer checks
deckbridge/backends/audio/                   # Reusable Linux audio model/backend
deckbridge/backends/desktop/                 # Native desktop icon lookup
```

See [architecture](docs/ARCHITECTURE.md), [IPC protocol](docs/PROTOCOL.md) and
[roadmap](docs/ROADMAP.md). IPC is bounded, versioned and same-user only. Native
actions use explicit local allowlists; there is no arbitrary shell endpoint.

## Disable or remove integration

Disable just callback forwarding with `deep_links = false` in `[features]`, then
restart the service. Removing a native mapping disables that target.
Set `[compat.volume_controller] enabled = false` to disable just the plugin
adapter, `[audio] allow_write = false` for read-only application streams, and
`allow_system_write = false` independently to disable System control. To stop
audio integration entirely, turn both write gates off, disable the plugin
adapter, and set `[audio] enabled = false`. Restart the service after changes.

For full reversible deactivation:

```bash
python3 tools/install.py --deactivate
python3 tools/install.py --deactivate --apply
```

This stops/disables the daemon, restores its MIME default key if still selected,
restores owned portal choices, and removes unchanged owned files.
User-modified files, configuration, backups,
the Wine prefix and the original Elgato installation remain. A changed MIME
default chosen by the user is preserved. The original `streamdeck-wine` launcher
continues to work independently.
