# SDeckLinux

A Linux compatibility layer for Elgato Stream Deck software and plugins.

The project connects application and plugin interfaces to native Linux services,
with Wine providing the Windows execution environment.

[Usage and configuration](docs/USAGE.md) · [Architecture](docs/ARCHITECTURE.md) ·
[Roadmap](docs/ROADMAP.md) · [Testing](docs/TESTING.md) ·
[Compatibility evidence](docs/STATUS.md)

## Architecture

Compatibility modules implement the interface expected by the application or
plugin. Reusable Linux backends provide host functionality independently of
those interfaces. Each integration has an explicit scope and can be disabled.

```text
deckbridge/compat/sdeck/          # Stream Deck application interfaces
  oauth/                        # URL and authorization handoff
  webview/                      # Embedded browser launch options
deckbridge/compat/plugins/       # Versioned plugin interfaces
  volume_controller/            # Audio Router service contract
deckbridge/backends/             # Reusable Linux implementations
  audio/                        # PipeWire / PipeWire-Pulse
  desktop/                      # Desktop metadata and icons
```

The [architecture document](docs/ARCHITECTURE.md) defines the layer boundaries,
dependency direction and approach to adding compatibility.

## Current compatibility

Experimental. Status as of **2026-11-08**, on **Fedora 44, KDE Plasma 6.7.5 /
Wayland, Wine 11.20 Staging, Stream Deck 7.6.1.23033, PipeWire 1.6.10 /
WirePlumber 0.5.18, and Stream Deck MK.2**. Other environments are untested.

**Verified** covers the stated behavior on that setup. **Partial** covers only
the listed paths. Detailed observations and test boundaries are in
[STATUS.md](docs/STATUS.md).

### Stream Deck application

| Area | Status | Scope / limitations |
| --- | --- | --- |
| Startup and main GUI | Verified | Original Windows application through the existing Wine installation. |
| `streamdeck://` callbacks | Verified | Browser/portal handoff to an existing same-prefix instance; encoded and Unicode contents supported. |
| Marketplace OAuth | Verified | Account linking in the original application. |
| Marketplace installation | Partial | Volume Controller installation; other downloads and updates are untested. |
| Existing profiles and resources | Verified | Preserved in the original application; the bridge does not rewrite profiles. |
| Plugin settings / property inspector | Partial | Volume Controller's main Auto Detection panel and Step Size slider; requires the [WebEngine workaround](docs/USAGE.md#original-plugin-settings-under-wine), with renderer sandbox disabled and software rendering enabled. |
| Bridge installation and removal | Verified | User-only integration with reversible, scoped MIME/portal changes. |
| Stream Deck application updates | Untested | Updater behavior and compatibility after an upgrade. |

### Basic Stream Deck functions

| Function | Status | Scope / limitations |
| --- | --- | --- |
| MK.2 USB/HID connection | Verified | Device access and connection through the original application. |
| Key images and physical buttons | Partial | Volume Controller's dynamic Auto profile; other actions require separate testing. |
| Profile loading | Partial | Existing profiles and dynamic Auto profile; navigation, folders and switching are not exhaustively tested. |
| Launching native Linux applications | Partial | Allowlisted CLI/Wine handoff; physical GUI-launch action untested. |
| Opening allowlisted URLs | Untested | Provider implemented; physical action/browser behavior untested. |
| Original Wine hotkey actions | Untested | Desktop-wide shortcuts require separate testing. |
| Native Wayland hotkeys, text and clipboard injection | Not implemented | No native input backend. |
| Multi Actions, media keys and automatic profile switching | Untested | No functional coverage. |
| Other device models, dials, touchscreens and hotplug | Untested | Current device coverage is limited to MK.2. |
| Volume-change feedback sound | Unavailable | Not provided. |

### Plugins

| Plugin | Version | Status | Scope / limitations |
| --- | --- | --- | --- |
| Elgato Volume Controller | `2.0.5.201` | Partial | Auto discovery of native/Flatpak audio apps, per-app and System output volume, icons/text, and event-stream filtering. Settings UI requires the WebEngine workaround. Physical mute, Manual Detection, dials and changes to Step Size are not fully tested. Direct PipeWire streams without Pulse handles are read-only. |
| Elgato Tutorial | `1.0.4.3` | Untested | No functional coverage. |
| Other plugins / versions | — | Untested | No universal plugin compatibility or generic Windows Core Audio implementation. |

Volume Controller uses an exact version/hash contract. Protocol limits and the
startup edge with no enumerated applications are documented in the
[plugin compatibility notes](docs/compat/plugins/volume-controller.md).
Stream Deck Icon Library is an asset bundle and is not counted as plugin support.

## Development

Python >= 3.11. Development tools and the optional WebSocket dependency are hash
pinned and installed into isolated environments.

```bash
git clone https://github.com/CrooLyyCheck/SDeckLinux.git
cd SDeckLinux
make setup
make check
```

`make check` runs formatting, lint, byte compilation and hardware-free tests.
Host, hardware and audio mutation tests are [separate and opt-in](docs/TESTING.md).

## Project scope

Installation requires an existing official Stream Deck application under Wine.
This repository does not bootstrap Wine or install Elgato software; see
[requirements and installation](docs/USAGE.md#requirements-and-scope).

The runtime package, commands, configuration paths and user service are named
**DeckBridge** (`deckbridge`).

SDeckLinux is an independent community project, unaffiliated with Elgato.
Vendor applications, plugins and binaries are not distributed here.
