# Keep tool reference

This technical reference is for MCP agents and client integrators.

Keep 0.1.0-alpha.6 uses contract `1.0-draft.k5.4`, schema 7, and thirty-one tools.
It includes [scoped access](#access-administration) and [record links](#record-links).
Alpha.5 uses `1.0-draft.k5.3`, schema 7, and twenty-nine tools.

## Setup

Before an update, stop Keep.
Back up its complete store directory before you proceed.
Keep atomically upgrades schema 5 or 6 to schema 7 and preserves content, IDs, history, and retry records.
A schema 5 upgrade creates Default with the previous space ID. A schema 6 upgrade preserves workspace IDs and collection assignments.
Alpha.4 and earlier cannot open schema 7.

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
Save the generated owner token securely. Use it for the server and clients that need full access, including after a restart.
For restricted clients, register separate [scoped credentials](#register-and-rotate-a-scoped-credential).
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
Keep has local principals and credentials. It provides no hosted account service.

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

Keep 0.1.0-alpha.5 supports workspaces, protected workspace deletion, and scoped access. Version 0.1.0-alpha.3 has one Personal space.
Check `describe` and the installed schemas before using these tools or options.
Workspaces use the existing `spaceId` argument. Scoped credentials expose only workspaces permitted by current authority.

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
Management requests share one requestId namespace per principal; another operation under an accepted ID returns request_conflict.
A fresh creation with the deleted key and `ifRevision: "absent"` produces a new workspace ID.

`describe` accepts an optional spaceId and returns the selected spaceId and defaultSpaceId. Omission selects an accessible workspace.
Its defaultSpaceId is null when Default is inaccessible. With no accessible workspace, both IDs are null.
Hybrid budgets apply separately to each workspace: 512 documents, 4,096 chunks, and 8 MiB of searchable source text.
At most eight indexes remain resident. After eviction, `describe` or hybrid search for that workspace requests a rebuild.
Readiness can report `index_evicted`. Retry hybrid search after `describe` with the same spaceId reports ready.
Exact reads and lexical search remain available while the index rebuilds.

Follow the [backup and migration steps](#setup) before the first open, including through offline commands.
No manual collection move is required.

Offline export accepts `--space-id <uuid>`; omission exports the default workspace. Each export contains one workspace.
Single-owner exports use `inline-space-v4` (format 4) or `file-space-v4` (format 5). Import also accepts their earlier profiles.
[Organization content transfers](#source-upgrades-and-organization-transfers) omit operational receipts and authority.
Single-owner profiles preserve workspace title, time zone, timestamps, and revision, alongside documents, views, history, and data-write retry receipts.
Workspace keys, permissions, default selection, and workspace management retry receipts do not transfer.

Import adopts the source workspace as the destination default with key `default` and retains the destination owner.
Older profiles supply no workspace title or time zone; import supplies `Default` and `UTC`.
Import requires a pristine whole store. An empty workspace in an existing store is insufficient.
Creating or updating workspace metadata makes a destination ineligible, even without collections or documents.
Deleting a newly created empty workspace does not make the store pristine again.

<a id="access-administration-unreleased"></a>

## Access administration

Keep 0.1.0-alpha.5 uses contract `1.0-draft.k5.3` with scoped access and eight administration tools.
Use the installed schemas before attempting this workflow. Personal stdio and the configured `KEEP_HTTP_TOKEN` retain full bootstrap-owner authority.
Scoped credentials intersect enabled identity, current workspace membership, credential workspace IDs, operation scopes, expiry, and revocation.
A credential scope alone grants no membership. A workspace owner is distinct from a store administrator.

| Authority | Required role and credential scope |
| --- | --- |
| Discovery, reads, history, search, exact queries, views, and aggregates | Workspace membership and `read` |
| Document, collection, and view writes; document deletion | `editor` or `owner`, with `write` |
| Workspace metadata replacement, deletion, and grants | `owner`, with `manage` |
| Workspace export | Workspace membership and explicit `export` |
| Principal and credential administration, workspace creation, import, and audit | Administrator identity with `admin` |

`reader`, `editor`, and `owner` are membership roles. Credential operations are `read`, `write`, `manage`, `export`, and `admin`.

| Membership role | Eligible operations |
| --- | --- |
| reader | `read`, `export` |
| editor | `read`, `write`, `export` |
| owner | `read`, `write`, `manage`, `export` |

Roles define eligibility. Effective operations also require the credential scope and workspace.
A scoped administrator still needs workspace membership and scope for workspace content operations.
The bootstrap owner stays enabled and administrative, with protected owner grants. Imported actor metadata grants no authority.
Documents remain private. Keep provides no anonymous or public document access.

### Discover and recover within granted access

`list_spaces` returns only accessible workspaces and effective permissions.
`describe` without spaceId selects an accessible workspace. Its defaultSpaceId is null when Default is inaccessible.
With no accessible workspace, describe returns general capabilities with null workspace IDs.
Tool capability readiness reports product support, not current caller permission.
Retrieval readiness reports the selected workspace state.
Keep returns `not_found` for absent or inaccessible resources. A visible workspace can return `permission_denied` for an unauthorized operation.
Do not infer resource existence from either response or automatically obtain broader credentials.

Every operation rechecks current authority. After accepted revocation, subsequent operations fail, including calls through an existing connection.
An operation already executing can finish before revocation commits.
Restart preserves principals, memberships, credential digests, expiry, and revocation state.
Cursors bind to the principal, credential, authorization revision, and existing query/snapshot state.
After `cursor_expired`, repeat discovery or the original query without a cursor under current authority.
Content retries remain principal-based across credential rotation, but the current credential must still authorize the operation and workspace.
A historical receipt proves the earlier mutation; it does not restore content or prove current access or state.

### Administration arguments

Every mutation requires a UUID requestId and ifRevision. Use `absent` for creation and the current revision for replacement.
`revoke_credential` requires the current revision. Read the appropriate list for revisions before changes.

| Tool | Additional required arguments | Optional arguments |
| --- | --- | --- |
| put_principal | principalId, definition | None |
| put_space_grant | spaceId, principalId, role | None |
| put_credential | credentialId, principalId, tokenSha256, spaceIds, operations, expiresAt | replacesCredentialId, ifReplacesRevision |
| revoke_credential | credentialId | None |
| list_principals | None | limit, cursor |
| list_space_grants | spaceId | limit, cursor |
| list_credentials | None | principalId, limit, cursor |
| list_audit_events | None | limit, cursor |

The principal definition requires name, kind (`human` or `agent`), enabled, and administrator. IDs are UUIDs.
A grant role is `reader`, `editor`, `owner`, or null. Null revokes membership and retains its revision.
Grant administration requires owner membership and manage scope. The other administration tools require store administration.
Lists accept limit 1–50, default 20, and return items, nextCursor, snapshotRevision, and exact coverage.
Credential lists exclude secrets and digests. Audit pages retain the first page's upper bound.
Mutation receipts contain target IDs, revision, disposition, and replayed.

After a revision conflict, read current metadata and reconcile before a new request with a new requestId.
After an ambiguous response, retain the original payload and requestId.
An administration retry can return a historical receipt after later changes; inspect current metadata before relying on its state.
Current authorization still applies. A denied retry does not justify broader credentials or a fresh mutation.

### Register and rotate a scoped credential

For an authorized credential setup, the operator runs `keep --generate-credential` locally.
It prints JSON with secret and tokenSha256 to operator stdout without opening a store.
Keep this output outside chat, source control, documents, and logs. Store the secret in the client's secret storage.
The digest covers the 64 ASCII lowercase hexadecimal secret characters, without the newline.
Generation neither registers a credential nor grants authority. Send only tokenSha256 through `put_credential`; never send the secret through MCP.

The administrator registers a new credential UUID, principalId, explicit spaceIds and operations, and a future expiresAt.
Space IDs permit at most 128 unique UUIDs. Operations permit at most five unique values; there is no implicit wildcard.
The client uses the secret as its Bearer token. The principal also needs current membership in each intended workspace.
A credential ID keeps its original principal and digest. A revoked ID cannot become active again.

Rotation registers a new credential ID with `ifRevision: "absent"`, replacesCredentialId, and the old credential's ifReplacesRevision.
Insertion and revocation commit atomically. A stale rotation leaves the old credential valid.
Read `list_credentials` again after a conflict and reconcile before a fresh rotation request.
`--generate-token` and the configured owner token keep their existing behavior; scoped rotation does not rotate that owner token.

### Audit and recovery

Successful content and administration mutations append audit atomically with their state and retry receipts.
Events retain principal and credential identity or trusted authentication class, operation/resource IDs, revisions, request ID, and server time.
They exclude content, titles, excerpts, secrets, and digests. Reads, denials, and receipt replays create no new event.
Audit remains for the store lifetime, including after workspace deletion or principal disable. There is no audit edit or deletion tool.
A stopped-store backup preserves authority, audit, and operational retries. Document exports omit authority and audit.
Protect backups as sensitive data; restored backups contain their historical access state.

### Source upgrades and organization transfers

Before an update, stop Keep.
Back up its complete store directory before you proceed.
The build upgrades schema 5 or 6 atomically to schema 7, preserving content, identity, history, and retry records.
Published alpha.4 and earlier cannot open schema 7. Rollback requires the previous executable and the pre-upgrade backup.
Offline commands perform the same upgrade. Access metadata alone does not prevent a pristine import.

A workspace with other principals' operational receipts or actors that identify other local principals uses an organization content-transfer profile.
Imported foreign actors remain provenance. Profile selection is automatic for the selected workspace.
Inline format 5 uses `organization-content-v1`; file format 6 uses `organization-file-content-v1`.
They preserve content, IDs, revisions, schemas, views, links, historical actors, and tombstones.
They exclude operational retries, principals, grants, credentials, and audit. Metadata reports operationalReceipts `excluded`, retries zero, and coverage `content`.
Legacy single-owner profiles retain data-write retries and report operationalReceipts `included` and coverage `complete`.
Neither transfer is a complete store backup. Copy the complete stopped store to preserve operational retries, authority, and audit.
For MCP import, spaceId names the pristine destination workspace before import.
After apply, new calls use the adopted source ID. Retries retain the original destination ID and payload.
Import retains local authority and adds its bootstrap owner's grant for the adopted workspace.
Previous local grant rows can remain; they give no access to absent workspaces.
Existing scoped credentials retain their original space ID limits. Imported actor identities grant no authority.

## Record links

These two read tools require Keep 0.1.0-alpha.6 and contract `1.0-draft.k5.4`.
Alpha.5 has no record-link tools. Check `describe` and the installed schemas before use.

| Tool | Required arguments | Optional arguments | Result |
| --- | --- | --- | --- |
| `get_document_link` | `spaceId`, `documentId` | `revision` | `{uri, storeId, spaceId, documentId, revision}` |
| `resolve_document_link` | `uri` | None | The complete current document or specified revision, as returned by `get_document` |

The caller selects the intended document, then requests its link with `get_document_link`.
Omit `revision` for a live link that follows later edits. Supply a revision from `document_history` to pin that historical value.
The request rejects an explicit null revision. The result uses `revision: null` for a live link.
Link creation checks current read access and target existence. It changes no document, revision, retry receipt, or audit event.

The canonical forms are:

```text
keep://<storeId>/s/<spaceId>/d/<documentId>
keep://<storeId>/s/<spaceId>/d/<documentId>/r/<revisionId>
```

Each ID is a lowercase, hyphenated UUID. The URI permits exact ASCII and at most 160 bytes.
Queries, fragments, credentials, ports, percent encoding, whitespace, alternate case, and trailing slashes are invalid.
Malformed URIs return `invalid_arguments`; a URI above 160 bytes returns `limit_exceeded`.
Copy the returned URI without changes.

The recipient uses `resolve_document_link` through an existing, trusted connection to the same Keep store.
The link grants no authority. Both tools check current principal status, workspace membership, credential scopes, expiry, and revocation.
A foreign store, missing target, or inaccessible workspace returns `not_found` without confirming existence.
A caller with workspace membership but insufficient operation scope can receive `permission_denied`.
Do not obtain owner credentials merely to resolve a denied link.

Both forms can read archived documents. Deleted documents and deleted workspaces cannot resolve, including through historical links.
These addresses provide no browser page, public access, automatic connection, or network fetch.
They remain separate from the same-space relation objects in a document's `links` field.

A restart or complete stopped-store backup restoration preserves the store ID and link identity.
A workspace import retains the destination store ID, even when it preserves workspace and document IDs. Generate new links in that destination.
Alpha.5 and alpha.6 both use schema 7. This change requires no schema upgrade for an alpha.5 store.

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
Without explicit fields, `list_documents` returns identity plus title, summary, tags, createdAt, and updatedAt.
The default omits data, body, and status. Omission does not prove that the document lacks a value.
Request explicit fields or use `get_document` when the task needs omitted values.
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
