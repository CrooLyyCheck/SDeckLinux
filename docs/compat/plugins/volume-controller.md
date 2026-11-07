# Elgato Volume Controller 2.0.5.201

UUID: `com.elgato.volume-controller`. Mode: **plugin-adapter**, with partial
functional acceptance. The automatic MK.2 profile discovers Linux apps and a
physical volume adjustment passed on a real native test stream. Device actions,
manual detection, dials and all hardware variants are not fully accepted.

## Files and boundaries

`deckbridge/compat/plugins/volume_controller/contract.json` pins the readable
entrypoint and native device addon hashes. `peer.py` verifies the installed build
and the connecting process; `protocol.py` maps its observed service contract;
`server.py` supplies the bounded WebSocket transport. Reusable host behavior is
in `deckbridge/backends/audio/`. Stream Deck authorization transport is separate
in `deckbridge/compat/sdeck/oauth/`.

Vendor JavaScript/addon binaries are neither modified nor distributed here. The
25,760-byte manifest is not plaintext JSON; no protected packaging was decoded.
The version is confirmed by the running client's SDK metadata. A generic manifest
scanner remains future work; the pinned contract is not a universal registry.

## Observed Audio Router contract

Endpoint: `ws://127.0.0.1:1844/`, JSON-RPC 2.0, integer request IDs. All volume
values are **0..1 scalars**, including events. The original client's adjustment
logic adds percentage points divided by 100. CLI percentage arguments are not
the vendor wire format.

| Method | Params | Result/behavior |
| --- | --- | --- |
| `getApplicationInstanceCount` | omitted/empty | `{count}` |
| `getApplicationInstanceAtIndex` | `{index}` | Current application |
| `getApplicationInstance` | `{processID}` | Current application or gone error |
| `getApplicationInstanceImage` | `{processID,imageSize}` | Null image; original client renders its fallback |
| `getSystemDefaultDevice` | omitted/empty | Read-only `{volume,mute}` |
| `setApplicationInstanceVolume` | `{processID,volume}` | Scoped backend write, subject to local write policy |
| `setApplicationInstanceMute` | `{processID,mute}` | Scoped backend write, subject to local write policy |
| `setSystemDefaultDeviceVolume/Mute` | any | Rejected: `global_audio_control_disabled` |

Application results contain `processID`, `displayName`, `executableFile`, `volume`,
`mute`, `activity`. IDs are connection-local, positive synthetic IDs; zero is
reserved for System. They never impersonate host/Flatpak PIDs. `executableFile`
is `deckbridge-audio:<application-key>`, so saved selections do not depend on
ephemeral node/PID values. Writable Pulse-backed presence maps to activity 2;
native-only read-only presence maps to activity 4. This is stream presence,
not audio-energy detection or a long-term recent-app cache.

Observed notifications implemented:

- `appInstanceAddRemove`: `{processID,appAddedRemoved:"Added"|"Removed"}`.
- `preferredSessionInstanceVolumeChanged`: `{processID,volume}`.
- `preferredSessionInstanceMuteChanged`: `{processID,mute}`.
- `appInstanceActivityChanged`: `{processID,activity}`.
- `currentSystemDefaultDeviceVolumeChanged` / `currentSystemDefaultDeviceMuteChanged`:
  read-only system observations with processID zero.

Unknown methods are errors, not success-shaped placeholders. The service does
not implement arbitrary device routing, polling controls or system mutators.
It accepts text frames up to 16 KiB, rejects browser Origins, limits queues and
uses bounded handshake/close times. Failed audio notifications close the client
with a fixed reason rather than leaving a silently stale session. The original
client reconnects after service updates; allow its own backoff (observed up to
about 30 seconds), without restarting Stream Deck or replaying actions.

## Acceptance and limits

- Actual original client, matching pinned build/prefix/socket owner: connected
  and enumerated Helium, Flatpak Fluxer Canary and `DeckBridge Test`.
- Dynamic Auto profile: user observed test column and physical buttons.
- Corrected physical test: one short Volume Down, 100% → 95.00%, measured on the
  exact native Pulse stream; unrelated surviving app streams unchanged.
- CLI: 25%, mute and restoration observed on the silent fixture. The immediate
  CLI window preserved sink volumes/default devices.
- A longer fixture-lifetime comparison observed a system sink change from 64%
  to 69%; its source was not attributed. No global setter exists in the adapter,
  and no attempt was made to overwrite desktop changes. Do not claim the whole
  interactive window preserved global volume.
- Initial unlinked `pacat` fixture timed out and disappeared from the dynamic
  profile. Replaced with a silent stream into an owned low-priority null sink;
  no manual profile editing. Fixture/sink were removed after acceptance. The
  helper checks graph isolation before a test; a later external monitor link
  correctly caused another invocation to stop before any mutation.
- User authorized normal control of other apps after the fixture test. This
  enables button-driven use; it is not evidence of automated tests on those apps.
- Global/device controls are outside the bridge; the original device addon
  retains Wine behavior. Generic Core Audio, custom native icons, manual actions,
  hardware mute and other models/dials need separate acceptance.

See [TESTING](../../TESTING.md) for opt-in commands and
[ADR 0002](../../adr/0002-volume-controller-service-adapter.md) for the design.
