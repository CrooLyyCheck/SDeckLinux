# ADR 0002: implement the observed Volume Controller Audio Router boundary

Status: accepted, 2026-11-08. Scope: `com.elgato.volume-controller` 2.0.5.201.

## Problem and evidence

The original plugin installs and connects to the Stream Deck SDK after the
Marketplace OAuth fix. Its unmodified readable JavaScript invokes a separate
JSON-RPC 2.0 Audio Router service at `ws://127.0.0.1:1844`. The service is absent
in this Wine installation; the plugin reports connection refusal. Its separate
`winAudioDeviceService.node` imports Windows device APIs and already enumerates
Wine devices in a real read-only Windows Node probe. The installed manifest is
not plaintext JSON and was not decoded. UUID/version came from the actual SDK
launch metadata; the service contract came from the readable client and live
requests, not from guessing the manifest.

## Options and decision

1. Keep Wine's existing device API behavior. This works for the native device
   addon but cannot supply the missing application-session service.
2. Add a generic Windows Core Audio COM shim. This would require an ABI-correct
   implementation, COM lifetime/threading work and the missing service that
   consumes it. It is not the boundary this client's application actions call.
3. Implement only the observed, version-pinned Audio Router service, backed by an
   independent Linux audio provider. **Selected**: it enables unchanged original
   plugin behavior without a DLL override, vendor patch or new UI.

The reusable backend owns no plugin wire fields. A future generic API shim can
reuse its host model; it must be justified by an actual Windows API consumer.
This adapter does not imply support for arbitrary Core Audio plugins.

## Consequences

The fixed loopback endpoint is required by the unchanged client. Since it has no
credential field, authentication attributes the established kernel socket to the
same-user, exact-prefix, hash/version-pinned Windows Node plugin process. Browser
Origins and unmatched peers are rejected. This cannot defend against a process
already controlling the user's account. The normal host IPC remains a private
Unix socket. Both features are separately disableable and off by default.

Use maintained `websockets` 17.4 for bounded RFC 6455 framing/handshake/close
handling instead of introducing a custom parser. Its portable pure-Python wheel
is URL/SHA256 pinned, prepared locally and hash-tracked in the installed runtime;
there is no global package installation. Library frame/header logs are replaced
with fixed metadata to protect payloads.

PipeWire supplies graph observation and identity; PipeWire-Pulse supplies scoped
sink-input control. Direct PipeWire-only streams remain visible/read-only.
Control is limited to 0..1 scalars, channel balance is retained, stale identities
are rejected, global writes are unavailable and mutations are never retried.
The subprocess control path has a small non-atomic check/use window. Unsupported
builds fail closed by hash/version rather than inheriting an unverified contract.

## Validation

The original Windows Node client connected, enumerated Helium, Flatpak Fluxer
and the temporary native test stream, and reacted to stream addition/removal.
The user confirmed the dynamic MK.2 profile and physical control. After correcting
the adapter's initial percentage/scalar mistake, a single physical Volume Down
changed the native test stream from 1.0 to 0.9499969482421875 (95% within one Pulse
unit). Native volume/mute/restore CLI observations passed on that fixture.
No automated volume changes were made to other applications. Broader normal
application control was enabled only after the user's separate authorization.

References: [PipeWire null sink](https://docs.pipewire.org/page_pulse_module_null_sink.html),
[WirePlumber priority selection](https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/priorities.html),
[PipeWire 1.6.10 Pulse volume conversion](https://github.com/PipeWire/pipewire/blob/1.6.10/src/modules/module-protocol-pulse/message.c).
