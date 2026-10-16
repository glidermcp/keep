# Keep tool reference

This technical reference is for MCP agents and client integrators.

## Setup

Stop Keep before the first store access with 0.1.0-alpha.4.
Back up the complete store directory before you proceed.
Keep atomically upgrades schema 5 to schema 6 and preserves all content and IDs in Default.
Default retains the previous space ID. Version 0.1.0-alpha.3 cannot open schema 6.

To roll back, stop Keep.
Restore the backup that you created before the upgrade.
Then use the previous executable. That executable alone cannot reverse the upgrade.

Run one Keep server on your computer.
Connect all agents and sessions to it over HTTP.
They share the same document store.

For a persistent Docker service, use the [installation guide](https://glidermcp.com/keep/installation).
The steps below install the executable through npm or a native archive.

Requires Node.js 24 or later for npm.
Supported systems are Linux x64 with glibc, macOS Apple Silicon, and Windows x64.
Linux 0.1.0-alpha.3 and later require glibc 2.39 or later, such as Ubuntu 24.04.
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

The [Docker guide](https://github.com/glidermcp/keep/tree/main/docker) supplies the image, Compose files, and backup procedure.
For the custom port above, Docker's `-p 127.0.0.1:8080:8080` mapping preserves the expected Host authority.
The host client uses `http://127.0.0.1:8080/mcp`.
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


## Workspaces

Keep 0.1.0-alpha.4 uses contract `1.0-draft.k5.2` with workspaces and workspace deletion. Version 0.1.0-alpha.3 has one Personal space.
Check `describe` and the installed schemas before using these tools or options.
Workspaces use the existing `spaceId` argument. They organize collections; all workspaces share the owner's full-access token.

The caller selects the intended workspace through `list_spaces`. Use `isDefault` to identify the default, rather than list position.
`get_space` reads workspace metadata, its revision, and the content snapshotRevision together.
`put_space` creates or replaces metadata through a stable key, definition, ifRevision, and UUID requestId.
The definition requires title and accepts an IANA defaultTimeZone. An omitted defaultTimeZone becomes `UTC`, including on replacement.

Use `ifRevision: "absent"` to create, or the current revision to replace. Repeat the same request and requestId after an ambiguous response.

There is no collection move or default-workspace selection operation.

For authorized deletion, inspect the workspace and read `get_space` for both current revisions.
Call `delete_space` with spaceId, ifRevision, ifSnapshotRevision, and a fresh UUID requestId.
Default remains protected by identity after a title change or import; deletion returns default_space_protected.
Cascade defaults to false. Any collection, including an empty or archived collection, or retained content requires explicit `cascade: true`.
Otherwise, the request returns space_not_empty. Supply cascade only when the task authorizes deletion of all workspace content.

Deletion atomically removes the workspace, collections, documents, history, saved views, deletion records, and associated content receipts.
It removes that workspace's retrieval state and cursors. Other workspaces remain unchanged; catalog cursors require a fresh list request.
Exports and backups remain independent of deletion.
The receipt contains spaceId, a new deletion revision, disposition `deleted`, and replayed.

A metadata or content change returns revision_conflict with currentRevision and currentSnapshotRevision.
Read and inspect the workspace again before a new deletion request. Use a new requestId after reconciliation.
After an ambiguous response, repeat the original payload and requestId, including both original revision preconditions.

Workspace management receipts survive deletion and restart. Creation, replacement, and deletion retries return historical receipts and do not restore data.
A past creation receipt does not prove the workspace still exists. Content operations against the deleted workspace return not_found.
Management requests share one requestId namespace for the owner; another operation under an accepted ID returns request_conflict.
A fresh creation with the deleted key and `ifRevision: "absent"` produces a new workspace ID.

`describe` accepts an optional spaceId and returns the selected spaceId and defaultSpaceId. Omission selects the default workspace.
Hybrid budgets apply separately to each workspace: 512 documents, 4,096 chunks, and 8 MiB of searchable source text.
At most eight indexes remain resident. After eviction, `describe` or hybrid search for that workspace requests a rebuild.
Readiness can report `index_evicted`. Retry hybrid search after `describe` with the same spaceId reports ready.
Exact reads and lexical search remain available while the index rebuilds.

Stop Keep and back up the complete store before the first open with 0.1.0-alpha.4.
Opening a schema 5 store upgrades it atomically to schema 6, including through offline commands.
The previous Personal space becomes Default with the same UUID. All existing collections, documents, history, and retry records remain there.
No manual collection move is required. Published alpha.3 cannot open the upgraded store.

Offline export accepts `--space-id <uuid>`; omission exports the default workspace. Each export contains one workspace.
New exports use `inline-space-v4` (format 4) or `file-space-v4` (format 5). Import also accepts their earlier profiles.
They preserve workspace title, time zone, timestamps, and revision, alongside documents, views, history, and data-write retry receipts.
Workspace keys, permissions, default selection, and workspace management retry receipts do not transfer.

Import adopts the source workspace as the destination default with key `default` and retains the destination owner.
Older profiles supply no workspace title or time zone; import supplies `Default` and `UTC`.
Import requires a pristine whole store. An empty workspace in an existing store is insufficient.
Creating or updating workspace metadata makes a destination ineligible, even without collections or documents.
Deleting a newly created empty workspace does not make the store pristine again.

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
Published 0.1.0-alpha.3 has one persistent Personal space. The caller obtains its ID with `list_spaces`.
For a server with workspace support, follow [workspace selection](#workspaces).
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
An operator uses `keep export --output <file>` for a complete export of the default space while the server is stopped.
To back up every workspace and store-level retry record, copy the complete stopped store directory.
An operator runs `keep import --input <file> --validate` before an import into a pristine destination store.
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
