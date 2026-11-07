# Local protocol v1

UTF-8 JSON followed by LF, at most 16,384 bytes including LF. One request and one
response per connection. This host protocol uses no TCP listener. The separately
enabled Volume Controller service has its own versioned loopback contract.
Envelope and action parameters reject
unknown keys. Duplicate JSON keys, non-standard constants, malformed UTF-8,
wrong types and unsupported versions are errors.

```json
{"v":1,"id":"client-generated-id","method":"capabilities.list","params":{}}
{"v":1,"id":"client-generated-id","result":{"capabilities":[],"events":{"supported":false},"automatic_retry":false}}
```

The example's capabilities array is abbreviated; the real response describes
the six concrete capabilities and their enabled state. `id` is 1–64 ASCII letters,
digits or hyphens. It is echoed to the client but never used as a log correlation
ID. The server generates a separate random correlation ID.
Logs include only validated method/capability names. Diagnostics include a safe
summary of the remembered portal handler separately from the MIME default.

| Method | Params | Meaning |
| --- | --- | --- |
| `capabilities.list` | `{}` | Implemented providers with v1 and enabled flags |
| `diagnostics.get` | `{}` | Safe local observations, no raw logs, URIs or serial numbers |
| `actions.execute` | `capability`, `arguments` | Execute one supported action |

Action arguments:

```json
{"capability":"oauth.deepLink","arguments":{"uri":"streamdeck://plugins/message/com.example.plugin/callback?code=SYNTHETIC&state=sample#fragment"}}
{"capability":"desktop.launch","arguments":{"target":"configured-alias"}}
{"capability":"desktop.openUrl","arguments":{"target":"configured-alias"}}
{"capability":"audio.sessions.list","arguments":{}}
{"capability":"audio.session.volume","arguments":{"target":"app:io.deckbridge.audio-test","volume":0.25}}
{"capability":"audio.session.mute","arguments":{"target":"app:io.deckbridge.audio-test","mute":true}}
```

URIs are capped at 8,192 UTF-8 bytes; keep practical deep-links under Elgato's
recommended 2,000 characters. URI values are opaque after validation. Native
target aliases resolve only to local configuration, with no request argv.

Audio targets are a session ID (`pw:<server-cookie>:<object.serial>`) or logical
application key from the current listing. Backend and adapter volumes are finite
scalars **0..1**; only the CLI accepts percentages **0..100**. No boost is allowed.
Mute is a strict JSON boolean. Writes require enabled audio, `allow_write = true`
and a matching `allowed_apps` entry if that list is nonempty. Empty means all
applications. The default is audio disabled and writes disabled.

The list result has `version: 1`, `backend`, `revision`, `applications`, `system`
(default-output volume/mute), `write_enabled` and `system_write_enabled`. Each application
has `id`, `name`, `executable`, `volume`, `mute`, `mixed_mute`, `controllable` and
member `sessions`. Session fields include stable ID, current node/serial/Pulse
handle, application key, reported PID/Flatpak metadata, channel scalars and mute.
Named icon hints and event-only metadata are additive fields. Global output
control is currently consumed only by the versioned plugin service, through
its separate opt-in gate; no generic host IPC system action is advertised.
These metadata are returned to the requesting same-user client, not logged.
Successful writes return `status: applied` and `stream_count`; this means the
targeted commands completed and the graph was refreshed, not physical audibility.
Responses over the existing 16 KiB frame limit fail with `response_too_large`;
there is no silent truncation or pagination in v1.

```json
{"v":1,"id":"client-generated-id","error":{"code":"capability_disabled"}}
```

For malformed envelopes the response `id` is `null`. Errors are fixed machine
codes, including `invalid_frame`, `invalid_json`, `unsupported_version`,
`unsupported_method`, `invalid_params`, `uri_not_allowed`, `capability_disabled`,
`target_not_allowed`, `instance_missing`, `instance_ambiguous`, `instance_lost`,
`launcher_failed`, `backend_unavailable`, `timeout_outcome_unknown`.
Audio adds fixed readiness/backend/snapshot errors, `audio_write_disabled`,
`invalid_audio_volume`, `audio_application_gone`, `audio_stream_gone`,
`audio_stream_read_only`, `audio_partial_action`, and `audio_action_failed`.

Limits: 16 concurrent clients; 5 seconds for frame input/output; 10 seconds for
launcher completion; client action deadline 15 seconds. These bound resource use
and responsiveness, not application/OAuth readiness. Cancellation reaps the
direct helper; Wine's target process and transient native services have separate
lifecycles. No automatic side-effect retries or deduplication are provided.

`forwarded-unconfirmed` / `started-unconfirmed` explicitly carry
`application_ack: false`. Successful application/plugin behavior must be measured
separately. Event subscriptions are not supported in this version and are not
advertised as implemented.

The envelope `v=1` pins the provider argument contracts to capability version 1.
Incompatible envelope or provider argument changes require a new `v`, a matching
capability version and a migration description. Current configuration is v1 and
remains compatible with configurations without audio tables. The optional
`[audio]` and `[compat.volume_controller]` tables are additive. Plugin JSON-RPC
methods/events are documented in [its contract notes](compat/plugins/volume-controller.md).
