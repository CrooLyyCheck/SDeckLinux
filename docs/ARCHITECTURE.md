# Architecture

## Current boundaries

```text
Linux browser / explicit original Stream Deck Open action
  -> XDG streamdeck:// handler / Wine start /unix
  -> DeckBridge CLI (desktop URI ingress or named native target)
  -> v1 JSON-lines IPC over a same-user Unix socket
  -> systemd --user DeckBridge daemon
       -> Wine StreamDeck.exe URI handoff to the existing exact-prefix instance
       -> allowlisted native argv or URL through a transient systemd user service
```

`StreamDeck.exe`, its SDK WebSockets, device handling and installed plugins remain
under Wine. Standard Wine remains the first compatibility provider. No DLL
overrides, plugin patches, WebSocket interception or replacement UI are added.
The existing launch environment (`WINEARCH=win64`, disabled `winemenubuilder`)
and prefix-local Liberation Sans font fix remain intact.

## Implemented components

| Component | Responsibility |
| --- | --- |
| `deckbridge.uri` | Validate opaque URIs; repair KDE's decoded spaces/Unicode only at desktop ingress |
| `deckbridge.config` | Private v1 TOML, exact Wine paths, individually enabled mappings |
| `deckbridge.protocol` | Bounded typed request envelope and fixed error codes |
| `deckbridge.client` / `server` | Framing, peer UID, deadlines, disconnects and explicit reconnection |
| `deckbridge.wine` | Match executable plus `WINEPREFIX`, hand off only with exactly one main process |
| `deckbridge.providers` | Concrete `oauth.deepLink`, `desktop.launch`, `desktop.openUrl` dispatch |
| `deckbridge.diagnostics` | Read-only component and HID visibility observations |
| `tools/install.py` | Hash-tracked user integration and scoped MIME restoration |
| `tools/smoke.py` | Explicit real-host observations, excluded from `make check` |

`oauth.deepLink` means transport for the complete URI, including application
callbacks. It reports `forwarded-unconfirmed`; this is not an OAuth completion
signal. Elgato's own single-instance mechanism is responsible for dispatch after
Wine starts the forwarding helper. A disappearing instance produces an error;
there remains a process-exit race between observation and launch.

KDE 6.7.5 `%u` was observed to decode `%20` and UTF-8 Unicode while preserving
reserved escapes. The desktop-only `handle-uri` command encodes those characters
again, preserving `%`, `+`, delimiters and existing escapes. It does not unquote
the URI. Exact original escape spelling for already decoded unreserved characters
cannot be recovered from KDE; semantic URI contents are preserved. The ordinary
`deep-link` CLI preserves its supplied encoded URI exactly.

## Security and lifecycle

The socket is `$XDG_RUNTIME_DIR/deckbridge/control.sock`, with directory `0700`,
socket `0600` and `SO_PEERCRED` UID validation. A held `flock` prevents a second
daemon from unlinking a live socket. Arbitrary pre-existing files and symlinks
are rejected. This is a same-user service boundary, not a sandbox against plugins
already running as that user under Wine.

Only three concrete actions exist. Native targets and URLs are fixed in the
private local configuration; request payloads cannot supply commands, arguments,
desktop IDs or arbitrary URLs. Transient `Type=exec` user services avoid killing
native applications when DeckBridge stops. Environment expansion is disabled,
descriptions are fixed, and their standard output/error are discarded.

Logs contain fixed events/codes and server-generated correlation IDs, never URI
payloads or subprocess output. Core dumps are disabled for the installed service.
The original application may write received URLs into its own private logs;
DeckBridge does not control that logger. Do not collect those logs around real
OAuth flows without redaction. URI argv is also visible to same-user process
inspection, as with ordinary desktop protocol handlers.

No callbacks are automatically retried or queued. A disconnect/timeout can mean
the action already happened. Clients reconnect for a new explicit request; users
must restart an OAuth flow rather than replay an old authorization code.

## Expansion boundaries

The contract uses capability names, versions and capability-specific arguments;
providers return fixed errors and distinguish transport acceptance from observed
behavior. Only implemented capabilities are advertised. Event subscriptions are
explicitly unavailable in v1; no polling bus or placeholder event framework exists.

Future providers must be based on observed needs:

| Capability family | Required boundary before implementation |
| --- | --- |
| `input.hotkey`, `input.text` | KDE RemoteDesktop/portal and libei consent, Unicode/layout semantics, modifier release |
| `clipboard.read/write` | Wayland selection ownership and explicit consent/privacy model |
| `audio.sessions.list`, `audio.session.volume/mute` | PipeWire stream identity vs logical applications and vanished-stream errors |
| `media.player.control` | Actual MPRIS service capabilities and lifecycle |
| `applications.monitor`, `windows.observe` | KDE/Wayland visibility and permission constraints |

A generic Win32 shim requires real API tracing, correct ABI/architecture,
threading/reentrancy, COM lifetime where relevant, and comparison with current
Wine. The Stream Deck SDK is not a universal Windows API boundary. Per-plugin
adapters need an observed, versioned protocol and a selective switch.

Plugin compatibility evidence will be keyed by UUID **and version**, with states
`native-wine`, `generic-bridge`, `plugin-adapter`, `unsupported`, `untested`.
Launching alone is insufficient. Manifest metadata does not prove API dependencies.
There is no automatic telemetry upload.

## References

- [Elgato deep-link contract and passive callbacks](https://docs.elgato.com/streamdeck/sdk/v1/guides/deep-linking/).
- [Desktop Entry Exec field codes](https://specifications.freedesktop.org/desktop-entry/latest-single/).
- [systemd-run exec semantics](https://freedesktop.org/software/systemd/man/latest/systemd-run.html).
- [Linux hidraw identity ioctl](https://www.kernel.org/doc/html/latest/hid/hidraw.html).
