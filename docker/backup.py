#!/usr/bin/env python3
"""Copy or restore a complete stopped Compose store."""

import argparse
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import uuid


def run(compose, *args, **kwargs):
    return subprocess.run([*compose, *args], check=True, timeout=180, **kwargs)


def backup(compose, output):
    output = Path(output)
    # Exclusive creation prevents an accidental overwrite of a previous backup.
    with output.open("xb") as target:
        running = run(compose, "ps", "--status", "running", "--quiet", "keep", capture_output=True).stdout.strip()
        stopped = False
        try:
            run(compose, "stop", "--timeout", "60", "keep")
            stopped = True
            run(compose, "run", "--rm", "--no-deps", "-T", "--entrypoint", "tar", "keep",
                "-C", "/data", "-czf", "-", ".", stdout=target)
        except Exception:
            # A failed archive remains named .partial so it cannot look complete.
            target.close()
            output.rename(output.with_name(output.name + ".partial-" + uuid.uuid4().hex))
            raise
        finally:
            if running and stopped:
                run(compose, "start", "keep")


def validate_backup(path):
    with tarfile.open(path, "r:gz") as source:
        seen = set()
        for member in source.getmembers():
            normalized = PurePosixPath(member.name)
            if normalized.is_absolute() or ".." in normalized.parts or "\\" in member.name:
                raise ValueError("The backup contains an unsafe path.")
            if not (member.isfile() or member.isdir()) or member.issparse():
                raise ValueError("The backup must contain regular files and directories.")
            if str(normalized) in seen:
                raise ValueError("The backup repeats a path.")
            seen.add(str(normalized))
        if "documents" not in seen:
            raise ValueError("The backup has no document directory.")


def restore(compose, path):
    validate_backup(path)
    running = run(compose, "ps", "--status", "running", "--quiet", "keep", capture_output=True).stdout.strip()
    if running:
        raise ValueError("Stop Keep before restore. Select a fresh destination volume.")
    script = ('test -z "$(find /data -mindepth 1 -maxdepth 1 ! -name documents -print -quit)" '
              '&& test -z "$(find /data/documents -mindepth 1 -print -quit)" '
              '&& exec tar --no-same-owner -C /data -xzf -')
    with Path(path).open("rb") as source:
        run(compose, "run", "--rm", "--no-deps", "-T", "--entrypoint", "sh", "keep", "-ec", script, stdin=source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "restore"])
    parser.add_argument("file")
    parser.add_argument("--compose-file", default=str(Path(__file__).with_name("compose.yaml")))
    parser.add_argument("--project-name")
    args = parser.parse_args()
    compose = ["docker", "compose", "-f", args.compose_file]
    if args.project_name:
        compose += ["-p", args.project_name]
    (backup if args.action == "backup" else restore)(compose, args.file)


if __name__ == "__main__":
    main()
