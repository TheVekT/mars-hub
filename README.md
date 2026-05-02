# MARS Modules Marketplace

This repository is the public module marketplace for MARS, the desktop application hosted at [TheVekT/MARS](https://github.com/TheVekT/MARS).

It acts as a distribution and discovery layer for third-party modules that extend MARS with additional functionality. Contributors can publish modules by opening pull requests, and maintained packages are mirrored here for client-side consumption.

## Purpose

- Provide a single catalog of installable MARS modules.
- Keep module distribution separate from the main application repository.
- Allow the community to contribute modules through pull requests.
- Expose a machine-readable module index for the MARS client.

## Repository Layout

- `modules/` - module source code published by the marketplace.
- `index.json` - registry metadata used by the client to resolve available modules.
- `README.md` - marketplace overview, contribution policy, and publishing notes.

## Registry Structure

The `index.json` file contains metadata for all published modules. Each entry includes:

- `name` - human-readable module name shown in the marketplace.
- `version` - semantic version of the module package.
- `author` - module maintainer or organization.
- `description` - short technical summary of what the module provides.
- `compatibility` - supported target platforms or runtime environments.
- `required_tools` - optional list of tools or capabilities the module depends on.
- `package_name` - the directory name of the module under `modules/` for client-side discovery and loading.

## Module Distribution Model

Each module should ship with a manifest that describes how the marketplace and the MARS client should treat the module source. A minimal manifest can look like this:

```json
{
	"name": "Task Manager",
	"version": "1.0.0",
	"author": "TheVekT",
	"description": "Provides task management capabilities for the system.",
	"compatibility": ["windows", "linux"],
	"required_tools": []
}
```

Field expectations for `manifest.json`:

- `name` - human-readable module name shown in the marketplace.
- `version` - semantic version of the module package.
- `author` - module maintainer or organization.
- `description` - short technical summary of what the module provides.
- `compatibility` - supported target platforms or runtime environments.
- `required_tools` - optional list of tools or capabilities the module depends on.

Optional dependency installation notes can be provided in `INSTRUCTIONS.md`; the client can display that file automatically when it is present.

The module source should be laid out as a conventional Python package or module tree that MARS can import directly. For example, a package initializer may re-export the implementation:

```python
from . import task_manager
```

The manifest and source layout should stay aligned so the client can discover and load the module without ambiguity.

Modules in this repository are distributed as source code. Each module is intended to be self-contained and consumable by the MARS client without requiring the source tree of the main application.

## Publishing Workflow

1. Fork this repository.
2. Add or update the module source under `modules/`.
3. Update `index.json` with the corresponding metadata entry.
4. Open a pull request.
5. Maintainers review the package for compatibility, structure, and basic hygiene.

Pull requests are the preferred publication path for community modules. Direct pushes are reserved for maintainers.

## Contribution Guidelines

- Submit only modules that you own or have permission to redistribute.
- Keep module packages small, deterministic, and free of unnecessary binaries.
- Do not include secrets, credentials, or environment-specific configuration.
- Document any special installation or runtime requirements in the pull request.
- Make sure the package name and metadata match the archive contents.
- If the module needs setup steps for dependencies, place them in `INSTRUCTIONS.md` so the client can display them automatically.

## License

If a module is distributed under the MIT License, state that clearly in the manifest, add the license text to the package if applicable, and mention it in the pull request description. If a different license is used, make that explicit as well.

## Compatibility Notes

This marketplace is designed to remain version-aware. Module authors should expect the MARS client to validate module metadata and reject incompatible packages when necessary.

If a module targets a specific MARS release, document that requirement explicitly in the metadata and in the pull request description.

## Recommended PR Template

Use the following checklist when submitting a module:

- Module name
- Author or maintainer
- Version
- What changed in this release
- Platforms or runtime targets validated by the author
- Any required external tools, permissions, or caveats
- License clarification, if the module is not meant to follow the repository default

If the PR introduces a new manifest shape or a new import/load behavior, include a short example and call out the change explicitly.

## Status

This repository is the canonical marketplace source for MARS modules and is intended to grow through community contributions.
