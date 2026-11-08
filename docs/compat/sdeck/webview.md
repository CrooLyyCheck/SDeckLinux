# Original property inspectors under Wine

Observed: Stream Deck 7.6.1.23033, Qt WebEngine 6.11.1, Wine 11.20 Staging.
The original Volume Controller inspector contains a Step Size range (1–25), but
its renderer did not execute JavaScript under the audited normal launch.
This was an application WebEngine boundary, independent of Audio Router RPC.

## Controlled result

1. Normal launch with temporary loopback diagnostics: the browser CDP command
   responded, while renderer/document commands timed out and the inspector stayed
   blank. No vendor assets were patched.
2. The user authorized **one test only** with `QTWEBENGINE_DISABLE_SANDBOX=1`
   scoped to the original app's process environment. The original inspector
   rendered, its panel and slider were visible, the range was 1–25, and the
   displayed slider value was 13. A screenshot and boolean-only metadata remain
   private. The displayed initial value is not proof of a changed step setting.
3. The user quit the test app. The original launcher restarted normally, both
   diagnostic/sandbox-test variables were absent, and the debugger listener was
   closed. The user again observed the missing controls. No permanent workaround
   was enabled by the test.

This comparison establishes a dependency on the renderer sandbox flag in this
configuration. It does not establish a general absence of sandbox support in
Wine, nor provide a Windows sandbox implementation.

## Native window composition acceptance

The first comparison established that the original HTML could render, not that
the native application actually displayed it. The user subsequently showed the
correct main Auto action selected, with an empty native inspector area despite
the now-healthy renderer. No-sandbox mode alone was insufficient.

Adding only `QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu` to the approved launch
made the panel visible in the native window; the user confirmed the result.
This is the accepted current configuration: renderer sandbox disabled with
separate daily-use consent, plus Chromium software rendering. No Qt Quick,
global GPU, security or vendor-file setting was changed. Remote debugging is off.
Evidence is private in `webview-composition-smoke.json`.

## Built-in startup compatibility

The normal `make install` operation installs the menu integration and the built-in
Wine startup behavior. Software rendering is enabled and the WebEngine renderer
sandbox is disabled for Stream Deck. There is no separate repair installer or
mode-selection dialog. `bash install.sh` runs the same installation flow.

These defaults belong to the runtime configuration model as well as the fresh
configuration template. Older configurations that omit the WebEngine section
inherit them automatically on update. Explicit preferences are preserved.

```toml
[compat.sdeck.webview]
renderer_sandbox = false
software_rendering = true
```

The renderer isolation tradeoff is part of this built-in Wine mode: HTML plugin
pages run with the user's account permissions. To opt out, set
`renderer_sandbox = true` and `software_rendering = false`, or use
`tools/install.py --webview-mode sandboxed` with the usual prefix/apply options.
The two preferences remain independently configurable. Software rendering adds
`--disable-gpu` while preserving unrelated Chromium flags. No remote debugger is
enabled and no global security or GPU preference is changed.

## Menu and original launcher

The normal install hands the existing menu icon to `deckbridge streamdeck`.
Original menu bytes/mode are saved privately and restored on deactivation if the
entry is still managed. Modified or unowned entries are preserved. `--no-menu`
opts out or restores the menu. No autostart entry is enabled and no vendor/prefix
file is edited.

The launch helper uses the existing user-owned `streamdeck-wine` command,
retaining its Wine fixes. It validates the exact prefix and ownership marker;
unsupported layouts fail visibly. A local patch to that original command is not
required. Direct `streamdeck-wine` launches remain independent. Quit a running
instance before switching modes; the helper refuses duplicate instances.

The relevant settings are in the **original main Auto Detection or Manual
Detection action**. The dynamically generated +/- child actions do not each
implement their own property-inspector settings UI in this plugin build.

References: [Qt sandbox controls](https://doc.qt.io/qt-6/qtwebengine-platform-notes.html#sandboxing-support),
[Qt debugging controls and sandbox risk](https://doc.qt.io/qt-6/qtwebengine-debugging.html),
[Qt WebEngine graphics/software rendering](https://doc.qt.io/qt-6.10/qtwebengine-features.html).
