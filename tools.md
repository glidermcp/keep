# Keep tool reference

This technical reference is for MCP agents and client integrators.

## Setup

Run one Keep server on your computer.
Connect all agents and sessions to it over HTTP.
They share the same document store.

Requires Node.js 24 or later for npm.
Supported systems are Linux x64 with glibc, macOS Apple Silicon, and Windows x64.
Linux 0.1.0-alpha.3 requires glibc 2.39 or later, such as Ubuntu 24.04.
Enable npm optional dependencies.
Windows 0.1.0-alpha.2 and later include the required Microsoft Visual C++ runtime.

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

### HTTP address, port, and proxy

Select another local port with `keep --transport http --port 8080`.
Connect clients to `http://127.0.0.1:8080/mcp`. The default port is 7340; `--port 0` selects an available port.
Keep reports the actual port on stderr after startup.

An HTTPS proxy uses `--public-url https://keep.example.com/mcp` and forwards the client's Bearer header.
The URL must use HTTPS and the exact `/mcp` path, without credentials, queries, fragments, or wildcard hosts.
Keep accepts that public Host authority or the exact local authority. It rejects every browser Origin header.
Keep has no account system in this alpha.

`--bind-address` requires Keep 0.1.0-alpha.3 or later.
Keep defaults to `127.0.0.1`. Select another listener address and port with:

```sh
keep --transport http --bind-address 0.0.0.0 --port 8080
```

Set `KEEP_HTTP_TOKEN` before startup, as shown above.
The address must be a literal IPv4 or IPv6 value, without brackets, a port, or a zone identifier.
The option requires explicit HTTP transport. Stdio, token generation, and offline file commands reject it.

The listener address does not allow arbitrary Host headers.
A concrete address accepts its exact IP and actual bound port as the local authority.
`0.0.0.0` accepts `127.0.0.1:<bound port>`; `::` accepts `[::1]:<bound port>`.
IPv6 authorities use brackets. A local Host can omit its port only when the actual port is 80.
The configured HTTPS public authority remains accepted; its Host can omit port 443.

For a container with the example above, Docker's `-p 127.0.0.1:8080:8080` option preserves the expected Host authority.
The host client uses `http://127.0.0.1:8080/mcp`. This fragment specifies a port mapping, not a Keep image or complete deployment.
A different host port requires a proxy that preserves the configured HTTPS authority or rewrites Host to the accepted local authority.
A proxy in another container can use the container network with the same Host rules.
Keep serves plain HTTP. Restrict network access and use an external HTTPS proxy for remote clients.
The token remains required for every listener address.

### Native executable

Download the archive for your system and `SHA256SUMS` from [GitHub Releases](https://github.com/glidermcp/keep/releases).
Verify its SHA-256 checksum.
Extract the archive.
Put `keep` or `keep.exe` on `PATH`.
Then follow the HTTP setup above.
The native executable runs without Node.js.


## Document API

An MCP client starts Keep as a stdio server when it runs `keep` without arguments.
The client uses the absolute path of the installed executable and no arguments for the personal store.
The server uses `~/.glider/keep` on Linux, macOS, and Windows.
One process owns the store at a time.
Keep exposes only document tools. It rejects the removed `--root` option before it creates state.
Use no arguments for the personal store, or `--data-dir <directory>` for another document store.
Keep refuses a selected directory containing `knowledge.db` or its recovery files, including during offline export and import.
It preserves those files and supplies no conversion or automatic import.

The caller uses `describe` to get the current limits and supported tools.
The caller uses `list_spaces` to get the persistent Personal space ID.
The caller uses `list_collections` and `list_documents` to inspect existing data.
The first `put_collection` call uses `ifRevision: "absent"` and a UUID `requestId`.
The first `put_document` call uses `ifRevision: "absent"` and a different UUID `requestId`.
After `list_spaces`, the caller creates a collection with the returned space ID:

```json
{"spaceId":"<space ID>","key":"recipes","ifRevision":"absent","requestId":"00000000-0000-4000-8000-000000000001","definition":{"title":"Recipes"}}
```

The caller sends that request to `put_collection` and retains its `collectionId`.
The caller then sends this request to `put_document`:

```json
{"spaceId":"<space ID>","collectionId":"<collection ID>","key":"lentil-soup","ifRevision":"absent","requestId":"00000000-0000-4000-8000-000000000002","document":{"title":"Lentil soup","body":"Simmer lentils. Add lemon."}}
```

The caller generates fresh UUID values for each new request.
For an update, the caller reads the current revision and passes it as `ifRevision`.
Keep rejects a stale revision so another writer's change survives.
If a write response is lost, the caller repeats the same payload with the same `requestId`.

To archive a document, the caller first reads it with `get_document`.
The caller preserves all mutable fields and replaces the document through `put_document` with `status: "archived"`.
The request uses the current revision as `ifRevision` and a fresh UUID `requestId`.
An omitted mutable field becomes its default. Use `status: "active"` to restore ordinary visibility.

For example, the caller creates a `recipes` collection with `title: "Recipes"`.
It creates a document with key `lentil-soup` and title `Lentil soup`.
It puts the recipe text in `body` and uses `search` with query `lentil` to find it.
The caller can create an `exercise` collection and store a workout with a date in `data`.
It uses `get_document` to read an exact document and `document_history` to inspect its revisions.
It uses `export_space` for a small inline transfer.
An operator uses `keep export --output <file>` for a complete file backup while the server is stopped.
An operator runs `keep import --input <file> --validate` before an import into another current store.
The file command help gives the required digest and revision values for an import.

An operator can instead use [HTTP setup](#setup) to share one server across clients.
The [HTTP address reference](#http-address-port-and-proxy) describes custom ports, proxies, and listener addresses.

An operator enables hybrid retrieval with `--semantic` on stdio or HTTP.
The optional `--model-dir <absolute-directory>` selects the directory containing the pinned model files.
It holds `config.json`, `tokenizer.json`, and `model.safetensors` directly. Keep adds no model-name subdirectory.
It requires `--semantic` in document mode. Relative paths and filesystem roots are rejected.
Keep downloads missing files and verifies their pinned checksums in that directory.
It does not fall back to the default cache when the selected directory fails.
Without this option, Keep retains the shared per-user model cache.
The default Windows model cache uses the operating system profile, independently of the document-store `USERPROFILE` setting.
Lexical search and exact document operations remain available when the model fails.

The operator stops Keep before a copy, export, import, or restore operation.
Keep refuses an unsupported internal layout and leaves its files in place.
Keep never deletes the store when you remove the executable.
