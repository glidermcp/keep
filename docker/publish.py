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

IMAGE = "ghcr.io/glidermcp/keep"


def command(*args, env=None):
    result = subprocess.run(args, text=True, capture_output=True, env=env, timeout=1200)
    if result.returncode:
        raise RuntimeError(f"Command failed: {' '.join(args)}\n{result.stderr}")
    return result.stdout.strip()


def require_absent(tag, bootstrap=False):
    if bootstrap:
        require(os.environ.get("GITHUB_REPOSITORY") == "glidermcp/keep",
                "Bootstrap requires the public Keep repository workflow.")
        token = os.environ.get("GH_TOKEN")
        require(bool(token), "Bootstrap requires the workflow package token.")
        request = urllib.request.Request("https://api.github.com/orgs/glidermcp/packages/container/keep",
                                        headers={"Authorization": "Bearer " + token,
                                                 "Accept": "application/vnd.github+json",
                                                 "User-Agent": "Keep-Docker"})
        try:
            with urllib.request.urlopen(request, timeout=30):
                raise ValueError("The package already exists. Disable bootstrap.")
        except urllib.error.HTTPError as error:
            require(error.code == 404, "Package lookup failed. Bootstrap requires an authenticated HTTP 404.")
        return
    result = subprocess.run(["docker", "manifest", "inspect", tag], text=True, capture_output=True, timeout=60)
    require(result.returncode != 0, "The version tag already exists. Use verify mode; versions are immutable.")
    # Authentication and transport failures must not count as a missing tag.
    require("manifest unknown" in result.stderr.lower() or "no such manifest" in result.stderr.lower(),
            f"Cannot establish that the version tag is absent: {result.stderr}")


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
    record = approved(args.version)
    tag = f"{IMAGE}:{args.version}"
    evidence = Path(args.evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    report = {"version": args.version, "image": IMAGE, "platform": "linux/amd64", "mode": args.mode,
              "binarySha256": record["binarySha256"], "anonymousPull": False, "next": False}
    try:
        if args.mode == "publish":
            require_absent(tag, args.bootstrap)
            with tempfile.TemporaryDirectory(prefix="keep-docker-context-") as directory:
                prepare(args.version, directory, args.assets)
                command("docker", "build", "--platform", "linux/amd64", "--provenance=false",
                        "--build-arg", f"KEEP_VERSION={args.version}",
                        "--build-arg", f'KEEP_BINARY_SHA256={record["binarySha256"]}', "--tag", tag, directory)
            command(sys.executable, str(ROOT / "smoke.py"), "--image", tag, "--version", args.version,
                    "--output", str(evidence / "smoke.json"))
            # No build occurs after the smoke probe.
            report["digest"] = push(tag)
            report["anonymousDigest"] = anonymous_pull(tag)
            require(report["digest"] == report["anonymousDigest"], "Anonymous pull returned another image digest.")
        else:
            report["digest"] = anonymous_pull(tag)
            command(sys.executable, str(ROOT / "smoke.py"), "--image", tag, "--version", args.version,
                    "--output", str(evidence / "smoke.json"))
        report["anonymousPull"] = True
        if args.tag_next:
            command("docker", "tag", tag, f"{IMAGE}:next")
            report["nextDigest"] = push(f"{IMAGE}:next")
            require(report["nextDigest"] == report["digest"], "The next tag returned another image digest.")
            require(anonymous_pull(f"{IMAGE}:next") == report["digest"], "The anonymous next image differs.")
            report["next"] = True
    finally:
        (evidence / "image.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--mode", choices=["publish", "verify"], default="publish")
    parser.add_argument("--tag-next", action="store_true")
    parser.add_argument("--assets")
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--evidence", default="evidence")
    publish(parser.parse_args())


if __name__ == "__main__":
    main()
