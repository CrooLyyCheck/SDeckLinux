# DeckBridge repository rules

- Communicate with the user in Polish. Code and technical documentation use English.
- Preserve the original Elgato application, Wine fixes, profiles and unmodified plugins.
- Inspect `git status` before substantial edits; preserve unrelated changes. Never rewrite history.
- No GitHub Actions, external CI, push, PR or publication without explicit authorization.
- No root, global Wine/KDE/SELinux changes or system package installation without authorization.
- Before writing to an existing Wine prefix, check free space and make a bounded, verified private backup of the affected files. Never commit prefix data, binaries, tokens, logs or device identifiers.
- Runtime code uses Python >= 3.11. The optional Audio Router adapter uses pinned `websockets` for RFC 6455 framing; native icons use a bounded system-Python worker with existing GI/GTK3/GdkPixbuf packages. The core uses the standard library. Do not add a toolchain or dependency without a concrete need.
- Keep service-specific compatibility in `deckbridge/compat/sdeck/`, plugin-specific contracts/adapters in `deckbridge/compat/plugins/<plugin_name>/`, and reusable Linux capabilities in `deckbridge/backends/`. Never mix plugin wire fields into backend models.
- `make setup` creates an isolated development environment; `make check` runs format, lint, byte compilation and hardware-free tests. `make format` formats source.
- Hardware/input/audio mutation tests are separate and opt-in; see `docs/TESTING.md`. Do not inject input or change volume on the active desktop without consent.
- Never claim OAuth, plugin or hardware functionality solely from process exit status. Record observable evidence and untested boundaries in `docs/STATUS.md`.
- Do not log request payloads, URIs, subprocess argv/output or exception text containing external data. Structured logs use server-generated correlation IDs and fixed error codes.
- IPC must remain versioned and bounded, same-user only, with no arbitrary command execution endpoint. Actions use explicit local allowlists, never `shell=True`.
- Experimental capabilities must be individually disableable. Installed files must be owned, hash tracked and reversible; preserve modified files.
