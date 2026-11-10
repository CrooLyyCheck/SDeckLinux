# Verification and acceptance

## Default: hardware-free

`make setup` creates the local development environment. `make check` runs Ruff
format/lint, Python byte compilation and unittest discovery. Tests use temporary
configuration/installer trees, real local Unix sockets and a deliberately hung
Python helper that must be killed and reaped at the test deadline. They do not
start Wine, touch the real prefix, press buttons, inject input or alter audio.
Audio tests cover grouping, stale identities, write policies, scalar units,
events, fixture ownership and real ephemeral WebSocket framing. Transport tests
mock process identity; separate real-process acceptance is recorded in STATUS.

Provider mocks verify the Wine argv/allowlist contract only. They are not evidence
of Wine, Wayland or physical hardware functionality.

## Explicit real-host observations

Start the original application through its existing `streamdeck-wine` launcher.
Use `deckbridge diagnose` to check the exact-prefix instance, handler, private
socket-backed service and HID access. This diagnostic does not test button input.

Read kernel HID identity only:

```bash
python3 tools/smoke.py inspect-hardware
```

This opens the sole connected MK.2 read-only and issues `HIDIOCGRAWINFO`. It never
reads input reports, writes reports, changes the display, detaches a driver or
changes permissions. It is not a full hardware smoke test.

Test passive synthetic browser-to-application URI transport:

```bash
python3 tools/smoke.py deep-link --app-log \
  "$HOME/.local/share/streamdeck-wine/prefix/drive_c/users/$USER/AppData/Roaming/Elgato/StreamDeck/logs/StreamDeck.log"
```

The prefix/log path shown is the audited workstation's path; pass the actual app
log inside the configured prefix. This sends exactly one synthetic deep-link to
an intentionally absent `io.deckbridge.probe` plugin. It checks a fresh `openFile`
receipt, the unchanged main PID, reserved escapes and Unicode in Elgato's log,
without printing or saving unrelated log contents. It does **not** claim plugin
receipt or OAuth completion.

The log observer has a documented 10-second receipt deadline and 100 ms sampling
interval, configurable via `--deadline` and `--poll-interval`. Sampling never
retries the callback. The workstation exhausted the per-user inotify instance
limit (128, `EMFILE` with only five process FDs); bounded log sampling is used
without modifying global sysctls. Log rotation during the test fails explicitly.

## Native process receipt

`tools/native_probe.py --receipt ABSOLUTE_PATH` is a harmless headless native
application fixture. It exclusively creates a private JSON receipt with its
observed `/proc/self/exe`, UID and ELF magic result. It refuses to overwrite an
existing receipt. A temporary explicit mapping can point to:

```toml
[applications]
native-smoke = ["/usr/bin/python3", "/ABSOLUTE/DeckBridge/tools/native_probe.py", "--receipt", "/ABSOLUTE/private-test-directory/receipt.json"]
```

After restarting the daemon, invoke `deckbridge launch native-smoke`, inspect the
receipt, remove that owned test receipt, then repeat through the original Wine
Unix launcher in the audited prefix:

```bash
WINEPREFIX="$HOME/.local/share/streamdeck-wine/prefix" \
  WINEDLLOVERRIDES='winemenubuilder.exe=d' WINEDEBUG=-all \
  wine start /unix "$HOME/.local/bin/deckbridge" launch native-smoke
```

Restore the private configuration and restart the daemon after testing. The
recorded workstation result proved native ELF execution through both paths.
A physical Stream Deck action and a native GUI application's behavior need their
own manual observation. Opening a real browser URL also requires an explicit
interactive test; it is not exercised by the default suite.

## Interactive OAuth and MK.2 regression

1. Keep DeckBridge running during the full callback flow. In the original app,
   start Marketplace login and complete the browser/password/MFA steps yourself.
   Confirm the account becomes linked in the **original app**. Do not paste a
   callback URI, code, state or token into chat or shell history.
2. Verify the device displays the existing profiles. In the pre-existing **Wine
   Test** profile, press only **Linux OK**, observe the native KDE dialog and
   dismiss it yourself. This is a regression test of the existing explicit action.
3. For new bridge-native acceptance, add a separate System → Open action pointing
   at a dedicated `.cmd` that calls one configured alias, then press that key and
   observe the chosen native app. Back up the affected prefix files first; do not
   edit active profile JSON externally.
4. For future keyboard tests, prepare a harmless native KDE editor document and
   obtain consent before Ctrl+A/C/V or text injection. Test Polish Unicode and
   modifier release on failure. Those providers are not implemented yet.

Hardware display/button checks and user-reported results must be identified as
such in STATUS. Never infer them from USB detection or a zero exit status.

## Explicit audio fixture and Volume Controller acceptance

`deckbridge audio list` is read-only. Do not run volume/mute commands against
ordinary application keys as an incidental check. Keep writes disabled or
restricted to `app:io.deckbridge.audio-test` while preparing a test; enabling
normal use does not authorize automated real-app volume tests.

After explicit authorization, enable audio/the adapter using the README tables
and allow writes only to that fixture key. Start the bounded silent fixture in
a separate terminal, or an independent transient user unit:

