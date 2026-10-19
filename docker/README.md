# Keep with Docker

Run one Keep service and connect all clients to its HTTP endpoint.
The [Docker Hub image](https://hub.docker.com/r/sacrorum/keep) contains the verified Linux release executable.
Use `sacrorum/keep:0.1.0-alpha.5-ubuntu26.04` for this guide.
This alpha image supports `linux/amd64`. It includes its Ubuntu 26.04 runtime; the host needs no Node.js installation.
Use Docker Engine with Compose, or Docker Desktop in Linux container mode on an x64 computer.

## Get the configuration

For an existing store, complete [the backup steps](#update-and-back-up) before you start the new image.

Download and extract the [public repository archive](https://github.com/glidermcp/keep/archive/refs/heads/main.zip).
Open a terminal in its `docker` directory. Keep this directory for updates and backups.
Alternatively, clone the public repository:

```sh
git clone https://github.com/glidermcp/keep.git
cd keep/docker
```

The [site guide](https://glidermcp.com/keep/installation) explains the setup and client connection.
The steps below use the supplied `compose.yaml`.

## Create a token

Create the token once. Reuse it after a restart or update.
Keep grants full access to the store to every client with this token.
Store it outside chat, source control, and shared logs.
For restricted clients, use separate [scoped credentials](https://github.com/glidermcp/keep/blob/main/tools.md#access-administration). Keep the configured owner token private.

On Linux or macOS, run:

```sh
mkdir -p secrets
chmod 700 secrets
test ! -e secrets/keep_http_token || exit 1
docker run --rm sacrorum/keep:0.1.0-alpha.5-ubuntu26.04 --generate-token > secrets/keep_http_token
chmod 444 secrets/keep_http_token
```

In Windows PowerShell, run:

```powershell
New-Item -ItemType Directory -Force secrets | Out-Null
if (Test-Path secrets/keep_http_token) { throw 'The token file already exists.' }
docker run --rm sacrorum/keep:0.1.0-alpha.5-ubuntu26.04 --generate-token |
    Set-Content -Encoding ascii secrets/keep_http_token
```

Restrict the Windows directory to your account through its Security properties.
The container runs as UID and GID `10001`. Its secret mount must remain readable by that user.
The Linux directory restriction protects the file on the host; the mounted file permits the container to read it.
The image accepts `KEEP_HTTP_TOKEN_FILE` or `KEEP_HTTP_TOKEN`, but rejects both together.
The supplied Compose file uses the token file.

Use the offline image command to create a scoped credential:

```sh
docker run --rm --read-only --network none sacrorum/keep:0.1.0-alpha.5-ubuntu26.04 --generate-credential
```

This command needs no owner token or store.
Keep the JSON `secret` private. Give only `tokenSha256` to the administrator for registration.
Follow the [access reference](https://github.com/glidermcp/keep/blob/main/tools.md#access-administration) to assign the intended permissions.

## Start and connect

```sh
docker compose up -d
docker compose ps
```

Wait for the Keep service to become healthy.
Docker restarts the service after a failure or daemon restart, unless you stop it explicitly.
On Docker Desktop, enable Docker startup at sign-in if you need this behavior after a computer restart.

Configure clients with `http://127.0.0.1:7340/mcp` and `Authorization: Bearer <token>`.
Replace `<token>` with the saved value through your client's secret storage when available.
For clients that accept this JSON format:

```json
{
  "mcpServers": {
    "keep": {
      "url": "http://127.0.0.1:7340/mcp",
      "headers": { "Authorization": "Bearer <token>" }
    }
  }
}
```

Keep one registration per client. Remove a previous stdio registration that opens the same store.
Ask your agent: “Show the spaces and collections in Keep. Do not change any documents.”
Install the [Keep skill](https://github.com/glidermcp/glidermcp/tree/main/plugins/keep) after the connection works.
The skill starts no server.

The Compose port is available only on this computer.
For another local port, change both sides of the port mapping and the Keep `--port` argument to the same value.
Set the service environment variable `KEEP_HTTP_HEALTH_PORT` to that port so the health check uses the same address.
Keep validates the HTTP Host authority. Changing only the host port can produce a rejected request.
See the [HTTP reference](https://github.com/glidermcp/keep/blob/main/tools.md#http-address-port-and-proxy) for custom listeners and proxies.

## Storage and optional semantic search

The named volume `keep_data` mounts at `/data`; the document store is `/data/documents`.
Compose adds its project name to volume names. Preserve that project name when you update the service.
Only one Keep process can open a store at a time.
Use a Docker named volume unless you need a host directory.
For a host directory, give UID and GID `10001` write access before startup.

The separate `keep_models` volume mounts at `/models`.
Full-text search needs no model. To enable optional semantic search, add this service command to `compose.yaml`:

```yaml
    command: [--transport, http, --bind-address, 0.0.0.0, --port, '7340', --data-dir, /data/documents, --semantic, --model-dir, /models/snowflake-arctic-embed-xs]
```

Then run `docker compose up -d` again.
The first enabled start can download about 86 MiB. The model volume retains those files after container replacement.
The nested model directory keeps temporary download files inside the writable model volume.
For the remote configuration, append `--semantic` and `--model-dir /models/snowflake-arctic-embed-xs` to its existing command instead.
Retain its `--public-url` argument.

Keep has no account or shared-license integration in this alpha.
A mounted license directory does not activate a subscription.

## Update and back up

Use an exact image version for controlled updates. Set `KEEP_IMAGE` in a local `.env` file to select another published version.
For example, select the 0.1.0-alpha.5 image after its publication:

```dotenv
KEEP_IMAGE=sacrorum/keep:0.1.0-alpha.5-ubuntu26.04
```

Exact image tags remain unchanged. The `next` tag can move to a newer verified alpha image.
The container revision follows the native version; an Ubuntu update does not change the Keep executable version.

Stop Keep before the first store access with 0.1.0-alpha.5.
Back up the complete store directory before you proceed.
Keep atomically upgrades schema 5 or 6 to schema 7 and preserves content, IDs, history, and retry records.
A schema 5 upgrade creates Default with the previous space ID. A schema 6 upgrade preserves workspace IDs and collection assignments.
Alpha.4 and earlier cannot open schema 7.

To roll back, stop Keep.
Restore the backup that you created before the upgrade.
Then use the previous executable. That executable alone cannot reverse the upgrade.
Preserve the data volume, token file, and Compose configuration during the update.
The complete store includes history, principals, grants, credential digests, revocations, and audit.
A restart reopens that state; it does not grant new access or restore revoked credentials.
Restoring a backup restores its historical access state and loses later writes.

Back up the store before an update. The optional `backup.py` helper requires Python 3 and Docker Compose.
It stops Keep, copies `/data`, and restarts the service only if it was active before the backup.
It refuses an existing output filename. A failed copy receives a `.partial-...` suffix.

```sh
python backup.py backup keep-backup.tar.gz
docker compose pull keep
docker compose up -d keep
docker compose ps
```

Keep the backup in a private location. Copy it off this computer when you need recovery after a disk failure.
The archive includes the document store, but excludes tokens, Compose configuration, and the separate model cache.
Preserve those secrets and configuration separately. Models can be downloaded again.
Without Python, stop Keep before copying its complete data volume with your backup tool.
Never copy a live store. Do not use `docker compose down -v` to update; that command deletes named volumes.

### Restore into a new volume

Stop the original service before a transfer. Use a different Compose project name to create empty destination volumes:

```sh
docker compose stop keep
python backup.py restore keep-backup.tar.gz --project-name keep-restored
docker compose -p keep-restored up -d
```

The helper checks archive paths and refuses a nonempty destination store.
Verify documents, revision history, and access permissions through the restored service before removing the original volume.
Retain `-p keep-restored` for later commands against this service.
Do not run both projects on the same host port.

## Private access through your domain

The [private-domain guide](https://glidermcp.com/keep/setup) explains the supplied `remote/compose.yaml`.
It uses Tailscale for network access and Caddy for your domain's HTTPS certificate.
Cloudflare supplies DNS and certificate validation. The Compose file publishes no host ports and enables no Tailscale Funnel.

Use `docker compose -f remote/compose.yaml` for this deployment instead of the local Compose commands.
The remote project has separate data volumes. To move an existing store, back it up and restore into that project's empty volume.
For example, run `python backup.py restore keep-backup.tar.gz --compose-file remote/compose.yaml` before its first startup.
For remote backups, run `python backup.py backup keep-backup.tar.gz --compose-file remote/compose.yaml`.
Set the values in `remote/.env` before these commands, as described in the guide.
For remote image updates, set `KEEP_IMAGE` in that file instead of the local `.env` file.

## Troubleshooting

- **Unhealthy service:** inspect `docker compose logs keep`. Check the token file and volume permissions.
- **Unauthorized client:** check the configured credential, its expiry or revocation, and the principal's enabled state.
  Remove accidental spaces from the client header. Owner clients use the configured service token.
  Do not replace a scoped credential with the owner token.
- **Access denied:** check the intended space grants and credential operations.
- **Rejected Host:** use `127.0.0.1` and the configured port locally, or the configured HTTPS domain remotely.
- **Store lock:** stop the other Keep process that owns this store. Do not delete store files to bypass the lock.
- **Remote connection:** confirm Tailscale connectivity, DNS, the certificate, and access rules before changing Keep's token.

Keep rejects browser Origin headers. Connect with an MCP client rather than browser JavaScript.
See the [technical reference](https://github.com/glidermcp/keep/blob/main/tools.md) for offline transfers, limits, and recovery.

## Publish an image (maintainers)

The public repository runs [Publish Keep Docker](https://github.com/glidermcp/keep/actions/workflows/keep-docker-publish.yml) through a manual workflow dispatch.
A merge does not publish an image.
The workflow uses the approved public release executable and verifies its checksum before assembly.

Set the repository variable `DOCKERHUB_USERNAME` to `sacrorum`.
Store a Docker Hub personal access token with Read and Write permissions in the repository secret `DOCKERHUB_TOKEN`.
Delete permission is unnecessary. Replace the secret before the token expires, then revoke the previous token after verification.

Run the workflow from `main` with these inputs:

- `version`: the approved native release, such as `0.1.0-alpha.5`.
- `image_tag`: the native version plus a container revision, such as `0.1.0-alpha.5-ubuntu26.04`.
- `mode`: `verify` for an existing image, or `publish` for a new image tag. The workflow defaults to `verify`.
- `tag_next`: select this option to move `next` after the image passes verification.

Publish mode refuses an existing tag. Choose a new container revision when the base image or configuration changes.
Verify mode downloads the existing image without registry credentials and checks the executable and HTTP service.
The workflow retains its results in the `keep-docker-evidence` artifact.
