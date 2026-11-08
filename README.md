# SDeckLinux

A Linux compatibility layer for Elgato Stream Deck software and plugins.

The project connects application and plugin interfaces to native Linux services,
with Wine providing the Windows execution environment.

[Usage and configuration](docs/USAGE.md) · [Architecture](docs/ARCHITECTURE.md) ·
[Roadmap](docs/ROADMAP.md) · [Testing](docs/TESTING.md)

## Installation

Start with an existing official Stream Deck installation under the supported
`streamdeck-wine` installer. Download this repository using **Code → Download ZIP**,
extract it, open a terminal in the extracted folder, and run:

```bash
make install
```

The normal installation includes the Wine startup fixes and menu integration.
After installation, quit any running Stream Deck and reopen **Stream Deck (Wine)**
from your application menu. No separate repair step or mode selection is needed.

The built-in Wine mode uses software rendering with the WebEngine renderer
sandbox disabled. Explicit preferences can override these defaults; see the
[startup mode details](docs/compat/sdeck/webview.md).

See [requirements and setup details](docs/USAGE.md) for prerequisites and other options.

## Architecture

Compatibility modules implement the interface expected by the application or
plugin. Reusable Linux backends provide host functionality independently of
those interfaces. Each integration has an explicit scope and can be disabled.

```text
deckbridge/compat/sdeck/          # Stream Deck application interfaces
  oauth/                        # URL and authorization handoff
  webview/                      # Browser startup and native surface rendering
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

## Contributing

Contributions are welcome, including vibe coding and other AI-assisted workflows.
Please use sufficiently capable models such as **GPT 6.1 Sol**, **Claude Sonnet
5.5**, **Kimi K3.1 Pro**, or models of comparable or greater capability.

Review generated code, follow the [repository rules](AGENTS.md) and
[architecture](docs/ARCHITECTURE.md), and run `make check` before submitting changes.

## Project scope

Installation requires an existing official Stream Deck application under Wine.
This repository does not bootstrap Wine or install Elgato software; see
[requirements and installation](docs/USAGE.md#requirements-and-scope).

The runtime package, commands, configuration paths and user service are named
**DeckBridge** (`deckbridge`).

SDeckLinux is an independent community project, unaffiliated with Elgato.
Vendor applications, plugins and binaries are not distributed here.
