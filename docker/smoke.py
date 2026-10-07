#!/usr/bin/env python3
"""Probe the final Docker image with an isolated store and synthetic token."""

import argparse
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid

from prepare import approved, require


def docker(*args, check=True, **kwargs):
    result = subprocess.run(["docker", *args], capture_output=True, timeout=180, **kwargs)
    if check and result.returncode:
        raise RuntimeError(f"Docker command failed: {args[0]}\n{result.stderr.decode(errors='replace')}")
    return result


def text(*args):
    return docker(*args).stdout.decode().strip()


def probe(image, version):
    record = approved(version)
    require(text("run", "--rm", image, "--version") == f"keep {version}", "The image version differs.")
    require(text("run", "--rm", "--entrypoint", "sha256sum", image, "/usr/local/bin/keep").split()[0]
            == record["binarySha256"], "The image executable differs from its approval.")
    config = json.loads(text("image", "inspect", image))[0]
    require(config["Architecture"] == "amd64" and config["Os"] == "linux", "The image platform differs.")
    require(config["Config"]["User"] == "10001:10001", "The image must use the dedicated nonroot user.")
    report = {"version": version, "imageId": config["Id"], "binarySha256": record["binarySha256"], "checks": []}
    report["checks"].append("approved-binary-version-platform-nonroot")
    name = "keep-probe-" + uuid.uuid4().hex[:12]
    volume = name + "-data"
    restored = name + "-restored"
    active = []
    with tempfile.TemporaryDirectory(prefix="keep-image-probe-") as directory:
        token = secrets.token_hex(32)
        secret = Path(directory) / "token"
        secret.write_text(token + "\n", encoding="ascii", newline="\n")
        secret.chmod(0o644)
        mount = ["--mount", f"type=bind,source={secret},target=/run/secrets/keep_http_token,readonly"]
        try:
            missing = docker("run", "--rm", image, check=False)
            require(missing.returncode != 0, "Startup accepted a missing token.")
            secret.write_text("invalid\n", encoding="ascii", newline="\n")
            invalid = docker("run", "--rm", *mount, image, check=False)
            require(invalid.returncode != 0, "Startup accepted a malformed token.")
            secret.write_text(token + "\n", encoding="ascii", newline="\n")
            conflict = docker("run", "--rm", *mount, "-e", "KEEP_HTTP_TOKEN_FILE=/run/secrets/keep_http_token",
                              "-e", "KEEP_HTTP_TOKEN=" + "b" * 64, image, check=False)
            require(conflict.returncode != 0, "Startup accepted conflicting token sources.")
            report["checks"].append("missing-malformed-conflicting-token-rejected")
            text("volume", "create", volume)
            text("volume", "create", restored)

            def mapped_url():
                port = text("port", name, "7340/tcp").rsplit(":", 1)[1]
                return "http://127.0.0.1:" + port + "/mcp"

            def start(store):
                text("run", "-d", "--name", name, "--read-only", "--cap-drop", "ALL", "--security-opt",
                     "no-new-privileges:true", "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m", "--stop-timeout", "60",
                     "-p", "127.0.0.1::7340", "-v", f"{store}:/data", *mount, image,
                     "--transport", "http", "--bind-address", "0.0.0.0", "--port", "7340", "--data-dir",
                     "/data/documents", "--public-url", "https://keep.example.test/mcp")
                active.append(name)
                return mapped_url()

            url = start(volume)

            def rpc(method, params=None, auth=token, host="127.0.0.1:7340", origin=None):
                headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                           "MCP-Protocol-Version": "2025-11-25", "Host": host}
                if auth is not None:
                    headers["Authorization"] = "Bearer " + auth
                if origin is not None:
                    headers["Origin"] = origin
                payload = {"jsonrpc": "2.0", "id": 1, "method": method}
                if params is not None:
                    payload["params"] = params
                request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
                try:
                    with urllib.request.urlopen(request, timeout=8) as response:
                        return response.status, json.load(response)
                except urllib.error.HTTPError as error:
                    return error.code, {}

            def ready():
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    try:
                        status, value = rpc("tools/list")
                        if status == 200 and value.get("result", {}).get("tools"):
                            return
                    except (OSError, ValueError):
                        pass
                    time.sleep(0.25)
                raise RuntimeError("The image did not become ready.")

            def call(tool, arguments):
                status, value = rpc("tools/call", {"name": tool, "arguments": arguments})
                require(status == 200 and "error" not in value, f"The {tool} request failed.")
                result = value["result"]
                require(not result.get("isError"), f"The {tool} tool failed: {result}")
                return result["structuredContent"]

            ready()
            require(text("exec", name, "id", "-u") == "10001", "The running process user differs.")
            require(text("exec", name, "cat", "/proc/1/comm") == "keep", "Keep must be PID 1.")
            for auth in [None, "c" * 64]:
                require(rpc("tools/list", auth=auth)[0] == 401, "Authentication did not reject the request.")
            require(rpc("tools/list", host="evil.example")[0] == 403, "Keep accepted an arbitrary Host.")
            require(rpc("tools/list", origin="null")[0] == 403, "Keep accepted a browser Origin.")
            require(rpc("tools/list", host="keep.example.test")[0] == 200, "Keep rejected the configured public authority.")
            text("exec", name, "/usr/local/lib/keep/healthcheck.sh")
            report["checks"].append("http-auth-host-origin-public-authority-pid1-health")
            rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                               "clientInfo": {"name": "keep-image-probe", "version": "1"}})
            space = call("list_spaces", {})["items"][0]["id"]
            collection = call("put_collection", {"spaceId": space, "key": "image-probe", "ifRevision": "absent",
                              "requestId": str(uuid.uuid4()), "definition": {"title": "Image probe"}})["collectionId"]
            created = call("put_document", {"spaceId": space, "collectionId": collection, "key": "persistent",
                           "ifRevision": "absent", "requestId": str(uuid.uuid4()),
                           "document": {"title": "Persistent", "body": "Docker store probe"}})
            arguments = {"spaceId": space, "documentId": created["documentId"]}
            before = call("get_document", arguments)
            text("stop", "--time", "60", name)
            state = json.loads(text("inspect", name))[0]["State"]
            require(state["ExitCode"] == 0 and not state["OOMKilled"], "Keep did not stop gracefully.")
            text("start", name)
            url = mapped_url()
            ready()
            require(call("get_document", arguments) == before, "Restart changed the saved document.")
            text("stop", "--time", "60", name)
            text("rm", name)
            active.remove(name)
            archive = docker("run", "--rm", "--entrypoint", "tar", "-v", f"{volume}:/data:ro", image,
                             "-C", "/data", "-czf", "-", ".").stdout
            restore = subprocess.run(["docker", "run", "--rm", "-i", "--entrypoint", "tar", "-v",
                                      f"{restored}:/data", image, "--no-same-owner", "-C", "/data", "-xzf", "-"],
                                     input=archive, capture_output=True, timeout=120)
            require(restore.returncode == 0, "The stopped store backup could not be restored.")
            url = start(restored)
            ready()
            require(call("get_document", arguments) == before, "Restore changed the saved document.")
            report["checks"].append("write-restart-graceful-stop-full-store-backup-restore-recreate")
            # A replaced token file makes the active process unhealthy until restart.
            secret.write_text("d" * 64 + "\n", encoding="ascii", newline="\n")
            require(docker("exec", name, "/usr/local/lib/keep/healthcheck.sh", check=False).returncode != 0,
                    "The health check accepted a token that the server rejected.")
            log_result = docker("logs", name)
            logs = (log_result.stdout + log_result.stderr).decode(errors="replace")
            require(token not in logs and "d" * 64 not in logs, "The container logs expose a token.")
            secret.write_text(token + "\n", encoding="ascii", newline="\n")
            report["checks"].append("health-auth-failure-token-free-logs")
        finally:
            for container in active:
                docker("rm", "-f", container, check=False)
            for store in [volume, restored]:
                docker("volume", "rm", store, check=False)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    report = probe(args.image, args.version)
    content = json.dumps(report, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(content, encoding="utf-8", newline="\n")
    print(content, end="")


if __name__ == "__main__":
    main()
