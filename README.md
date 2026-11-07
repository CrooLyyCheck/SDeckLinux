# DeckBridge

An incremental Linux compatibility layer for the **original Elgato Stream Deck
Windows application and unmodified plugins under Wine**. This first slice adds a
user daemon, diagnostics, a reversible `streamdeck://` handler and explicit native
launch mappings. It does not yet implement Wayland input or Windows Core Audio.

The existing installation is a separate sibling project, `../streamdeck-linux`.
DeckBridge integrates alongside its installed launcher, without reinstalling
Elgato or changing its Wine fixes. See [observed status](docs/STATUS.md),
[architecture](docs/ARCHITECTURE.md) and [roadmap](docs/ROADMAP.md).

## Local verification

Python >= 3.11 is the only runtime dependency. Fedora desktop tools are needed
for host integration. The development environment pins Ruff's Linux x86_64 wheel
and SHA256; it does not install packages globally.

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

## Disable or remove integration

Disable just callback forwarding with `deep_links = false` in `[features]`, then
restart the service. Removing a native mapping disables that target.

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
