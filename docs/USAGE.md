# Usage

## Guided setup

For an existing installation using the supported `streamdeck-wine` layout, run
`bash install.sh` from this repository. KDE shows a setup window; a terminal
choice is available when KDialog is absent. Python >= 3.11 and `make` must already
be installed. The helper prepares the isolated, hash-pinned dependencies.

Choose **Install with plugin settings fix** to apply the tested WebEngine mode
and menu handoff automatically. This mode uses software rendering and disables
the renderer sandbox only for Stream Deck, reducing isolation of plugin pages.
The installer explains this before applying changes. **Install with sandbox**
retains renderer isolation, with potentially blank plugin panels on the tested
Wine setup. **Cancel** makes no changes.

Both modes wire the ordinary **Stream Deck (Wine)** menu icon to the saved
DeckBridge preferences. No private TOML editing or separate local launcher patch
is required. Quit an already running app, then reopen it from the menu. The helper
does not enable autostart, install system packages or download Elgato software.

The original menu entry is backed up, hash tracked and restored on deactivation.
Existing custom entries are preserved: setup stops rather than overwriting them.
Advanced users can use `--no-menu` below to leave a custom shortcut alone.

## Requirements and scope

This repository integrates with an **existing, separately installed official
Stream Deck application under Wine**. It does not download Elgato software,
create a fresh Wine prefix or include the original `streamdeck-wine` installer.
The audited installation used that installer layout. The
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
audio mutation tests are separate and opt-in; see [TESTING.md](TESTING.md).
No GitHub Actions or external CI is configured.

## Manual installation

Supply the prefix you actually audited. This is the tested installer's layout,
not a universal default:

```bash
python3 tools/install.py --prefix "$HOME/.local/share/streamdeck-wine/prefix" --webview-mode compatible
python3 tools/install.py --prefix "$HOME/.local/share/streamdeck-wine/prefix" --webview-mode compatible --apply
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

`--webview-mode compatible` explicitly selects software rendering with the
renderer sandbox disabled; `--webview-mode sandboxed` restores sandboxing and
automatic GPU selection. Omitting this option preserves existing preferences;
new configurations retain sandboxed defaults. Existing unrelated settings are
preserved and changes keep a verified private backup.

The installer automatically hands over the known installer's unmodified menu
entry, retaining its name and icon. The original Wine launcher and its ownership
manifest remain intact. `--no-menu` leaves an unmanaged menu alone, or restores
an entry previously managed by DeckBridge. Unknown prefix layouts do not receive
automatic menu integration; guided setup requires the recognized layout.

Before regenerating menu entries with the separate original Wine installer,
restore the entry using `--no-menu --apply` (with the same `--prefix`) or deactivate
DeckBridge, then rerun guided setup afterwards. Ownership checks preserve an
entry managed by the other installer instead of silently overwriting it.

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

See the [versioned compatibility notes](compat/plugins/volume-controller.md).
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
complete. See the [compatibility notes](compat/plugins/volume-controller.md)
for supported actions and current limits.

## Original plugin settings under Wine

If the plugin property inspector is blank, the tested Wine setup requires
process-local WebEngine options for renderer startup and software composition.
See the [WebEngine compatibility notes](compat/sdeck/webview.md) for the exact
scope and known limits.

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
direct launcher remains independent. The installed menu applies these preferences
automatically. No remote debugger is enabled. Settings belong to
the main Auto/Manual Detection action; generated +/- keys do not each have their
own settings panel in this plugin build.

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
restores owned portal choices and its unchanged menu entry, and removes unchanged owned files.
User-modified files, configuration, backups,
the Wine prefix and the original Elgato installation remain. A changed MIME
default chosen by the user is preserved. The original `streamdeck-wine` launcher
continues to work independently.
