# ADR 0005: shared default-output policy

Status: implemented behind opt-in gates; original Set Audio Device output/default
switch accepted, 2026-11-17.

Audio Switcher 3.2.0.90 uses `IPolicyConfigVista::SetDefaultEndpoint`, rather than
Volume Controller's Audio Router protocol. Its observed ABI comes from the
[pinned AudioDeviceLib header](https://github.com/fredemmott/AudioDeviceLib/blob/fb7b31b42d331480dce766c83230c905fbb1e540/src/PolicyConfig.h).
The generic boundary therefore belongs in shared Core Audio, not a plugin adapter.

The first supported operation sets the native output default for Console or
Multimedia. Communications and capture setters are explicitly unsupported. The
native backend has independent routing permission, an optional exact-ID allowlist,
fresh server/serial/index/default revalidation and verified readback. Uncertain
commands are never retried or automatically reversed.

Policy installation owns only its absent prefix-local COM registration, separately
from the existing MMDevice class. Write-ahead state and bounded registry backups
support interrupted installation and opt-out. User overrides are preserved; no
vendor or Wine DLL file is replaced.

MMDevice default reads resolve the native physical output by exact name/flow.
The native subscription supplies Windows Console/Multimedia default-change
notifications while the Wine proxy preserves other device events. This avoids
writing Wine default-device preferences on each operation and remains consistent
with native desktop default changes.

The existing `DBA2` state frame remains unchanged. New policy operations are 4
(set output default), 5 (read default) and 6 (subscribe to default). Successful
5/6 responses append a little-endian byte length and at most 4096 UTF-8 native-name
bytes. Existing volume/mute clients continue using their original framing. The
policy feature defaults off and disabled operations fail before host commands.

Wine COM read and memory-only mutation/notification tests do not establish real
routing acceptance. After separate consent and installation, the user pressed the
original Set Audio Device key and confirmed switching to Virtuoso Wireless;
native default readback matched. Toggle, reverse switching and independent key
indicator behavior remain unverified. Levels and microphone permissions remain
separate.
