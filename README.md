# Keep

Shared memory for your agents, stored on your computer.
Keep lets agents save, organize, and find documents across conversations and projects.

## Setup

Keep is an alpha. Run one server and connect your clients to its token-protected HTTP endpoint.
All clients share the same store. Only one process can open that store at a time.

Before an update, stop Keep.
Back up its complete store directory before you proceed.
Keep atomically upgrades schema 5 or 6 to schema 7 and preserves content, IDs, history, and retry records.
A schema 5 upgrade creates Default with the previous space ID. A schema 6 upgrade preserves workspace IDs and collection assignments.
Alpha.4 and earlier cannot open schema 7.

To roll back, stop Keep.
Restore the backup that you created before the upgrade.
Then use the previous executable. That executable alone cannot reverse the upgrade.

For Docker on an x64 computer, follow [Install with Docker](https://glidermcp.com/keep/installation).
The [Docker Hub image](https://hub.docker.com/r/sacrorum/keep) includes its Linux runtime.
The Compose files provide persistent storage, a token file, and automatic restart.
Use the [private-domain guide](https://glidermcp.com/keep/setup) for HTTPS access through Tailscale and Cloudflare DNS.

For npm, install Node.js 24 or later and keep optional dependencies enabled:

```sh
npm install --global @glidermcp/keep@next
```

The `next` tag selects the alpha. Supported systems are Linux x64 with glibc, macOS Apple Silicon, and Windows x64.
Linux 0.1.0-alpha.3 and later require glibc 2.39 or later, such as Ubuntu 24.04.
Windows 0.1.0-alpha.2 and later include the required Microsoft Visual C++ runtime.
Alpha.1 has separate prerequisites in its [release notes](https://github.com/glidermcp/keep/releases/tag/keep-v0.1.0-alpha.1).
Follow [HTTP setup and native installation](https://github.com/glidermcp/keep/blob/main/tools.md#setup) to create a token and connect clients.
Store the configured owner token securely. It grants full access to the store; do not share it in chat or commit it.

Alpha.5 lets you limit each person or agent to selected workspaces and operations.
Workspace roles control read, edit, and management permissions. Separate credentials can restrict those permissions further, with expiry and revocation.
See [access administration](https://github.com/glidermcp/keep/blob/main/tools.md#access-administration) for setup.
Documents are private by default; Keep provides no anonymous or public document access.

Install the [Keep skill](https://github.com/glidermcp/glidermcp/tree/main/plugins/keep) after your connection works.
This skill-only plugin starts no server and adds no MCP registration. It uses your existing connection.

## What you can do

- Keep project decisions and reusable notes available across sessions.
- Grant each person or agent access to selected workspaces, with expiry and revocation.
- Organize collections into workspaces while preserving existing content and history.
- Delete workspaces, except Default. A non-empty workspace requires explicit cascade to remove its contents.
- Organize text and JSON documents into collections, with optional schemas.
- Find records with filters, full-text search, and optional local semantic search.
- Inspect document history and update records with revision checks.

Ask your agent: “Find the deployment decision for this project and explain its source and date.”
For an update: “Save this agreed decision in the existing project collection, preserving other fields.”

Record references require Keep 0.1.0-alpha.6 or later.
They identify the current document or one historical revision.
The recipient still needs authorized access to the same store. A link grants no access.
Live links follow later edits. Pinned links retain their selected revision. Neither opens a browser page or enables public access.
See the [record-link reference](https://github.com/glidermcp/keep/blob/main/tools.md#record-links) for the required server contract.

## Storage and updates

The default store is `~/.glider/keep`, independent of any project or conversation.
A different store uses `--data-dir`. Do not start another server for each agent or working directory.
Document content and queries stay on the server. Your MCP client controls what returned content reaches its model provider.
Full-text search needs no model. Optional semantic search can download about 86 MiB at first use.

Stop the shared server before updating its executable or copying, exporting, importing, or restoring its store.
Update through the same installation channel, then restart with the same data directory and token.
Keep retains documents when you uninstall the executable.
See the [tool and backup reference](https://github.com/glidermcp/keep/blob/main/tools.md) before a transfer or restore.

[Report a problem](https://github.com/glidermcp/keep/issues). Product terms are in the package LICENSE file.
