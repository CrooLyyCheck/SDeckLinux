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
deckbridge streamdeck --no-webview-sandbox
```

Alternatively a deliberate private host preference makes that mode apply when
using `deckbridge streamdeck`:

```toml
[compat.sdeck.webview]
renderer_sandbox = false
```

The table is optional and its default is `true`. Set it back to `true`, quit the
app and launch normally to restore sandboxing. Existing `streamdeck-wine` launches
remain independent of this DeckBridge-only preference. The helper does not
enable remote debugging. It preserves unrelated environment/Wine fixes and
rejects an external `--no-sandbox` override when sandboxed mode was requested.

Disabling the renderer sandbox removes an isolation layer for HTML plugin pages
inside that app; those pages run with the user's account permissions. A one-off
diagnostic authorization is not permission to enable that mode for daily use.
The audited workstation currently retains the normal sandboxed preference.

The relevant settings are in the **original main Auto Detection or Manual
Detection action**. The dynamically generated +/- child actions do not each
implement their own property-inspector settings UI in this plugin build.

References: [Qt sandbox controls](https://doc.qt.io/qt-6/qtwebengine-platform-notes.html#sandboxing-support),
[Qt debugging controls and sandbox risk](https://doc.qt.io/qt-6/qtwebengine-debugging.html).
