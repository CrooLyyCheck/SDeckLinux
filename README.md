# SDeckLinux

A Linux compatibility layer for Elgato Stream Deck software and plugins.

The project connects application and plugin interfaces to native Linux services,
with Wine providing the Windows execution environment.

[Usage and configuration](docs/USAGE.md) · [Architecture](docs/ARCHITECTURE.md) ·
[Roadmap](docs/ROADMAP.md) · [Testing](docs/TESTING.md)

## Architecture

Compatibility modules implement the interface expected by the application or
plugin. Reusable Linux backends provide host functionality independently of
those interfaces. Each integration has an explicit scope and can be disabled.

```text
deckbridge/compat/sdeck/          # Stream Deck application interfaces
  oauth/                        # URL and authorization handoff
  webview/                      # Embedded browser launch options
deckbridge/compat/plugins/       # Versioned plugin interfaces
  volume_controller/            # Audio Router service contract
deckbridge/backends/             # Reusable Linux implementations
  audio/                        # PipeWire / PipeWire-Pulse
  desktop/                      # Desktop metadata and icons
```

The [architecture document](docs/ARCHITECTURE.md) defines the layer boundaries,
dependency direction and approach to adding compatibility.

## Compatibility

[**View compatibility tables →**](docs/COMPATIBILITY.md)

See Application, basic Stream Deck functions and plugins progress here.

## Development

Python >= 3.11. Development tools and the optional WebSocket dependency are hash
pinned and installed into isolated environments.

```bash
git clone https://github.com/CrooLyyCheck/SDeckLinux.git
cd SDeckLinux
make setup
make check
```

`make check` runs formatting, lint, byte compilation and hardware-free tests.
Host, hardware and audio mutation tests are [separate and opt-in](docs/TESTING.md).

## Project scope

Installation requires an existing official Stream Deck application under Wine.
This repository does not bootstrap Wine or install Elgato software; see
[requirements and installation](docs/USAGE.md#requirements-and-scope).

The runtime package, commands, configuration paths and user service are named
**DeckBridge** (`deckbridge`).

SDeckLinux is an independent community project, unaffiliated with Elgato.
Vendor applications, plugins and binaries are not distributed here.
