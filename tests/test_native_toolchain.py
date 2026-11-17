"""Pinned compiler acquisition on tiny synthetic archives; no network or execution."""

import contextlib
import hashlib
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import prepare_native as native


class ToolchainTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.cache = self.root / "cache"
        for mock in (
            patch.object(native, "CACHE", self.cache),
            patch.object(native.platform, "machine", return_value="x86_64"),
            patch.object(native.platform, "system", return_value="Linux"),
            patch.object(
                native.shutil, "disk_usage", return_value=type("Disk", (), {"free": 1 << 40})()
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            mock.__enter__()
            self.addCleanup(mock.__exit__, None, None, None)

    def archive(self, *, escaping_link=False):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:xz") as archive:
            entry = tarfile.TarInfo(native.NAME + "/bin/x86_64-w64-mingw32-gcc")
            entry.mode = 0o755
            content = b"synthetic compiler; never execute"
            if escaping_link:
                entry.type, entry.linkname = tarfile.SYMTYPE, "../../../outside"
                archive.addfile(entry)
            else:
                entry.size = len(content)
                archive.addfile(entry, io.BytesIO(content))
        return buffer.getvalue()

    def acquire(self, data, digest=None):
        with (
            patch.object(native, "SIZE", len(data)),
            patch.object(native, "SHA256", digest or hashlib.sha256(data).hexdigest()),
            patch.object(
                native.urllib.request, "urlopen", return_value=io.BytesIO(data)
            ) as request,
        ):
            native.prepare()
            return request

    def test_verified_archive_is_local_and_reused_without_network(self):
        request = self.acquire(self.archive())
        request.assert_called_once_with(native.URL, timeout=30)
        self.assertTrue(native.compiler_ready(self.cache / native.NAME))
        with patch.object(native.urllib.request, "urlopen") as request:
            native.prepare()
            request.assert_not_called()

    def test_checksum_failure_does_not_extract_and_cleans_partial_download(self):
        with self.assertRaisesRegex(RuntimeError, "checksum"):
            self.acquire(self.archive(), "0" * 64)
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_data_filter_rejects_a_link_outside_verified_archive_root(self):
        with self.assertRaises(tarfile.FilterError):
            self.acquire(self.archive(escaping_link=True))
        self.assertFalse((self.root / "outside").exists())
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_incomplete_existing_toolchain_is_preserved_without_network(self):
        destination = self.cache / native.NAME
        destination.mkdir(parents=True)
        sentinel = destination / "user-file"
        sentinel.write_bytes(b"preserve")
        with patch.object(native.urllib.request, "urlopen") as request:
            with self.assertRaisesRegex(RuntimeError, "preserved"):
                native.prepare()
            request.assert_not_called()
        self.assertEqual(sentinel.read_bytes(), b"preserve")
