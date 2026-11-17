"""Own only the optional PolicyConfigVista COM class in the audited Wine prefix."""

from pathlib import Path

from .. import registry
from .activation import library_path

CLASS = r"HKLM\Software\Classes\CLSID\{294935CE-F637-4E7C-A41B-AB255460B862}"
KEY = CLASS + r"\InprocServer32"
MANAGED = "windows_audio_policy"


def desired(data):
    return {"default": "Z:" + str(library_path(data)), "ThreadingModel": "Both"}


def query(prefix, name):
    return registry.query_string(prefix, KEY, name)


def write(prefix, name, value):
    selector = ["/ve"] if name == "default" else ["/v", name]
    arguments = (
        ["delete", KEY, *selector, "/f"]
        if value is None
        else ["add", KEY, *selector, "/t", "REG_SZ", "/d", value, "/f"]
    )
    if registry.reg(prefix, arguments)[0] or query(prefix, name) != value:
        raise RuntimeError("Audio policy registration write unverified")


def validate(record, prefix):
    if (
        not isinstance(record, dict)
        or set(record) != {"version", "prefix", "phase", "created_key", "created_class"}
        or record["version"] != 1
        or record["prefix"] != str(prefix)
        or record["phase"] not in ("pending", "applied")
        or type(record["created_key"]) is not bool
        or type(record["created_class"]) is not bool
    ):
        raise RuntimeError("Invalid audio policy ownership")


def restore(data, manifest, save, backup, *, shared_enabled=True):
    record = manifest.get(MANAGED)
    if record is None:
        return
    if not isinstance(record, dict) or not isinstance(record.get("prefix"), str):
        raise RuntimeError("Invalid audio policy ownership")
    prefix = Path(record["prefix"])
    validate(record, prefix)
    if not registry.owned_prefix(prefix, data):
        raise RuntimeError("Original audio policy prefix unavailable")
    registry.snapshot(prefix, backup)
    current = {name: query(prefix, name) for name in desired(data)}
    if current["default"] not in (None, desired(data)["default"]):
        print("Preserved user-modified audio policy registration.")
        if shared_enabled:
            return  # Retain the record until shared native files can be safely deactivated.
        for path in (library_path(data), library_path(data).with_suffix(".token")):
            manifest.get("files", {}).pop(str(path), None)
        manifest.pop(MANAGED)
        save()
        return
    for name, value in desired(data).items():
        if current[name] == value:
            write(prefix, name, None)
    for key, created in ((KEY, record["created_key"]), (CLASS, record["created_class"])):
        if created and registry.key_empty(prefix, key) is True:
            if (
                registry.reg(prefix, ["delete", key, "/f"])[0]
                or registry.key_empty(prefix, key) is not None
            ):
                raise RuntimeError("Audio policy cleanup unverified")
    manifest.pop(MANAGED)
    save()


def synchronize(prefix, data, enabled, manifest, save, backup, *, shared_enabled=True):
    if not enabled:
        restore(data, manifest, save, backup, shared_enabled=shared_enabled)
        return
    if not registry.owned_prefix(prefix, data):
        raise RuntimeError("Unsupported audio policy prefix")
    record = manifest.get(MANAGED)
    if record is not None:
        validate(record, prefix)
    registry.snapshot(prefix, backup)
    current = {name: query(prefix, name) for name in desired(data)}
    if record is None:
        if (
            any(value is not None for value in current.values())
            or registry.key_empty(prefix, KEY) is False
        ):
            raise RuntimeError("Existing audio policy registration preserved")
        record = {
            "version": 1,
            "prefix": str(prefix),
            "phase": "pending",
            "created_key": registry.key_empty(prefix, KEY) is None,
            "created_class": registry.key_empty(prefix, CLASS) is None,
        }
        manifest[MANAGED] = record
        save()
    elif record["phase"] == "applied":
        if current == desired(data):
            return
        if any(value is not None for value in current.values()):
            print("Preserved user-modified audio policy registration.")
            return
        record["phase"] = "pending"
        save()
    if any(current[name] not in (None, value) for name, value in desired(data).items()):
        raise RuntimeError("Audio policy changed during installation; preserving it")
    for name, value in desired(data).items():
        if current[name] != value:
            write(prefix, name, value)
    record["phase"] = "applied"
    save()
