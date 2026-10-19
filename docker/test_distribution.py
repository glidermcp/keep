#!/usr/bin/env python3
"""Integrity and recovery regression checks that need no Docker daemon."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import backup
import prepare
import publish
import smoke


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

    def test_credential_smoke_validates_shape_digest_and_keeps_failure_messages_private(self):
        secret = "a" * 64
        valid = {"secret": secret, "tokenSha256": hashlib.sha256(secret.encode("ascii")).hexdigest()}
        result = subprocess.CompletedProcess([], 0, json.dumps(valid).encode(), b"")
        self.assertIsNone(smoke.validate_credential_output(result))
        invalid = [({}, 0, b""), ({**valid, "extra": True}, 0, b""),
                   ({**valid, "secret": "A" * 64}, 0, b""), ({**valid, "secret": "a" * 63}, 0, b""),
                   ({**valid, "tokenSha256": "0" * 64}, 0, b""),
                   ({**valid, "tokenSha256": None}, 0, b""), (valid, 1, secret.encode()),
                   (valid, 0, secret.encode())]
        for payload, status, stderr in invalid:
            with self.subTest(status=status, fields=set(payload)):
                result = subprocess.CompletedProcess([], status, json.dumps(payload).encode(), stderr)
                with self.assertRaises(ValueError) as error:
                    smoke.validate_credential_output(result)
                self.assertNotIn(secret, str(error.exception))
                self.assertNotIn(valid["tokenSha256"], str(error.exception))
        with self.assertRaisesRegex(ValueError, "invalid JSON") as error:
            smoke.validate_credential_output(subprocess.CompletedProcess([], 0, b"private-invalid-json", b""))
        self.assertNotIn("private-invalid-json", str(error.exception))

    def test_approved_version_capabilities_gate_only_the_new_credential_probe(self):
        class ExistingSmokeChecksReached(Exception):
            pass

        def command(*arguments, **kwargs):
            if arguments[:2] == ("run", "--rm"):
                raise ExistingSmokeChecksReached()
            return subprocess.CompletedProcess([], 0, b"", b"")

        configuration = {"Architecture": "amd64", "Os": "linux", "Id": "synthetic-image",
                         "Config": {"User": "10001:10001"}}
        for version, credential_probe in (("0.1.0-alpha.3", False), ("0.1.0-alpha.4", False), ("0.1.0-alpha.5", True)):
            with self.subTest(version=version), patch.object(smoke, "approved", return_value=self.record), \
                    patch.object(smoke, "text", side_effect=[f"keep {version}", self.record["binarySha256"],
                                                             json.dumps([configuration])]), \
                    patch.object(smoke, "probe_offline_credentials") as offline, \
                    patch.object(smoke, "docker", side_effect=command) as commands:
                with self.assertRaises(ExistingSmokeChecksReached):
                    smoke.probe("synthetic-image", version)
                if credential_probe:
                    offline.assert_called_once_with("synthetic-image")
                else:
                    offline.assert_not_called()
                self.assertEqual(commands.call_args_list[0].args, ("run", "--rm", "synthetic-image"))

    def test_new_approved_version_requires_explicit_capabilities_before_docker(self):
        with patch.object(smoke, "approved", return_value=self.record), patch.object(smoke, "text") as text, \
                patch.object(smoke, "docker") as commands, patch.object(smoke, "probe_offline_credentials") as offline:
            with self.assertRaisesRegex(ValueError, "Update the version capability map"):
                smoke.probe("synthetic-image", "0.1.0-alpha.99")
            text.assert_not_called()
            commands.assert_not_called()
            offline.assert_not_called()

    def test_alpha5_malformed_or_mismatched_credential_output_fails_the_image_probe(self):
        configuration = {"Architecture": "amd64", "Os": "linux", "Id": "synthetic-image",
                         "Config": {"User": "10001:10001"}}
        invalid = [b"private-invalid-json", json.dumps({"secret": "a" * 64, "tokenSha256": "0" * 64}).encode()]
        for index, payload in enumerate(invalid):
            result = subprocess.CompletedProcess([], 0, payload, b"")
            with self.subTest(case=index), patch.object(smoke, "approved", return_value=self.record), \
                    patch.object(smoke, "text", side_effect=["keep 0.1.0-alpha.5", self.record["binarySha256"],
                                                             json.dumps([configuration])]), \
                    patch.object(smoke, "probe_offline_credentials", side_effect=lambda image: smoke.validate_credential_output(result)), \
                    patch.object(smoke, "docker") as commands:
                with self.assertRaises(ValueError):
                    smoke.probe("synthetic-image", "0.1.0-alpha.5")
                commands.assert_not_called()

    @unittest.skipUnless(os.name == "posix" and shutil.which("sh"), "The entrypoint routing test requires a POSIX shell.")
    def test_entrypoint_routes_offline_credential_to_native_without_loading_http_auth(self):
        native = self.directory / "native-keep"
        token_loader = self.directory / "token.sh"
        entrypoint = self.directory / "entrypoint.sh"
        arguments_file = self.directory / "arguments"
        gate = self.directory / "token-loader-called"
        native.write_text('''#!/bin/sh
set -eu
printf '%s\\n' "$@" > "$KEEP_TEST_ARGUMENTS"
for argument in "$@"; do
    if [ "$argument" = --generate-credential ]; then
        [ "$#" -eq 1 ] || exit 23
        printf '%s\\n' "$KEEP_TEST_CREDENTIAL"
        exit 0
    fi
done
case "${1:-}" in
    --generate-token|--version|-V|--help|-h|export|import) exit 0 ;;
esac
exit 23
''', encoding="utf-8", newline="\n")
        native.chmod(0o755)
        token_loader.write_text('''load_keep_token() {
    printf called > "$KEEP_TEST_GATE"
    return 47
}
''', encoding="utf-8", newline="\n")
        script = (Path(__file__).parent / "entrypoint.sh").read_text(encoding="utf-8")
        script = script.replace("/usr/local/bin/keep", shlex.quote(str(native)))
        script = script.replace("/usr/local/lib/keep/token.sh", shlex.quote(str(token_loader)))
        entrypoint.write_text(script, encoding="utf-8", newline="\n")
        secret = "b" * 64
        environment = {"PATH": os.defpath, "KEEP_TEST_ARGUMENTS": str(arguments_file), "KEEP_TEST_GATE": str(gate),
                       "KEEP_TEST_CREDENTIAL": json.dumps({"secret": secret,
                           "tokenSha256": hashlib.sha256(secret.encode("ascii")).hexdigest()})}

        def run(*arguments):
            return subprocess.run([shutil.which("sh"), str(entrypoint), *arguments], env=environment,
                                  capture_output=True, timeout=10)

        smoke.validate_credential_output(run("--generate-credential"))
        self.assertFalse(gate.exists())
        invalid = [("--generate-credential", "--transport", "http"),
                   ("--generate-credential", "--data-dir", str(self.directory / "no-store")),
                   ("--generate-credential", "--generate-token"), ("--generate-token", "--generate-credential"),
                   ("--generate-credential", "--generate-credential"), ("--help", "--generate-credential")]
        for arguments in invalid:
            with self.subTest(arguments=arguments):
                result = run(*arguments)
                self.assertEqual(result.returncode, 23)
                self.assertFalse(result.stdout or gate.exists())
                self.assertEqual(arguments_file.read_text().splitlines(), list(arguments))
        for arguments in [("--generate-token",), ("--help",), ("--version",), ("export",), ("import",)]:
            self.assertEqual(run(*arguments).returncode, 0)
            self.assertFalse(gate.exists())
        self.assertEqual(run("--transport", "http").returncode, 47)
        self.assertTrue(gate.exists())
        self.assertFalse((self.directory / "no-store").exists())

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
