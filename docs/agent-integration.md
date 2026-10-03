# CLI and MCP agent integration

ProjectMapper provides two local adapters over its public action layer:

- `projectmapper-cli` for one-shot scans, snapshots, exports, patch validation and
  approved patch application.
- `projectmapper-mcp` for a local MCP server over stdio, with tools and read-only
  resources for one project root.

Both adapters confine paths to the selected root, force backups for writes that support
them, and record the `cli` or `mcp` origin in the current session's history. Each process
has its own session; it does not attach to a running desktop window. History and adapter
state are in memory and end with the process.

## Install

The CLI is included in the normal install:

```console
pip install .
projectmapper-cli --root C:\work\my-project scan
```

The MCP server uses the official SDK as an optional extra. Install it only when using
MCP:

```console
pip install ".[mcp]"
projectmapper-mcp --root C:\work\my-project
```

Equivalent module entry points are `python -m projectmapper.cli` and
`python -m projectmapper.mcp --root PATH`. The MCP server uses stdio only and does not
open a network listener.

## Configure an MCP client

Add the server to the client's MCP server configuration. For clients using the common
`mcpServers` layout, a Windows example is:

```json
{
  "mcpServers": {
    "projectmapper": {
      "command": "projectmapper-mcp",
      "args": ["--root", "C:\\work\\my-project"]
    }
  }
}
```

If the executable is not on the client's `PATH`, set `command` to the full path to the
installed `projectmapper-mcp.exe`. Keep the project root fixed in this configuration;
the server does not expose a root-switching tool. The server supports MCP's current
discovery protocol and the legacy initialize handshake through the Python SDK.

The server exposes these 27 sorted, allow-listed tools:

`application.diagnostics`, `backup.list`, `capture.configure`, `exclusions.inspect`,
`exclusions.update`, `file.create`, `file.name`, `history.query`, `output.location`,
`patch.load`, `patch.result`, `patch.save`, `patch.schema`, `patch.validate`,
`project.scan`, `project_patch.add_entry`, `project_patch.apply`,
`project_patch.validate`, `selection.set`, `snapshot.compile`, `snapshot.export`,
`snapshot.require`, `state.get`, `text.find`, `text.open`, `text.replace`, and
`text.save`. They cover project state, selection and exclusions, snapshots, file and
patch operations, project-patch operations and content-free history. The server also
exposes:

- `projectmapper://tree` for the current tree scan.
- `projectmapper://snapshot/{projection}` for a compiled `tree`, `filedump`, `combined`
  or `manifest` projection.

Validate a proposal before applying it. `project_patch.validate` returns a review and a
single-use `plan_id` when every file is valid; `project_patch.apply` applies that exact
plan. For one file, use `text.open`, then `patch.validate`, then `patch.save`, or use
`text.save` with the SHA-256 returned by `text.open`. `file.create` never overwrites.

## CLI examples

```console
projectmapper-cli --root C:\work\my-project --exclude "*.log" scan
projectmapper-cli compile --root C:\work\my-project --include-binary
projectmapper-cli export tree --root C:\work\my-project --text
projectmapper-cli validate-patch src\app.py patch.json --root C:\work\my-project
projectmapper-cli validate-project project-patch.json --root C:\work\my-project
projectmapper-cli apply-project project-patch.json --root C:\work\my-project
projectmapper-cli history --root C:\work\my-project
```

JSON is the default output; use `--text` for a concise human-readable result. Shared
options may appear before or after a command. `--exclude PATTERN` can be repeated.
`validate-patch` and `validate-project` only prepare proposals. The `apply-patch` and
`apply-project` commands ask the local user through the trusted approval window; they do
not use terminal input or command-line approval flags.

Exit codes are stable: `0` succeeded, `1` action or I/O failure, `2` usage or invalid
input, `3` stale snapshot/plan/source, `4` approval is required but no local approval
window is available, `5` unsafe path, and `130` denied or cancelled.

## Approval and safety

The approval window is owned by the local adapter process. It shows the action, affected
paths and exact proposed diff. Deny is focused by default; closing the window, pressing
Escape, or reaching the configured timeout denies the request. Project-wide changes
always ask once for the validated plan. Single-file writes ask by default; the desktop
Settings window can waive prompts for fingerprint-guarded single-file writes.

An MCP tool argument, JSON field, CLI flag, stdin value, or MCP elicitation answer cannot
approve a write. Agent input schemas contain no approval field. The popup is the only
approval channel. A process with access to the user's desktop could click the popup;
the approval boundary does not protect against desktop-control software.

All agent paths are confined to the configured project root. Linked targets, `.parts/`
and ProjectMapper's `_projectmapper/` output folder are refused for agent writes. The
adapter forces backups for `text.save`, `patch.save` and `project_patch.apply`; agents
cannot disable those backups. File creation is exclusive and cannot overwrite. Delete,
overwrite-via-Save-As, backup restore/prune, vendor export and root switching are not
exposed.

## User settings

Use the desktop **Settings…** button to configure values before starting adapter
processes. Settings are stored outside project roots so an agent cannot change them.
On Windows the file is `%LOCALAPPDATA%\ProjectMapper\settings.json`; set
`PROJECTMAPPER_SETTINGS` to override the path. Other platforms use their standard user
configuration directory.

Defaults and allowed ranges:

| Setting | Default | Range |
| --- | ---: | ---: |
| Maximum tool result | 256 KiB | 4 KiB–16 MiB |
| Maximum resource read | 1 MiB | 4 KiB–64 MiB |
| Approval timeout | 120 seconds | 10–3,600 seconds |
| Ask before single-file writes | Yes | On/off |

An agent may request a lower tool-result limit for an individual call, never a higher
one. Results that are cut include truncation metadata. Text previously served truncated
cannot be written back as a whole-file save; use a validated patch instead. Resources
are capped by the user's resource limit. Settings changes apply to newly started adapter
processes.

## Limits

The adapters are local process interfaces, not operating-system sandboxes. Root
confinement, the action allow-list, forced backups and the approval window enforce the
ProjectMapper action policy. They do not constrain other tools or programs available to
the agent. MCP is stdio-only, and each process keeps its own in-memory session.
