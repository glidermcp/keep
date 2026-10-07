#!/usr/bin/env python3
"""Integrity and recovery regression checks that need no Docker daemon."""

import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import backup
import prepare
import publish


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.version = "0.1.0-alpha.99"
        binary = bytearray(32)
        binary[:6] = b"\x7fELF\x02\x01"
        binary[18:20] = b"\x3e\x00"
        self.contents = {"keep": bytes(binary), "LICENSE": b"license", "THIRD-PARTY-NOTICES.txt": b"notices",
                         "INSTALL.txt": b"install"}
        self.archive = self.directory / f"keep-v{self.version}-linux-x64.tar.gz"
        self.record = {"binarySha256": prepare.sha256(self.contents["keep"]),
                       "licenseSha256": prepare.sha256(self.contents["LICENSE"]),
                       "noticesSha256": prepare.sha256(self.contents["THIRD-PARTY-NOTICES.txt"])}
        self.write_archive()

    def write_archive(self, members=None):
        with tarfile.open(self.archive, "w:gz") as target:
            for name, content in (members or list(self.contents.items())):
                member = tarfile.TarInfo(name)
                member.size = len(content)
                member.mode = 0o755 if name == "keep" else 0o644
                target.addfile(member, io.BytesIO(content))
        self.record["archiveSha256"] = prepare.sha256(self.archive.read_bytes())
        manifest = {"version": self.version, "buildId": "public-build", "assets": [
            {"target": "linux-x64", "archive": self.archive.name, "sha256": self.record["archiveSha256"]}]}
        self.write_manifest(manifest)

    def write_manifest(self, manifest):
        raw = json.dumps(manifest).encode()
        (self.directory / "release.json").write_bytes(raw)
        self.record["manifestSha256"] = prepare.sha256(raw)
        (self.directory / "SHA256SUMS").write_text("".join(
            f'{item["sha256"]}  {item["archive"]}\n' for item in manifest["assets"]), encoding="utf-8", newline="\n")

    def test_approved_context_has_only_runtime_files(self):
        destination = self.directory / "context"
        with patch.object(prepare, "approved", return_value=self.record):
            prepare.prepare(self.version, destination, self.directory)
        self.assertEqual({file.name for file in (destination / "native").iterdir()}, prepare.FILES)
        self.assertEqual({file.name for file in destination.iterdir()},
                         {"native", "Dockerfile", ".dockerignore", "entrypoint.sh", "token.sh", "healthcheck.sh"})
        with patch.object(prepare, "approved", return_value=self.record), self.assertRaisesRegex(ValueError, "empty"):
            prepare.prepare(self.version, destination, self.directory)

    def test_version_must_be_explicitly_approved(self):
        for version in ["latest", "next", "../0.1.0-alpha.3", "0.1.0-alpha.99"]:
            with self.subTest(version=version), self.assertRaises(ValueError):
                prepare.approved(version)

    def test_tampered_manifest_archive_and_checksums_fail(self):
        for name in ["release.json", "SHA256SUMS", self.archive.name]:
            file = self.directory / name
            original = file.read_bytes()
            file.write_bytes(original + b"changed")
            with self.subTest(name=name), self.assertRaises(ValueError):
                prepare.verify_assets(self.version, self.directory, self.record)
            file.write_bytes(original)

    def test_manifest_target_and_version_must_match(self):
        for field, value in [("version", "0.1.0-alpha.1"), ("target", "macos-arm64")]:
            manifest = json.loads((self.directory / "release.json").read_bytes())
            if field == "version":
                manifest[field] = value
            else:
                manifest["assets"][0][field] = value
            self.write_manifest(manifest)
            with self.assertRaises(ValueError):
                prepare.verify_assets(self.version, self.directory, self.record)
            self.write_archive()

    def test_approved_archive_still_rejects_duplicate_and_unsafe_paths(self):
        for members in [list(self.contents.items()) + [("keep", self.contents["keep"])],
                        [("../keep" if name == "keep" else name, content) for name, content in self.contents.items()]]:
            self.write_archive(members)
            with self.assertRaisesRegex(ValueError, "paths"):
                prepare.verify_assets(self.version, self.directory, self.record)

    def test_binary_and_legal_hashes_are_checked(self):
        for key in ["binarySha256", "licenseSha256", "noticesSha256"]:
            record = {**self.record, key: "0" * 64}
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "checksum"):
                prepare.verify_assets(self.version, self.directory, record)

    def test_version_guard_fails_closed_for_auth_and_network_errors(self):
        for code, stderr, allowed in [(0, b"", False), (1, b"manifest unknown", True),
                                      (1, b"unauthorized", False), (1, b"timeout", False)]:
            result = subprocess.CompletedProcess([], code, "", stderr.decode())
            with patch.object(publish.subprocess, "run", return_value=result):
                if allowed:
                    publish.require_absent("image:version")
                else:
                    with self.assertRaises(ValueError):
                        publish.require_absent("image:version")

    def test_bootstrap_requires_authenticated_absence(self):
        for status, allowed in [(404, True), (403, False), (401, False), (500, False)]:
            error = urllib.error.HTTPError("url", status, "error", {}, None)
            with patch.dict(publish.os.environ, {"GITHUB_REPOSITORY": "glidermcp/keep", "GH_TOKEN": "synthetic"}), \
                    patch.object(publish.urllib.request, "urlopen", side_effect=error):
                if allowed:
                    publish.require_absent("image:version", True)
                else:
                    with self.assertRaises(ValueError):
                        publish.require_absent("image:version", True)

    def test_restore_rejects_links_traversal_and_missing_store(self):
        for name, kind in [("../documents", tarfile.DIRTYPE), ("/documents", tarfile.DIRTYPE),
                           ("documents/link", tarfile.SYMTYPE), ("other", tarfile.DIRTYPE)]:
            file = self.directory / "backup.tar.gz"
            with tarfile.open(file, "w:gz") as target:
                member = tarfile.TarInfo(name)
                member.type = kind
                member.linkname = "/etc/passwd" if kind == tarfile.SYMTYPE else ""
                target.addfile(member)
            with self.subTest(name=name), self.assertRaises(ValueError):
                backup.validate_backup(file)


if __name__ == "__main__":
    unittest.main()
