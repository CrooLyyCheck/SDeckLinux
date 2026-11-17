# Audio Switcher / Audio Devices 3.2.0.90

Consumer UUID: `com.fredemmott.audiooutputswitch`, author Fred Emmott.
The installed unmodified executable, manifest and inspector hashes are recorded
in `compat/plugins/audio_switcher/contract.json`. This is audit metadata, not a
plugin-specific service or a claim of GUI acceptance.

The installed action category is **Audio Devices**. Set Audio Device uses
`com.fredemmott.audiooutputswitch.set`; Toggle Audio Device uses `.toggle`.
The inspected v3.2.0 source pins AudioDeviceLib commit
`fb7b31b42d331480dce766c83230c905fbb1e540`. Its Windows path calls
[`IPolicyConfigVista::SetDefaultEndpoint`](https://github.com/fredemmott/AudioDeviceLib/blob/fb7b31b42d331480dce766c83230c905fbb1e540/src/AudioDevicesWindows.cpp)
with `eConsole` for Default and `eCommunications` for Communications. Default
state updates arrive through `IMMNotificationClient::OnDefaultDeviceChanged`.

## Implemented boundary

Implementation belongs to shared `compat/windows/core_audio/` and native
`backends/audio/defaults.py`. The plugin executable, inspector, icons and profiles
are unchanged. The first scope is **Output → Default**. Console and Multimedia
share the native output default. Input and Communications setters return explicit
unsupported errors; other policy-format/property/visibility methods also fail.
Toggle uses the same upstream setter but has no separate acceptance yet.

The optional policy class is installed by standard `make install` when
`[compat.windows.core_audio] default_output = true`. It requires Core Audio to be
enabled. `[audio] allow_default_output_write` is separate and defaults false;
volume/mute permissions do not enable routing. `allowed_default_outputs` restricts
exact current native output IDs. Policy toggles/native-library updates require a
full app restart so existing callback registrations are recreated.

Actual native defaults are returned as physical Windows endpoints through exact
Wine GUID/native-name mapping. A native output-default subscription supplies
Console/Multimedia notifications. Wine continues to supply other device events.
No registry default-device value is written on a button press.

The shared read-only property store also supplies the current native friendly
name. Per-node monitor nicknames lead GPU/controller descriptions. Each endpoint
is resolved separately by exact identity; shared GPUs or duplicate display labels
do not merge devices. The synthetic multi-port test does not establish real
multi-monitor acceptance. Default aliases/missing metadata keep Wine names.
The user confirmed LG appears once and the retained unavailable entry no longer
contains repeated Speakers wrappers. Unavailable entries stay unavailable; the
bridge does not delete saved selections or rewrite the plugin's settings.

## Evidence and limits

- Real x64 COM factory/interface identity and lifetime checks pass under Wine.
- A read-only probe identifies the native physical default; no setter is invoked.
- The memory-only probe changes its synthetic default, reads the selected device,
  receives the matching Windows notification and restores the model. Input and
  Communications writes are denied. Native defaults remain unchanged, with zero
  host setter calls.
- The new prefix-local policy registration was applied/read back and removed,
  restoring its original absence. Unknown user registrations are preserved.
- With separately authorized manual testing, the original Set Audio Device key
  switched Output / Default to the selected current Virtuoso Wireless output.
  The user confirmed success; native readback matched, with one bridge write and
  zero rejected requests. The update itself performed no routing change.
- Toggle, switching back and independent key-indicator behavior remain untested.
  Input and Communications routing remain unsupported. Simulation alone is not
  hardware evidence.

Changing the native default can affect streams following that default, according
to the host's policy. The backend uses an explicit, revalidated Pulse handle and
[`pactl set-default-sink`](https://wiki.freedesktop.org/www/Software/PulseAudio/Documentation/User/DefaultDevice/).
It does not issue stream-move, microphone or volume/mute commands. A real routing
test needs its own consent; previous fixture-volume approval does not cover it.
