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

## Explicit launch option

The default remains sandboxed:

```bash
deckbridge streamdeck
```

The command uses the existing user-owned `streamdeck-wine` launcher, retaining
its Wine fixes and foreground lifetime. It verifies the configured audited
prefix and ownership marker; other installer layouts fail visibly. Quit an
existing instance first. The command refuses to silently change the environment
of a running app. It does not edit the original launcher, prefix, registry,
plugins, desktop entries or system environment.

Only after explicitly accepting the renderer isolation tradeoff, a launch can use:

```bash
deckbridge streamdeck --no-webview-sandbox --software-webview
```

Alternatively a deliberate private host preference makes that mode apply when
using `deckbridge streamdeck`:

```toml
[compat.sdeck.webview]
renderer_sandbox = false
software_rendering = true
```

Both preferences are optional: `renderer_sandbox` defaults to `true`,
`software_rendering` to `false`. Set sandboxing back to `true`, quit the app and
launch normally to restore it. Software rendering is independent and adds only
`--disable-gpu`, preserving unrelated existing Chromium flags. A per-launch
`--software-webview` option is also available. Existing `streamdeck-wine` launches
remain independent of this DeckBridge-only preference. The helper does not
enable remote debugging. It preserves unrelated environment/Wine fixes and
rejects an external `--no-sandbox` override when sandboxed mode was requested.

Disabling the renderer sandbox removes an isolation layer for HTML plugin pages
inside that app; those pages run with the user's account permissions. A one-off
diagnostic authorization is not permission to enable that mode for daily use.
After the concluded one-off test, the user separately authorized daily use via
`deckbridge streamdeck`. The audited workstation now has the two preferences
shown above enabled. Future starts must use that command to apply them.

The relevant settings are in the **original main Auto Detection or Manual
Detection action**. The dynamically generated +/- child actions do not each
implement their own property-inspector settings UI in this plugin build.

References: [Qt sandbox controls](https://doc.qt.io/qt-6/qtwebengine-platform-notes.html#sandboxing-support),
[Qt debugging controls and sandbox risk](https://doc.qt.io/qt-6/qtwebengine-debugging.html),
[Qt WebEngine graphics/software rendering](https://doc.qt.io/qt-6.10/qtwebengine-features.html).
