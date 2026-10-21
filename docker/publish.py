#!/usr/bin/env python3
"""Publish one tested image or verify an existing immutable version."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

from prepare import ROOT, approved, prepare, require

IMAGE = "docker.io/sacrorum/keep"
REPOSITORY = "sacrorum/keep"


def validate_image_tag(version, image_tag):
    require(len(image_tag) <= 128 and bool(re.fullmatch(re.escape(version) + r"-[a-z0-9][a-z0-9_.-]*", image_tag)),
            "Use the Keep version followed by an explicit container revision, such as -ubuntu26.04.")


def command(*args, env=None):
    result = subprocess.run(args, text=True, capture_output=True, env=env, timeout=1200)
    if result.returncode:
        raise RuntimeError(f"Command failed: {' '.join(args)}\n{result.stderr}")
    return result.stdout.strip()


def manifest_digest(image_tag):
    # An anonymous registry token has no account credentials or push permissions.
    url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{REPOSITORY}:pull"
    with urllib.request.urlopen(url, timeout=30) as response:
        token = json.load(response).get("token")
    require(isinstance(token, str) and bool(token), "The registry did not return an anonymous pull token.")
    accepted_types = ", ".join([
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.docker.distribution.manifest.v2+json"])
    request = urllib.request.Request(f"https://registry-1.docker.io/v2/{REPOSITORY}/manifests/{image_tag}",
                                    headers={"Authorization": "Bearer " + token,
                                             "Accept": accepted_types,
                                             "User-Agent": "Keep-Docker"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            digest = getattr(response, "headers", {}).get("Docker-Content-Digest", "")
            require(bool(re.fullmatch(r"sha256:[0-9a-f]{64}", digest)), "The registry returned an invalid image digest.")
            return digest
    except urllib.error.HTTPError as error:
        require(error.code == 404, f"The registry lookup failed with HTTP {error.code}. Publish requires a missing manifest.")
        errors = json.load(error).get("errors", [])
        require(len(errors) == 1 and errors[0].get("code") == "MANIFEST_UNKNOWN",
                "The registry did not confirm a missing manifest. Publish requires MANIFEST_UNKNOWN.")
        return None


def require_absent(image_tag):
    require(manifest_digest(image_tag) is None,
            "The image tag already exists. Use verify mode; version tags are immutable.")


def channel_expectations(args):
    next_digest = getattr(args, "expected_next_digest", "")
    latest_digest = getattr(args, "expected_latest_digest", "")
    require(bool(next_digest) == bool(latest_digest), "Supply both expected channel digests or neither.")
    for value in (next_digest, latest_digest):
        require(not value or value == "absent" or re.fullmatch(r"sha256:[0-9a-f]{64}", value),
                "An expected channel digest must be sha256 or absent.")
    return next_digest, latest_digest


def guard_channels(expected_next, expected_latest, target_digest):
    if not expected_next:
        return
    latest = manifest_digest("latest")
    current = manifest_digest("next")
    require((latest or "absent") == expected_latest, "The latest channel changed. Reconcile before promotion.")
    require((current or "absent") == expected_next or current == target_digest,
            "The next channel changed after approval. Reconcile before promotion.")


def push(tag):
    output = command("docker", "push", tag)
    matches = re.findall(r"digest: (sha256:[0-9a-f]{64})", output)
    require(len(matches) == 1, "The registry did not report one image digest.")
    return matches[0]


def anonymous_pull(tag):
    with tempfile.TemporaryDirectory(prefix="keep-anonymous-docker-") as directory:
        env = {**os.environ, "DOCKER_CONFIG": directory}
        output = command("docker", "pull", "--platform", "linux/amd64", tag, env=env)
    matches = re.findall(r"Digest: (sha256:[0-9a-f]{64})", output)
    require(len(matches) == 1, "Anonymous pull did not report one image digest.")
    return matches[0]


def publish(args):
    expected_next, expected_latest = channel_expectations(args)
    record = approved(args.version)
    validate_image_tag(args.version, args.image_tag)
    tag = f"{IMAGE}:{args.image_tag}"
    evidence = Path(args.evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    report = {"version": args.version, "imageTag": args.image_tag, "image": IMAGE,
              "platform": "linux/amd64", "mode": args.mode,
              "binarySha256": record["binarySha256"], "anonymousPull": False, "next": False}
    try:
        if args.mode == "publish":
            require_absent(args.image_tag)
            with tempfile.TemporaryDirectory(prefix="keep-docker-context-") as directory:
                prepare(args.version, directory, args.assets)
                command("docker", "build", "--platform", "linux/amd64", "--provenance=false",
                        "--build-arg", f"KEEP_VERSION={args.version}",
                        "--build-arg", f'KEEP_BINARY_SHA256={record["binarySha256"]}', "--tag", tag, directory)
            command(sys.executable, str(ROOT / "smoke.py"), "--image", tag, "--version", args.version,
                    "--output", str(evidence / "smoke.json"))
            # Recheck after the build and probe. Never replace an existing version tag.
            require_absent(args.image_tag)
            report["digest"] = push(tag)
            report["anonymousDigest"] = anonymous_pull(tag)
            require(report["digest"] == report["anonymousDigest"], "Anonymous pull returned another image digest.")
        else:
            report["digest"] = anonymous_pull(tag)
        immutable = f'{IMAGE}@{report["digest"]}'
        command(sys.executable, str(ROOT / "smoke.py"), "--image", immutable, "--version", args.version,
                "--output", str(evidence / "smoke.json"))
        report["anonymousPull"] = True
        if args.tag_next:
            # The global workflow queue can delay this job beyond the parent preflight.
            guard_channels(expected_next, expected_latest, report["digest"])
            # Copy the registry manifest, including an existing index and its provenance.
            command("docker", "buildx", "imagetools", "create", "--prefer-index=false",
                    "--tag", f"{IMAGE}:next", immutable)
            report["nextDigest"] = anonymous_pull(f"{IMAGE}:next")
            require(report["nextDigest"] == report["digest"], "The next tag returned another image digest.")
            report["next"] = True
            if expected_latest:
                require((manifest_digest("latest") or "absent") == expected_latest,
                        "The latest channel changed during promotion.")
    finally:
        (evidence / "image.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--image-tag", required=True, help="Immutable tag with the Keep version and container revision.")
    parser.add_argument("--mode", choices=["publish", "verify"], default="publish")
    parser.add_argument("--tag-next", action="store_true")
    parser.add_argument("--expected-next-digest", default="")
    parser.add_argument("--expected-latest-digest", default="")
    parser.add_argument("--assets")
    parser.add_argument("--evidence", default="evidence")
    publish(parser.parse_args())


if __name__ == "__main__":
    main()
