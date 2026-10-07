#!/usr/bin/env python3
"""Verify a public release and create a minimal Docker build context."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+-alpha\.[0-9]+")
FILES = {"keep", "LICENSE", "THIRD-PARTY-NOTICES.txt", "INSTALL.txt"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def approved(version):
    require(bool(VERSION.fullmatch(version)), "Use a full Keep alpha version.")
    records = json.loads((ROOT / "approved-releases.json").read_text(encoding="utf-8"))
    require(version in records, "This release has no Docker approval record.")
    return records[version]


def verify_assets(version, directory, record):
    directory = Path(directory)
    raw = (directory / "release.json").read_bytes()
    require(sha256(raw) == record["manifestSha256"], "The public release manifest differs from its approval.")
    manifest = json.loads(raw)
    require(manifest["version"] == version, "The public release version differs.")
    assets = manifest["assets"]
    require(len({item["target"] for item in assets}) == len(assets), "The manifest repeats a target.")
    require(len({item["archive"] for item in assets}) == len(assets), "The manifest repeats an archive.")
    checksums = "".join(f'{item["sha256"]}  {item["archive"]}\n' for item in assets)
    require((directory / "SHA256SUMS").read_bytes() == checksums.encode(), "Public checksums differ from the manifest.")
    linux = [item for item in assets if item["target"] == "linux-x64"]
    name = f"keep-v{version}-linux-x64.tar.gz"
    require(linux == [{"target": "linux-x64", "archive": name, "sha256": record["archiveSha256"]}],
            "The approved Linux target differs.")
    archive = directory / name
    require(sha256(archive.read_bytes()) == record["archiveSha256"], "The Linux archive checksum differs.")
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        require(len(members) == len(FILES) and {item.name for item in members} == FILES,
                "The Linux archive has unexpected or repeated paths.")
        require(all(item.isfile() and not item.issparse() for item in members),
                "The Linux archive must contain regular files.")
        contents = {item.name: source.extractfile(item).read() for item in members}
        require(next(item for item in members if item.name == "keep").mode & 0o111,
                "The Linux executable lacks executable permissions.")
    for name, key in [("keep", "binarySha256"), ("LICENSE", "licenseSha256"),
                      ("THIRD-PARTY-NOTICES.txt", "noticesSha256")]:
        require(sha256(contents[name]) == record[key], f"The approved {name} checksum differs.")
    require(contents["keep"].startswith(b"\x7fELF\x02\x01"), "Use the Linux ELF64 executable.")
    require(contents["keep"][18:20] == b"\x3e\x00", "Use the Linux x86_64 executable.")
    return contents


def download(version, directory):
    names = ["release.json", "SHA256SUMS", f"keep-v{version}-linux-x64.tar.gz"]
    for name in names:
        url = f"https://github.com/glidermcp/keep/releases/download/keep-v{version}/{name}"
        request = urllib.request.Request(url, headers={"User-Agent": "Keep-Docker"})
        with urllib.request.urlopen(request, timeout=120) as response, (directory / name).open("wb") as output:
            shutil.copyfileobj(response, output)


def prepare(version, destination, assets=None):
    record = approved(version)
    destination = Path(destination)
    require(not destination.exists() or not any(destination.iterdir()), "Use an empty Docker build directory.")
    with tempfile.TemporaryDirectory(prefix="keep-docker-assets-") as temporary:
        directory = Path(assets) if assets else Path(temporary)
        if not assets:
            download(version, directory)
        contents = verify_assets(version, directory, record)
    (destination / "native").mkdir(parents=True)
    for name, content in contents.items():
        (destination / "native" / name).write_bytes(content)
    (destination / "native/keep").chmod(0o755)
    for name in ["Dockerfile", ".dockerignore", "entrypoint.sh", "token.sh", "healthcheck.sh"]:
        shutil.copyfile(ROOT / name, destination / name)
    evidence = {"version": version, "platform": "linux/amd64", **record}
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--assets")
    args = parser.parse_args()
    print(json.dumps(prepare(args.version, args.destination, args.assets), indent=2))


if __name__ == "__main__":
    main()
