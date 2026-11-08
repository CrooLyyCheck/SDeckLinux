# Compatibility

Experimental. Status as of **2026-11-08**, on **Fedora 44, KDE Plasma 6.7.5 /
Wayland, Wine 11.20 Staging, Stream Deck 7.6.1.23033, PipeWire 1.6.10 /
WirePlumber 0.5.18, and Stream Deck MK.2**. Other environments are untested.

[Application](#stream-deck-application) ·
[Basic functions](#basic-stream-deck-functions) · [Plugins](#plugins)

## Status legend

- 🟢 **Verified** — the stated behavior was observed on the tested setup.
- 🟡 **Partial** — only the listed paths are verified; limitations apply.
- ⚪ **Untested** — no functional acceptance recorded.
- 🔴 **Not implemented / Unavailable** — the feature is not provided.

Each row includes a colored marker and a text label. Detailed observations and
test boundaries are in [STATUS.md](STATUS.md).

## Stream Deck application

| Area | Status | Scope / limitations |
| --- | :---: | --- |
| Startup and main GUI | 🟢 **Verified** | Original Windows application through the existing Wine installation. |
| `streamdeck://` callbacks | 🟢 **Verified** | Browser/portal handoff to an existing same-prefix instance; encoded and Unicode contents supported. |
| Marketplace OAuth | 🟢 **Verified** | Account linking in the original application. |
| Marketplace installation | 🟡 **Partial** | Volume Controller installation; other downloads and updates are untested. |
| Existing profiles and resources | 🟢 **Verified** | Preserved in the original application; the bridge does not rewrite profiles. |
| Plugin settings / property inspector | 🟡 **Partial** | Main Auto Detection panel and Step Size slider. Requires the [WebEngine workaround](USAGE.md#original-plugin-settings-under-wine): renderer sandbox off, software rendering on. Step Size changes need behavioral verification. |
| Bridge installation and removal | 🟢 **Verified** | User-only integration with reversible, scoped MIME/portal changes. |
| Stream Deck application updates | ⚪ **Untested** | Updater behavior and compatibility after an upgrade. |

## Basic Stream Deck functions

| Function | Status | Scope / limitations |
| --- | :---: | --- |
| MK.2 USB/HID connection | 🟢 **Verified** | Device access and connection through the original application. |
| Key images and physical buttons | 🟡 **Partial** | Volume Controller's dynamic Auto profile; other actions require separate testing. |
| Profile loading | 🟡 **Partial** | Existing profiles and dynamic Auto profile; navigation, folders and switching are not exhaustively tested. |
| Launching native Linux applications | 🟡 **Partial** | Allowlisted CLI/Wine handoff; physical GUI-launch action untested. |
| Opening allowlisted URLs | ⚪ **Untested** | Provider implemented; physical action/browser behavior untested. |
| Original Wine hotkey actions | ⚪ **Untested** | Desktop-wide shortcuts require separate testing. |
| Native Wayland hotkeys, text and clipboard injection | 🔴 **Not implemented** | No native input backend. |
| Multi Actions, media keys and automatic profile switching | ⚪ **Untested** | No functional coverage. |
| Other device models, dials, touchscreens and hotplug | ⚪ **Untested** | Current device coverage is limited to MK.2. |
| Volume-change feedback sound | 🔴 **Unavailable** | Not provided. |

## Plugins

| Plugin | Version | Status | Scope / limitations |
| --- | --- | :---: | --- |
| Elgato Volume Controller | `2.0.5.201` | 🟡 **Partial** | Auto app discovery, app/System output volume, icons/text and event-stream filtering. Hardware mute, Manual Detection and dials remain unverified. [Details and limits](compat/plugins/volume-controller.md). |
| Elgato Tutorial | `1.0.4.3` | ⚪ **Untested** | No functional coverage. |
| Other plugins / versions | — | ⚪ **Untested** | No universal plugin compatibility or generic Windows Core Audio implementation. |

Volume Controller uses an exact version/hash contract. Direct PipeWire streams
without Pulse handles are read-only. Settings UI requires the
[WebEngine workaround](USAGE.md#original-plugin-settings-under-wine). Protocol
limits and the startup edge with no enumerated applications are documented in the
[plugin compatibility notes](compat/plugins/volume-controller.md).
Stream Deck Icon Library is an asset bundle and is not counted as plugin support.