```bash
systemd-run --user --collect --quiet --service-type=exec \
  --unit=deckbridge-audio-fixture --property=RuntimeMaxSec=1800 \
  "$PWD/.venv/bin/python" "$PWD/tools/audio_smoke.py" hold-fixture --duration 1800
```

This creates an owned low-priority hidden null sink, checks that default devices
did not change, then feeds zero samples through an explicitly targeted `pacat`
stream. It never changes a sink volume or the default device. Graph links must
stay within the fixture and its null sink before a volume test; unexpected links
cause a failure before mutation. Starting a stream with no sink was observed to
time out, so an unlinked pacat is not a valid long-lived fixture.

Read the unit status and `deckbridge audio list`; wait past the earlier timeout
and confirm the original plugin is connected/enumerated in `deckbridge diagnose`.
Only then tell the user **test ready now**, with one exact button and target.
The plugin dynamically builds columns in **Volume Controller (Auto)**. Do not
edit active profile JSON or instruct the user to create a fixed test column.

With separate consent for the fixture-only 25% → mute → restore sequence:

```bash
.venv/bin/python tools/audio_smoke.py exercise --approved
```

The flag is a deliberate execution guard, not a substitute for consent. The
helper verifies the exact fixture, observes volume/mute, restores its original
values and compares surviving streams, sinks and default devices around that
exercise. It preserves earlier successful evidence if a later run stops before
mutation. Record physical-button evidence separately: snapshot the fixture and
other audio state immediately before the prompt, let the user press one short
Volume Down and inspect actual Pulse/PipeWire values. Scalars on the vendor
protocol are 0..1: a five-point step at 1.0 must yield approximately 0.95, not
0.0095. Do not automatically repeat or infer mute/other-model acceptance.

Stop and remove only the owned scaffolding when finished:

```bash
systemctl --user stop deckbridge-audio-fixture
```

The helper terminates/reaps its child, removes its unchanged private descriptor
and unloads only the module still associated with its unique sink and server
cookie. User-changed ownership blocks removal. The null sink/stream disappear
from the dynamic profile; they are not persistent product configuration.

The recorded workstation test authorized fixture mutations, then separately
authorized normal button-driven app control. Preserve that distinction in future
sessions. No automated real-app or global-volume tests were performed.

## Core Audio endpoint development probes

For the separate Input/Output Device Control boundary, see the
[Core Audio probe scope](compat/windows/core-audio.md#verification). Its default
COM run is read-only; simulated notifications change only memory-held models.
Original-addon fixture setters require separate explicit consent for the null
output, even when the existing stream fixture was previously approved. Neither
probe establishes physical IO key/dial acceptance or enables the normal loader.

## Explicit WebEngine inspector comparison

Do not infer property-inspector support from successful Audio Router RPC. The
audited blank inspector was isolated with a separately authorized **one-off**
renderer sandbox comparison. Normal launch stalled renderer document commands;
the original inspector and Step Size 1–25 slider rendered in the approved test.
The app was then quit and relaunched normally; the test/debug environment was
absent and the loopback debug listener closed. The user again saw blank controls. Later, after separate daily-use consent,
renderer startup worked but the native widget was still blank. Adding only
Chromium software rendering (`--disable-gpu`) made it visible and the user
confirmed it. A CDP screenshot alone must not be treated as native-widget acceptance.

`make check` does not run Wine or this comparison. Everyday `deckbridge streamdeck`
now uses the built-in Wine mode: software rendering with the renderer sandbox off.
For an explicitly sandboxed control, use the documented sandboxed override rather
than assuming a normal launch restores the historical defaults. Quit a running
instance before changing its environment and restore the previous preferences
after a controlled comparison. See the
[exact scope and result](compat/sdeck/webview.md).

Native surface preference tests use a synthetic registry and executable hash;
they never execute Wine. They check backup/journal ordering, exact typed rollback,
interrupted writes, opt-out, user overrides and unsupported builds. Real-host
notification acceptance is separately recorded in [STATUS.md](STATUS.md#resolved-notification-rendering-after-windows-backup-import),
including the distinction between notification rendering and the legitimate
Virtual Stream Deck window. Virtual key actions are not covered by that observation.

A delayed human Quit must be observed using the exact main PID/start identity;
transient matching Wine helpers must not be mistaken for the main exiting.
The initial ad-hoc observer aborted on such a transition and the app had to be
started explicitly. The corrected cleanup watched the exact main, allowed its
helpers to finish, and then started the normal launcher. Do not advertise an
automatic restart as completed before observing the returned app and flags.

## Rollback regression

Run outside an ongoing OAuth flow:

```bash
python3 tools/install.py --deactivate
python3 tools/install.py --deactivate --apply
xdg-mime query default x-scheme-handler/streamdeck
streamdeck-wine
```

Confirm the previous MIME default, unchanged original profiles/launcher and MK.2
behavior. Reinstall with the same explicit `--prefix ... --apply` to restore
DeckBridge. The temporary-tree installer tests cover idempotence, modified-file
preservation and scoped MIME restoration; real-host deactivation must be reported
separately and must not interrupt an interactive login test.
