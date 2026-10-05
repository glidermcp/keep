# Keep

**Shared memory for your AI agents.**

Keep is a local MCP server where agents save, organize, and find information.
Share knowledge across agents, conversations, and projects — with everything stored on your computer.

## Features

- Collections of text and JSON documents, with optional schemas and validation.
- Filters, custom sort order, saved views, and numeric aggregates.
- Full-text search and optional semantic search with a local model.
- Document history and revision checks that reject stale updates.
- Export and import for backups and transfers.
- Stdio for a single client, or token-protected HTTP for multiple clients.

## Setup

Run one Keep server on your computer.
Connect all agents and sessions to it over HTTP.
They share the same document store.

Requires Node.js 24 or later for npm.
Supported systems are Linux x64 with glibc, macOS Apple Silicon, and Windows x64.
Enable npm optional dependencies.
See the [release notes](https://github.com/glidermcp/keep/releases/tag/keep-v0.1.0-alpha.1) for Windows alpha.1 prerequisites.

Installation and token commands:

```sh
npm install --global @glidermcp/keep@next
keep --generate-token
```

The `next` tag selects the alpha release.
Save the generated token securely. Use it for the server and every client, including after a restart.
Replace `<token>` below with that value.

Start the server on macOS or Linux:

```sh
KEEP_HTTP_TOKEN="<token>" keep --transport http
```

Or in Windows PowerShell:

```powershell
$env:KEEP_HTTP_TOKEN = "<token>"
keep --transport http
```

Leave this process active while clients use it.
Each client connects to `http://127.0.0.1:7340/mcp` with the header `Authorization: Bearer <token>`.
The token grants full access to the shared store.

For clients that accept `mcpServers` JSON with `url` and `headers`:

```json
{
  "mcpServers": {
    "keep": {
      "url": "http://127.0.0.1:7340/mcp",
      "headers": {
        "Authorization": "Bearer <token>"
      }
    }
  }
}
```

Use the client's secret storage for the token when available.
The address is local to this computer.
Stdio is also available: configure a client to start `keep` without arguments.

### Native executable

Download the archive for your system and `SHA256SUMS` from [GitHub Releases](https://github.com/glidermcp/keep/releases).
Verify its SHA-256 checksum.
Extract the archive.
Put `keep` or `keep.exe` on `PATH`.
Then follow the HTTP setup above.
The native executable runs without Node.js.

## Storage and search

Documents stay on disk in `~/.glider/keep`, independently of any project or conversation.
Use `--data-dir <directory>` to select another store. Only one Keep process can open a store at a time.

Full-text search works without a model.
Add `--semantic` to enable local hybrid search; the first start can download about 86 MiB.
Document content and search queries stay on the server.

Stop Keep before you copy the store or run `keep export --output <file>` for a backup.
Keep also supports imports into another store. The documents stay on disk after you uninstall Keep.

See the [tool reference](tools.md) for the API, HTTP configuration, model options, and backup procedures.
Report problems in [GitHub Issues](https://github.com/glidermcp/keep/issues).
