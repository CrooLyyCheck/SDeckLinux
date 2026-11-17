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

Optional default-output policy adds `IPolicyConfigVista::SetDefaultEndpoint`,
physical native default reads and output-default notifications. Its independent
feature/write gates and limits are described in
[ADR 0005](../../adr/0005-default-output-policy.md). Successful policy read/subscribe
frames append a bounded native-name extension; existing volume frames stay intact.
Input and Communications routing are not provided.

## Deployment boundary

The feature defaults off and requires the native audio backend. Once explicitly
enabled, standard `make install` automatically prepares the isolated pinned
compiler, builds the library and installs it with a private token and hashes.
The user daemon serves its bounded endpoint transport; no Node preload,
debugger or vendor patch is used in ordinary launches.

The single `InprocServer32` registration lives in the **owned Wine prefix's**
`HKLM\Software\Classes` hive, not in the Linux system. Wine 11.20's
[COM implementation](https://github.com/wine-mirror/wine/blob/wine-11.20/dlls/combase/combase.c)
reads that Machine hive directly; HKCU class overrides do not affect it.
Only recognized stock Wine values are taken over. A write-ahead journal and
verified registry backups preserve exact original strings. Opt-out/deactivation
restores them; custom user registrations are preserved. With the feature enabled,
an update repairs an exact return to recorded stock values. The library delegates
to Wine's system32 factory and is never copied over a Wine DLL.

Actual registered COM reads, factory rollback/reapply and callback recovery after
daemon restart passed without audio setters. The user confirmed output volume
through both a named Virtuoso endpoint and Default. Input hardware, physical mute
and dials remain unverified. The probe-only Node activation bootstrap remains
isolated from ordinary installation.

## Responsiveness

Recent process IDs are lookup hints only: every connection still checks current
kernel socket ownership, UID, prefix and mapped-library inode/path. A 250 ms read
snapshot is invalidated by native sink/source/server events. One pending refresh
coalesces event bursts; write selection and post-write observations bypass this
cache. Setters preserve all fresh backend checks and never replay on reconnect.
Default writes fail if the selected endpoint ceases to be the native default.

The read-only COM comparison on 2026-11-17 improved from 3332.3 to 562.1 ms for
30 reads, reducing native commands from 120 to four. This measures the API probe,
not physical button latency. After restarting the app to load the repaired COM
factory, the user confirmed the same output key worked and reacted faster.
Cached authorization decisions are never used.

## Verification

```bash
make check
make native-core-audio native-probe
.venv/bin/python tools/core_audio_smoke.py
.venv/bin/python tools/core_audio_smoke.py --simulate-notifications
.venv/bin/python tools/core_audio_smoke.py --installed
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
