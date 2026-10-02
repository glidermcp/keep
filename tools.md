# Keep tool reference

This technical reference is for MCP agents and client integrators.
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

For example, the caller creates a `recipes` collection with `title: "Recipes"`.
It creates a document with key `lentil-soup` and title `Lentil soup`.
It puts the recipe text in `body` and uses `search` with query `lentil` to find it.
The caller can create an `exercise` collection and store a workout with a date in `data`.
It uses `get_document` to read an exact document and `document_history` to inspect its revisions.
It uses `export_space` for a small inline transfer.
An operator uses `keep export --output <file>` for a complete file backup while the server is stopped.
An operator runs `keep import --input <file> --validate` before an import into another current store.
The file command help gives the required digest and revision values for an import.

An operator can also start local HTTP with `keep --transport http`.
It binds to `127.0.0.1:7340` by default.
An operator generates a private value with `keep --generate-token`.
The operator sets `KEEP_HTTP_TOKEN` before starting the HTTP server.
The client sends `Authorization: Bearer <token>` with each MCP request.
The token gives full access to the selected store.
Keep has no account system in this alpha.
If a reverse proxy exposes Keep, its operator configures HTTPS and forwards the Bearer header.
Keep itself still binds only to loopback.

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
