# Keep alpha

Keep stores personal collections of documents for an MCP client.
It saves text and JSON data in a local document store.
The first alpha supports Linux x64 GNU, Windows x64, and macOS Apple Silicon.
Choose npm or a native archive for your system.

## npm setup

It contains the same approved `0.1.0-alpha.1` executable as the native archives.
Install Node.js 24 or later with npm; you need no developer toolchain.
Keep optional dependencies enabled so npm installs the native package for your system.
On Windows, install the [Microsoft Visual C++ v14 Redistributable for x64](https://aka.ms/vc14/vc_redist.x64.exe).

Check the version:

```sh
npx -y @glidermcp/keep@next --version
```

For clients that accept JSON, configure this stdio command:

```json
{"mcpServers":{"keep":{"command":"npx","args":["-y","@glidermcp/keep@next"]}}}
```

On Windows, some clients require `cmd` to start npm command shims:

```json
{"mcpServers":{"keep":{"command":"cmd","args":["/c","npx","-y","@glidermcp/keep@next"]}}}
```

The `next` tag selects the alpha channel.
For this first publication, npm also creates `latest`.
An unqualified npm installation selects this alpha.
Use `@glidermcp/keep@0.1.0-alpha.1` instead to select this exact version.
For a global command, run `npm install --global @glidermcp/keep@next`.
Then configure the client with `keep` and no arguments.

## Native archive setup

Choose the archive for your system from the prerelease assets.

Download the archive and `SHA256SUMS` from the same prerelease.
Check the archive hash before you extract it.
On Linux, run `sha256sum <archive>` and compare the result with that archive's line in `SHA256SUMS`.
On macOS, `shasum -a 256 <archive>` gives a hash that you can compare with `SHA256SUMS`.
On Windows, run `Get-FileHash <archive> -Algorithm SHA256` in PowerShell and compare the result.
On Windows, install the latest [Microsoft Visual C++ v14 Redistributable for x64](https://aka.ms/vc14/vc_redist.x64.exe) before you run `keep.exe`.
Move `keep` or `keep.exe` to a directory on `PATH`, then run `keep --version`.

Configure an MCP client to start `keep` with stdio and no arguments.
For clients that accept JSON, the command entry can look like this:

```json
{"mcpServers":{"keep":{"command":"/absolute/path/to/keep","args":[]}}}
```

Use an absolute path to `keep.exe` on Windows.
## Documents and recovery

Keep creates a Personal space in `~/.glider/keep` when the client starts it.
Ask your MCP agent to create collections and documents, then read or search them.
See [the tool reference](tools.md) for request examples and revision rules.

The default search mode is lexical and needs no model.
Add `--semantic` to enable hybrid search.
Use `--model-dir` with an absolute directory to choose where Keep stores its pinned model files.
This option requires `--semantic`; the default shared model cache stays unchanged when you omit it.
The first enabled start can download about 86 MiB from the pinned model source.
Your MCP agent can report whether the model and index are ready.
Keep sends no document content or query to GliderMCP.
The optional model source receives a download request when Keep provisions the model.

Only one Keep process can use a store at a time.
Stop Keep before you copy `~/.glider/keep` as a backup.
You can also export a space with `keep export --output <file>` while the server is stopped.
Restore a full backup while Keep is stopped.
A restored backup loses writes made after that backup.
An older Keep executable can refuse a store from a later version.
Keep preserves an unsupported or damaged store for manual recovery.

Stop Keep before uninstall.
For a native archive, remove the executable from `PATH`.
For a global npm installation, run `npm uninstall --global @glidermcp/keep`.
For npx, remove the client entry.
The store and backups remain on disk until you remove them yourself.
This is an alpha release. Report defects in the public Keep repository.
The release notes state the exact tested systems and measured limits.
