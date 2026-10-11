#!/usr/bin/env python3
"""Integrity and recovery regression checks that need no Docker daemon."""

import argparse
import io
import json
from pathlib import Path
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

    def test_image_tag_requires_matching_version_and_container_revision(self):
        for tag in [self.version + "-ubuntu26.04", self.version + "-ubuntu26.04-r2"]:
            publish.validate_image_tag(self.version, tag)
        for tag in ["latest", "next", self.version, "0.1.0-alpha.1-ubuntu26.04",
                    self.version + "-../escape", self.version + "-ubuntu:26.04", self.version + "-" + "a" * 128]:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                publish.validate_image_tag(self.version, tag)

    def test_version_guard_requires_structured_missing_manifest(self):
        for status, code, allowed in [(404, "MANIFEST_UNKNOWN", True), (404, "NAME_UNKNOWN", False),
                                      (403, "DENIED", False), (401, "UNAUTHORIZED", False),
                                      (429, "TOOMANYREQUESTS", False), (500, "UNKNOWN", False)]:
            body = io.BytesIO(json.dumps({"errors": [{"code": code}]}).encode())
            error = urllib.error.HTTPError("url", status, "error", {}, body)
            token = io.BytesIO(b'{"token":"synthetic-pull-token"}')
            with self.subTest(status=status, code=code), \
                    patch.object(publish.urllib.request, "urlopen", side_effect=[token, error]):
                if allowed:
                    publish.require_absent(self.version + "-ubuntu26.04")
                else:
                    with self.assertRaises(ValueError):
                        publish.require_absent(self.version + "-ubuntu26.04")

    def test_version_guard_rejects_existing_image_and_network_failures(self):
        for response in [io.BytesIO(b'{"schemaVersion":2}'), urllib.error.URLError("network unavailable")]:
            token = io.BytesIO(b'{"token":"synthetic-pull-token"}')
            with patch.object(publish.urllib.request, "urlopen", side_effect=[token, response]), \
                    self.assertRaises((ValueError, urllib.error.URLError)):
                publish.require_absent(self.version + "-ubuntu26.04")
        with patch.object(publish.urllib.request, "urlopen", side_effect=urllib.error.URLError("auth unavailable")), \
                self.assertRaises(urllib.error.URLError):
            publish.require_absent(self.version + "-ubuntu26.04")

    def test_version_guard_rejects_invalid_token_and_error_responses(self):
        for token_payload in [b'{}', b'{"token":1}', b'{"token":""}']:
            with patch.object(publish.urllib.request, "urlopen", return_value=io.BytesIO(token_payload)), \
                    self.assertRaises(ValueError):
                publish.require_absent(self.version + "-ubuntu26.04")
        for body in [b'{}', b'not json', b'{"errors":[]}',
                     b'{"errors":[{"code":"MANIFEST_UNKNOWN"},{"code":"DENIED"}]}']:
            token = io.BytesIO(b'{"token":"synthetic-pull-token"}')
            error = urllib.error.HTTPError("url", 404, "error", {}, io.BytesIO(body))
            with patch.object(publish.urllib.request, "urlopen", side_effect=[token, error]), \
                    self.assertRaises(ValueError):
                publish.require_absent(self.version + "-ubuntu26.04")

    def publish_args(self, mode="verify", tag_next=True):
        return argparse.Namespace(version=self.version, image_tag=self.version + "-ubuntu26.04",
                                  mode=mode, tag_next=tag_next, assets=None, evidence=self.directory / "evidence")

    def test_verify_existing_image_probes_anonymous_digest_before_next(self):
        digest = "sha256:" + "a" * 64
        events = []

        def command(*args, **kwargs):
            events.append(args)
            return ""

        def anonymous_pull(tag):
            events.append(("anonymous", tag))
            return digest

        with patch.object(publish, "approved", return_value=self.record), \
                patch.object(publish, "require_absent") as absent, patch.object(publish, "prepare") as prepare_context, \
                patch.object(publish, "command", side_effect=command), \
                patch.object(publish, "anonymous_pull", side_effect=anonymous_pull), \
                patch.object(publish, "push") as pushes:
            publish.publish(self.publish_args())
        absent.assert_not_called()
        prepare_context.assert_not_called()
        pushes.assert_not_called()
        self.assertEqual(events[0], ("anonymous", f"{publish.IMAGE}:{self.version}-ubuntu26.04"))
        self.assertIn("smoke.py", events[1][1])
        self.assertEqual(events[1][3], f"{publish.IMAGE}@{digest}")
        self.assertEqual(events[2], ("docker", "buildx", "imagetools", "create", "--prefer-index=false",
                                     "--tag", f"{publish.IMAGE}:next", f"{publish.IMAGE}@{digest}"))
        report = json.loads((self.directory / "evidence/image.json").read_text())
        self.assertTrue(report["anonymousPull"] and report["next"])

    def test_failed_anonymous_probe_does_not_promote_next(self):
        with patch.object(publish, "approved", return_value=self.record), \
                patch.object(publish, "anonymous_pull", return_value="sha256:" + "a" * 64), \
                patch.object(publish, "command", side_effect=RuntimeError("probe failed")), \
                patch.object(publish, "push") as push_image, self.assertRaisesRegex(RuntimeError, "probe failed"):
            publish.publish(self.publish_args())
        push_image.assert_not_called()
        report = json.loads((self.directory / "evidence/image.json").read_text())
        self.assertFalse(report["anonymousPull"] or report["next"])

    def test_next_promotion_requires_original_registry_digest(self):
        with patch.object(publish, "approved", return_value=self.record), \
                patch.object(publish, "anonymous_pull", side_effect=["sha256:" + "a" * 64, "sha256:" + "b" * 64]), \
                patch.object(publish, "command"), self.assertRaisesRegex(ValueError, "another image digest"):
            publish.publish(self.publish_args())
        report = json.loads((self.directory / "evidence/image.json").read_text())
        self.assertTrue(report["anonymousPull"])
        self.assertFalse(report["next"])

    def test_publish_rechecks_absence_before_push(self):
        with patch.object(publish, "approved", return_value=self.record), \
                patch.object(publish, "require_absent", side_effect=[None, ValueError("tag now exists")]), \
                patch.object(publish, "prepare"), patch.object(publish, "command") as commands, \
                patch.object(publish, "push") as push_image, self.assertRaisesRegex(ValueError, "tag now exists"):
            publish.publish(self.publish_args(mode="publish"))
        self.assertEqual(commands.call_args_list[0].args[:2], ("docker", "build"))
        push_image.assert_not_called()

    def test_publish_rejects_anonymous_digest_mismatch_before_next(self):
        with patch.object(publish, "approved", return_value=self.record), \
                patch.object(publish, "require_absent"), patch.object(publish, "prepare"), \
                patch.object(publish, "command"), patch.object(publish, "push", return_value="sha256:" + "a" * 64) as pushes, \
                patch.object(publish, "anonymous_pull", return_value="sha256:" + "b" * 64), \
                self.assertRaisesRegex(ValueError, "another image digest"):
            publish.publish(self.publish_args(mode="publish"))
        pushes.assert_called_once_with(f"{publish.IMAGE}:{self.version}-ubuntu26.04")

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
