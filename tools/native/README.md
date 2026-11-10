# Native Core Audio development probe

This optional developer target is separate from normal installation and
`make check`. It builds a read-only Windows x64 COM consumer, not an audio shim.
It enumerates active endpoints and reads scalar/mute values. It contains no
setter calls. It must not be used as evidence that volume control works.

The audited isolated toolchain is upstream
[llvm-mingw 20261104](https://github.com/mstorsjo/llvm-mingw/releases/tag/20261104):

- Archive: `llvm-mingw-20261104-ucrt-ubuntu-22.04-x86_64.tar.xz`
- Size: 84,104,244 bytes
- SHA-256: `919380403de87dca3c581c2053230cd298af5e891286628ba0613b7fed370926`

Download from that release, verify the size/hash, and extract under
`.local/toolchains/` with safe archive extraction. No system installation or Wine
DLL override is needed. The toolchain/archive and compiled PE remain ignored by
Git. An equivalent existing compiler can be selected with `NATIVE_CC`.

```bash
make native-probe
make native-core-audio
```

Running the probe is a separate explicit real-host step: make bounded verified
registry backups and check free space before starting Wine in the audited prefix.
Pass a private output filename as the sole Windows argument. The report has only
aggregate counts, HRESULT, volume bounds and `setters_called: 0`; it contains no
endpoint identifiers. Keep reports private. The audited Wine run returned seven
readable devices, scalar minimum/maximum 1.0 and no setters called.

The experimental library target also builds a **probe-only** Node-API activation
bootstrap and manifest. It does not install or enable them for Stream Deck.
`tools/core_audio_smoke.py` explicitly loads the library's real COM factory and
observes readback/lifetime behavior. With the native backend it reads actual
levels instead of Wine's constant 1.0. See [scope and limits](../../docs/compat/windows/core-audio.md).
