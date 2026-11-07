# Verification and acceptance

## Default: hardware-free

`make setup` creates the local development environment. `make check` runs Ruff
format/lint, Python byte compilation and unittest discovery. Tests use temporary
configuration/installer trees, real local Unix sockets and a deliberately hung
Python helper that must be killed and reaped at the test deadline. They do not
start Wine, touch the real prefix, press buttons, inject input or alter audio.

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
