# DeckBridge

An incremental Linux compatibility layer for the **original Elgato Stream Deck
Windows application and unmodified plugins under Wine**. This first slice adds a
user daemon, diagnostics, a reversible `streamdeck://` handler, explicit native
launch mappings and a PipeWire backend for the original **Volume Controller
2.0.5.201**. Wayland input and a generic Windows Core Audio shim are not implemented.

The existing installation is a separate sibling project, `../streamdeck-linux`.
DeckBridge integrates alongside its installed launcher, without reinstalling
Elgato or changing its Wine fixes. See [observed status](docs/STATUS.md),
[architecture](docs/ARCHITECTURE.md) and [roadmap](docs/ROADMAP.md).

## Local verification

Runtime uses Python >= 3.11 and, for the optional Volume Controller adapter,
`websockets` 17.4. `make setup` verifies the pinned pure-Python wheel and prepares
an isolated runtime dependency tree. Ruff is also hash pinned. No packages are
installed globally. Host audio requires `pw-dump`, `pactl` and PipeWire-Pulse;
desktop integration uses the existing Fedora user tools.

```bash
make setup
make check
```

## Install beside an audited installation

Supply the prefix you actually audited. The following is the discovered prefix
on this workstation, not a universal default:

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

The original application must already be running through `streamdeck-wine`.
Callback forwarding requires exactly one instance in the configured prefix;
it never starts a new instance when none is found. Use your browser's ordinary
external-application confirmation for `streamdeck://`.

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
allowed_apps = ["app:io.deckbridge.audio-test"]

[compat.volume_controller]
enabled = true
```

`allow_write = false` allows discovery only. With writes enabled, `allowed_apps`
restricts control to the listed application keys; an empty list allows all listed
applications. Use `deckbridge audio list` to find actual keys. The audited
workstation now has writes enabled for normal application use following explicit
user authorization. The bridge rejects system/device volume writes.

```bash
deckbridge audio list
# Only after authorizing a target; CLI percentages are 0..100:
deckbridge audio set-volume app:io.deckbridge.audio-test 25
deckbridge audio set-mute app:io.deckbridge.audio-test true
```

Direct PipeWire streams without a PipeWire-Pulse control handle are visible but
read-only. App icons use the original plugin's fallback. Automatic MK.2 profile
discovery and one physical 100% → 95% adjustment passed on an isolated native
test stream. Other apps were discovered without automated volume changes.

Compatibility code is organized by responsibility:

```text
deckbridge/compat/sdeck/oauth/                # Stream Deck URL/OAuth transport
deckbridge/compat/plugins/volume_controller/ # Versioned plugin protocol/peer checks
deckbridge/backends/audio/                   # Reusable Linux audio model/backend
```

## Disable or remove integration

Disable just callback forwarding with `deep_links = false` in `[features]`, then
restart the service. Removing a native mapping disables that target.
Set `[compat.volume_controller] enabled = false` to disable just the plugin
adapter, `[audio] allow_write = false` for read-only audio, or `[audio] enabled =
false` with the adapter disabled to stop audio integration entirely.

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

For explicitly invoked host and hardware tests, see [TESTING.md](docs/TESTING.md).
Do not put real callback URIs into shell history or diagnostic reports.
