# ADR 0004: shared Core Audio endpoint-volume boundary

Status: implementation in progress, 2026-11-10; ordinary device acceptance pending.

Volume Controller's application actions call Audio Router. Input/Output Device
Control instead uses its native Windows device addon. Wine enumerates devices,
but the user observes no output volume change after pressing the configured key.

The [matching Wine 11.20 source](https://github.com/wine-mirror/wine/blob/wine-11.20/dlls/mmdevapi/audiovolume.c)
returns `E_NOTIMPL` from the scalar setter, constant 1.0 from its getter, and stores
mute only in the wrapper. Read-only original-addon observations returned 1.0 on
all endpoints. No automatic mutation was used for this diagnosis.

Implement the actual endpoint-volume API under `compat/windows/`, sharing a
native device model under `backends/audio/`. Plugin UUID/version and Audio Router
translation stay under `compat/plugins/volume_controller/`. Preserve working Wine
enumeration, vendor files, profiles and session control.

A native COM bridge needs verified x64 ABI/interface ordering, QueryInterface
identity/refcounts, aggregation, threading, notifications and lifetime behavior.
Match endpoints by exact native identity, not friendly-name guesses. Keep input
and output write policy separate, preserve channel balance, reject stale handles
and never retry uncertain writes. Unsupported methods must fail explicitly.

The workstation initially lacked Windows development headers/compiler. A pinned,
hash-verified llvm-mingw bundle now supplies the isolated build environment;
the read-only x64 COM probe built with warnings-as-errors and read seven endpoints
under the actual Wine prefix. No system packages or DLL overrides were installed.
Deploy a control shim only after reversible
integration and actual-consumer acceptance. Font fallback does not imply device
control support; no empty shim or success-only API placeholder is provided.

The shared device backend and COM scalar/mute/read boundary now exist. Real
read-only factory and unchanged-addon probes reach the native service. The
probe uses process-local side-by-side activation, not persistent COM registration
or a vendor patch. Windows callbacks now have read-only/synthetic-event coverage;
the approved original-addon null-output write test also passed. Native recovery
and ordinary deployment remain gates;
unsupported APIs return errors. See [the implemented scope](../compat/windows/core-audio.md).
