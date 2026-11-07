"""Run with system Python for Fedora's existing GI/Gtk/GdkPixbuf packages.

Only named icons or matching installed desktop metadata are used. Exec fields
are never executed. The daemon bounds stdin, stdout, runtime and cache size.
"""

import json
import os
import re
import sys
from pathlib import Path


def main() -> int:
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gio, GLib, Gtk
    except (ImportError, ValueError):
        return 3
    try:
        request = json.loads(sys.stdin.buffer.read(4097))
        if not isinstance(request, dict) or set(request) != {"icon_name", "id", "executable"}:
            return 2
        key, executable = request["id"], request["executable"]
        if not isinstance(key, str) or not isinstance(executable, str):
            return 2
        candidates = [request["icon_name"]]
        identifier = key.split(":", 1)[1] if key.startswith(("flatpak:", "app:")) else None
        if identifier:
            candidates.append(identifier)
        candidates.append(executable)
        apps = Gio.AppInfo.get_all()
        desktop = next(
            (app for app in apps if identifier and app.get_id() == identifier + ".desktop"), None
        )
        if desktop is None:
            desktop = next((app for app in apps if app.get_executable() == executable), None)
        if desktop and desktop.get_icon():
            icon = desktop.get_icon()
            if isinstance(icon, Gio.ThemedIcon):
                candidates.extend(icon.get_names())
        # An independent icon theme can resolve without opening a display/window.
        theme = Gtk.IconTheme.new()
        roots = [Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))]
        roots.extend(
            Path(p)
            for p in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
        )
        roots.append(Path("/var/lib/flatpak/exports/share"))
        roots.append(Path.home() / ".local/share/flatpak/exports/share")
        for root in roots:
            if root.is_absolute():
                theme.append_search_path(str(root / "icons"))
        theme.set_custom_theme("hicolor")
        for name in candidates:
            # Reject absolute paths, traversal and option/URI-like metadata.
            if (
                not isinstance(name, str)
                or not re.fullmatch(r"[\w.+-]{1,256}", name)
                or name in {".", ".."}
            ):
                continue
            found = theme.lookup_icon(name, 96, Gtk.IconLookupFlags.FORCE_SIZE)
            if not found:
                continue
            pixbuf = found.load_icon()
            ok, data = pixbuf.save_to_bufferv("png", [], [])
            if ok and len(data) <= 32768:
                sys.stdout.buffer.write(data)
                return 0
        return 2
    except (ValueError, TypeError, KeyError, GLib.Error):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
