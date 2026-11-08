# ADR 0003: explicit, process-local WebEngine launch mode

Status: implemented, disabled by default, 2026-11-08.

Follow-up: the user separately approved daily use. Renderer execution alone did
not establish visibility in the native app: the supplied window screenshot
still showed a blank inspector. A process-local `--disable-gpu` comparison made
the panel visible and was confirmed by the user. The independent
`software_rendering` preference now supplies that flag, defaulting to false.
Only the audited host enables both preferences; repository defaults stay safe.

The original plugin's controls existed in its readable inspector assets, but
normal Wine WebEngine renderers did not respond to document commands. Audio
integration was independently functional. A separately authorized one-off
sandbox-flag comparison rendered the original UI, including its 1–25 Step Size
slider. Restoring normal launch removed the test flags/debug listener and
reproduced the missing controls.

Patching vendor inspectors, replacing their UI, disabling isolation globally,
or modifying the existing launcher's Wine fixes would cross unnecessary
boundaries. A generic Windows sandbox shim would require demonstrated missing
APIs and ABI/behavior analysis; this experiment is not such an implementation.

Provide `deckbridge streamdeck` in `compat/sdeck/webview/`, delegating to the
audited original installer launcher. Its optional renderer-sandbox preference
defaults to true. Disabling it requires an explicit command flag or deliberate
host configuration; neither is an IPC action offered to plugins. Configuration
remains backward-compatible. Existing instances are preserved rather than
silently pretending the changed environment applies to them.

Only the child environment changes. No global environment, registry, launcher,
desktop entry, vendor asset or prefix edit is needed. Remote debugging belongs
to the bounded manual diagnosis, not this launch feature. Unit coverage checks
default/opt-in environment isolation, original-launcher delegation and existing
instance refusal without executing Wine or altering audio.

Tradeoff: this is a documented compatibility mode with reduced renderer
isolation, not a transparent security-preserving fix. Daily use required and
received a separate user decision after the initial one-off comparison. GPU
composition was a second boundary; software rendering is an independent switch.
The original independently working Wine launcher remains available.
