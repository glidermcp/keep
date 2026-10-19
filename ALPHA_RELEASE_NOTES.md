# Keep 0.1.0-alpha.5 release notes

Keep provides shared local memory for AI agents through stdio or protected HTTP.
This alpha provides Linux x64 with glibc, Windows x64, and macOS Apple Silicon archives.
The Linux archive requires glibc 2.39 or later, such as Ubuntu 24.04.
Windows includes the required Microsoft Visual C++ runtime.

## Scoped access and store upgrade

Alpha.5 lets you limit each person or agent to selected workspaces and operations.
Access requires an enabled principal, workspace membership, credential scopes, and an unexpired credential that has not been revoked.
Reader, editor, and owner roles define eligible workspace operations. Store administration requires separate authority.
The configured owner token and personal stdio retain full bootstrap-owner access.
Documents remain private; this release provides no anonymous or public document access.

Agents can administer principals, grants, and credentials, and inspect the audit of successful mutations.
A restart preserves access state, including expiry and revocation. Content transfers exclude authority and audit.
Default remains protected from deletion. A non-empty workspace requires explicit cascade authorization.
See the [access reference](https://github.com/glidermcp/keep/blob/main/tools.md#access-administration) for setup, roles, and recovery.

Stop Keep before the first store access with 0.1.0-alpha.5.
Back up the complete store directory before you proceed, including before an offline export or import.
Keep atomically upgrades schema 5 or 6 to schema 7 and preserves content, IDs, history, and retry records.
A schema 5 upgrade creates Default with the previous space ID.
A schema 6 upgrade preserves workspace IDs and collection assignments. No manual collection move is required.

Alpha.4 and earlier cannot open schema 7.
To roll back, stop Keep and restore the complete backup from before the upgrade.
Then use the previous executable. The old executable alone cannot reverse the upgrade.
A restored backup loses later writes and restores its historical access state.

## Tested systems

| Condition | Linux x64 | Windows x64 | macOS arm64 |
| --- | --- | --- | --- |
| OS | Ubuntu 26.04.1 LTS; kernel 7.2.3-arch1-3 | Windows 11, build 10.0.26200 | macOS 26.5.1; Darwin 25.5.0 |
| Visible logical CPUs | 16 | 32 | 8 |
| Physical memory bytes | 66,751,107,072 | 66,217,689,088 | 17,179,869,184 |
| Model, cache recovery, and backup checks | Passed | Passed | Passed |

These are tested hosts, not minimum system requirements. No clean-machine installation result is claimed.
The Linux build host used Ubuntu 26.04.1. Its ELF version requirements contain a maximum required glibc version of 2.39.
This ABI requirement does not establish a tested minimum distribution or kernel version.

## Model and limits

Default search is lexical and needs no model. Add `--semantic` to enable hybrid search with a local model.
The archives contain no model weights; the first enabled start can download about 86 MiB.
The pinned model is [Snowflake/snowflake-arctic-embed-xs](https://huggingface.co/Snowflake/snowflake-arctic-embed-xs), revision `d8c86521100d3556476a063fc2342036d45c106f`.
All three platforms passed model checksum checks, corrupt-cache recovery, hybrid search, and lexical fallback after model failure.

Hybrid search permits at most 512 documents, 4,096 chunks, and 8,388,608 searchable text bytes per workspace.
Narrow filters do not bypass these limits. Use lexical search when a model is unavailable or a hybrid limit is exceeded.
The measured dataset contains 512 documents, 4,096 chunks, and 6,814,994 searchable text bytes.
It does not exercise the complete 8 MiB text limit. Lexical search remained available after a 513th document exceeded the document limit.

## Observed costs

| Measurement | Linux x64 | Windows x64 | macOS arm64 |
| --- | --- | --- | --- |
| Initial download, verification, and model load | 3.568993 s | 6.079000 s | 2.175795 s |
| Model load with verified cache in a fresh process | 72.723 ms | 47.000 ms | 64.915 ms |
| Index wall time | 952.955908 s | 607.594000 s | 474.429725 s |
| Index CPU time | 3,253.68000 s | 3,629.93750 s | 1,192.22000 s |
| Sampled peak resident memory | 215,359,488 bytes | 221,392,896 bytes | 270,598,144 bytes |
| One warm hybrid query | 335.990 ms | 266.000 ms | 222.527 ms |
| Maximum sample gap during initial download and load | 54.426 ms | 32.000 ms | 256.721 ms |
| Maximum sample gap during cached-process measurements | 58.045 ms | 47.000 ms | 177.694 ms |

The hosts are shared, with no exclusive CPU allocation.
Linux exposed 16 affinity CPUs, no quota in the visible CPU cgroup, and no limit in the visible memory cgroup.
Inherited Linux limits can be stricter. Windows job-object restrictions were not queried.

Cached measurements use a fresh process, verified model files, and the same dataset. The OS file cache stays warm.
Model and index times use observed phase transitions. Index CPU time includes protocol work and sums CPU time across threads.
Resident memory is a sampled peak. The warm query cost covers one request after readiness.
The verified-cache model-load interval excludes download and index work.

The requested sample interval is 10 ms. Actual gaps limit precision.
Treat model-load intervals shorter than their maximum sample gaps as coarse observations.
The observed index times range from about 7 minutes 54 seconds to 15 minutes 53 seconds on these shared hosts.
These results establish no general speed benefit, memory maximum, or comparison with another product.

## Fresh-agent tasks

Fresh agents completed all five tasks on each native archive.
Independent assessment checked the answers, final persisted state, and method evidence.
The tasks covered exact queries, conditional edits, history restoration, archive access, and deletion.

| Native archive | Evaluator MCP tool calls | Result |
| --- | --- | --- |
| Linux x64 | 24 | All five tasks passed |
| Windows x64 | 23 | All five tasks passed |
| macOS arm64 | 24 | All five tasks passed |

Each trial had four requested mutations and one expected `not_found` response after deletion. No unexpected MCP errors occurred.
Each evaluator was configured as GPT-6.1 Sol with medium reasoning. Independent client attestation of those settings is unavailable.
Call counts exclude protocol setup, seed operations, stop control, and the final export.

Each trial covers one synthetic store and one fresh evaluator. No matched comparison with another method ran.
These trials do not test semantic retrieval, HTTP, concurrency, access administration, expiry, conflicts, or lost-response recovery.
Exact wire bytes, token counts, comparable evaluator wall-clock duration, and client version are unavailable.
Operators provided transport assistance without task coaching.
Call counts establish no performance comparison.

## Integrity and recovery

This alpha uses checksums-only integrity. The archives are unsigned.
Download the archive and `SHA256SUMS` from the same prerelease. Compare the archive's SHA-256 before extraction.
Use the [public README](https://github.com/glidermcp/keep/blob/main/README.md) for installation and client setup.
Stop Keep before a backup or restore. Copy the complete store directory to preserve every workspace.
The native checks preserved and reopened stopped synthetic backups. They do not establish preservation of an existing deployment.
Uninstall removes only the executable; the personal store and backups remain on disk.
