# Compatibility

Experimental. Status as of **2026-11-10**, on **Fedora 44, KDE Plasma 6.7.5 /
Wayland, Wine 11.20 Staging, Stream Deck 7.6.1.23033, PipeWire 1.6.10 /
WirePlumber 0.5.18, and Stream Deck MK.2**. Other environments are untested.

[Application](#stream-deck-application) ·
[Basic functions](#basic-stream-deck-functions) · [Plugins](#plugins)

## Status legend

- 🟢 **Verified** — the stated behavior was observed on the tested setup.
- 🟡 **Partial** — only the listed paths are verified; limitations apply.
- ⚪ **Untested** — no functional acceptance recorded.
- 🔴 **Not implemented / Unavailable** — the feature is not provided.

The first column uses the dots defined above. Detailed observations and test
boundaries are in [STATUS.md](STATUS.md).

## Stream Deck application

| Status | Area | Scope / limitations |
| :---: | --- | --- |
| 🟢 | Startup and main GUI | Original Windows application through the existing Wine installation. |
| 🟢 | `streamdeck://` callbacks | Browser/portal handoff to an existing same-prefix instance; encoded and Unicode contents supported. |
| 🟢 | Marketplace OAuth | Account linking in the original application. |
| 🟡 | Marketplace installation | Volume Controller installation; other downloads and updates are untested. |
| 🟢 | Existing profiles and resources | Preserved in the original application; the bridge does not rewrite profiles. |
| 🟡 | Plugin settings / property inspector | Auto panel/Step Size and visible Output Device Control lists; shared Wine font fallback is built into installation. Manual/device actions require separate behavioral acceptance. |
| 🟢 | Notification popup rendering | User-confirmed after applying the application's native software-renderer preference; included in standard installation for the audited build. [Evidence](STATUS.md#resolved-notification-rendering-after-windows-backup-import). |
| 🟢 | Bridge installation and removal | User-only integration with reversible, scoped MIME/portal, menu and native renderer preference changes. |
| ⚪ | Stream Deck application updates | Updater behavior and compatibility after an upgrade. |

## Basic Stream Deck functions

| Status | Function | Scope / limitations |
| :---: | --- | --- |
| 🟢 | MK.2 USB/HID connection | Device access and connection through the original application. |
| 🟡 | Key images and physical buttons | Volume Controller's dynamic Auto profile; other actions require separate testing. |
| 🟡 | Profile loading | Existing profiles and dynamic Auto profile; navigation, folders and switching are not exhaustively tested. |
| 🟡 | Virtual Stream Deck | Startup window identified by the user; virtual key actions and shortcuts remain untested. |
| 🟡 | Launching native Linux applications | Allowlisted CLI/Wine handoff; physical GUI-launch action untested. |
| ⚪ | Opening allowlisted URLs | Provider implemented; physical action/browser behavior untested. |
| ⚪ | Original Wine hotkey actions | Desktop-wide shortcuts require separate testing. |
| 🔴 | Native Wayland hotkeys, text and clipboard injection | No native input backend. |
| ⚪ | Multi Actions, media keys and automatic profile switching | No functional coverage. |
| ⚪ | Other device models, dials, touchscreens and hotplug | Current device coverage is limited to MK.2. |
| 🔴 | Volume-change feedback sound | Not provided. |

## Plugins

| Status | Plugin | Version | Scope / limitations |
| :---: | --- | --- | --- |
| 🟡 | Elgato Volume Controller | `2.0.5.201` | Auto app discovery, app/System output volume, icons/text and event-stream filtering. Device lists render, but Input/Output endpoint control is unavailable in normal launches. A shared [Core Audio prototype](compat/windows/core-audio.md) passed isolated output volume/mute/restore through the original addon; ordinary activation remains pending. Hardware mute, Manual Detection and dials remain unverified. [Details and limits](compat/plugins/volume-controller.md). |
| ⚪ | Elgato Tutorial | `1.0.4.3` | No functional coverage. |
| ⚪ | Other plugins / versions | — | No universal plugin compatibility or generic Windows Core Audio implementation. |

Volume Controller uses an exact version/hash contract. Direct PipeWire streams
without Pulse handles are read-only. Settings UI requires the
[WebEngine workaround](USAGE.md#original-plugin-settings-under-wine). Protocol
limits and the startup edge with no enumerated applications are documented in the
[plugin compatibility notes](compat/plugins/volume-controller.md).
Stream Deck Icon Library is an asset bundle and is not counted as plugin support.
