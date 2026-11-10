# Core Audio endpoint volume (experimental)

The shared Windows API boundary is `compat/windows/core_audio/`; native device
models and policy live in `backends/audio/devices.py`. Neither uses Volume
Controller's JSON-RPC fields. The original application/plugins remain unchanged.

## Implemented slice

- Native input/output inventory with server-cookie/serial identities, exact names,
  independent write gates, channel balance, revalidation and verified readback.
- `CLSID_MMDeviceEnumerator` class factory and wrappers for enumeration,
  collections, devices and `IMMEndpoint`, preserving COM `IUnknown` identity.
  Properties, states, device IDs and other activation interfaces delegate to Wine.
- `IAudioEndpointVolume` / `Ex`: scalar master-volume and mute get/set, channel
  count/scalar reads and software-only hardware-support reporting.
- Endpoint callback registration/removal, bounded callback lists, balanced COM
  references and notifications outside registration locks. Setter event-context
  GUIDs reach subscriptions for the exact endpoint, including default aliases;
  external native changes use `GUID_NULL`. The corresponding Pulse event is
  deduplicated. Read-only reconnection resynchronizes state without replaying setters;
  recovery stops after six failed attempts rather than retrying indefinitely.
- Exact Wine 11.20 `winepulse.drv` endpoint GUID mapping, including the two
  empty-name aliases that follow native defaults. No friendly-name matching.
- Versioned, bounded native RPC with kernel socket ownership, exact prefix and
  mapped-library attribution. A private 32-byte sidecar token authenticates the
  server before endpoint names are sent. No arbitrary command endpoint or logs
  containing payloads/tokens are provided. This is not a sandbox against the
  same user's compromised account.

The Linux service has event-driven subscription frames from `pactl subscribe`.
The private wire format is `DBA2`: a 32-byte header, at most 4096 UTF-8 name bytes,
and 292-byte state replies. Each finite transaction has an absolute three-second
native network deadline. Callback transport has bounded frames and cancellable waits.
dB/range/step and channel-write APIs return explicit unsupported errors.
These limits prevent treating the library as complete Core Audio support.

## Deployment boundary

Normal installation does **not** register this COM replacement or preload it
into the original application. The native library is built only by the optional
developer target. The probe's Node-API bootstrap uses a thread-local activation
context in its own Windows process; it changes no persistent COM registration.
It is not a production loader and does not cover other threads automatically.

Before ordinary plugin activation, validate native recovery, implement reversible
loader/service deployment, and complete actual key/dial acceptance. Native C
source, compiler and test artifacts are not copied into a Wine system directory.

## Verification

```bash
make check
make native-core-audio native-probe
.venv/bin/python tools/core_audio_smoke.py
.venv/bin/python tools/core_audio_smoke.py --simulate-notifications
```

`make check` never runs Wine or audio mutations. The explicit smoke builds on
bounded registry backups and reads endpoints through the real x64 COM factory.
The initial run read nine endpoints including the isolated fixture. After that
fixture expired, the current callback-capable run read seven endpoints, verified
seven device/endpoint identity and callback registration/removal checks, balanced
object lifetimes, and made 21 read requests with zero writes. A separate read-only probe loaded
the unchanged Volume Controller native addon through the same COM activation
context and received the actual levels. This establishes the API read path,
not physical button acceptance. The simulated-notification run also delivered a
real Windows `OnNotify` callback using synthetic endpoint levels held only in
Python memory. It invoked no host setter and is not native audio-mutation evidence.
Hardware-free tests cover context GUID propagation, native external-change events,
deduplication, rejected registration after monitor loss, and policy failures.

The callback reference/lifecycle contract follows Microsoft's
[registration](https://learn.microsoft.com/en-us/windows/win32/api/endpointvolume/nf-endpointvolume-iaudioendpointvolume-registercontrolchangenotify)
and [notification](https://learn.microsoft.com/en-us/windows/win32/api/endpointvolume/nf-endpointvolume-iaudioendpointvolumecallback-onnotify)
interfaces. Client callbacks must remain nonblocking, as specified by the
[callback contract](https://learn.microsoft.com/en-us/windows/win32/api/endpointvolume/nn-endpointvolume-iaudioendpointvolumecallback).

The fixture-write option is a separate opt-in:

```bash
.venv/bin/python tools/core_audio_smoke.py --exercise-fixture --approved
```

Use it only after explicit user approval and preparation of the existing isolated
silent fixture. It calls the **original addon** setters, binds the selected
Windows GUID to that exact null output and allows no other device writes. It
checks 25%, mute, restoration and surviving unrelated audio/defaults. It does
not imply that a key in the normal application is already connected.

The approved run passed all of those checks through the unchanged Windows addon:
four write requests, 33 reads, exact native restoration, and unchanged surviving
unrelated audio/default devices. The temporary null output was removed afterwards.
This verifies output scalar/mute control on an isolated native device, not input
hardware or a physical key in the ordinary application.
