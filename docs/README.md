# Documentation

User-facing reference material for the [py2to3 Migration Skill Suite](../README.md). Everything in this directory describes current, shipped behavior. In-flight designs and investigation notes live in sibling directories, linked at the bottom.

## Start here

| Document | What it's for |
|----------|---------------|
| [MIGRATION-GUIDE.md](MIGRATION-GUIDE.md) | The practitioner's guide — why the suite is structured the way it is, how to think about a large-scale Py2→3 migration, and when to reach for each phase. Read this first if you're planning a migration. |
| [SCALE-PLAYBOOK.md](SCALE-PLAYBOOK.md) | How to adjust the six-phase workflow for small, medium, large, and very large codebases. Read this after the migration guide, when you know roughly what you're working with. |

## Reference material

Shared technical references consumed by the skills and available to human practitioners.

| Directory | Contents |
|-----------|----------|
| [references/python-migration/](references/python-migration/) | 11 reference files covering Py2/Py3 syntax and semantic changes, bytes/str patterns, industrial encodings, SCADA protocols, stdlib removals by version, serialization migration, hypothesis test strategies, encoding test vectors, and the sub-agent guide. These are the authoritative catalogs the skills consult during a migration. |

Every skill under [`../skills/`](../skills/) has a `references/INDEX.md` that points at the specific reference files it depends on.

## Related directories

Documentation for this project is split across four sibling top-level directories so visitors landing in `docs/` see only shipped, user-facing material:

- **`docs/`** (you are here) — shipped user-facing reference
- [`../planning/`](../planning/) — in-flight designs, the authoritative PLAN.md spec, the backlog, and the agent-kit generalization notes
- [`../research/`](../research/) — the original build history (review prompts, exploration chat log, build tracker) and research stubs like framing-and-bounding
- [`../retrospectives/`](../retrospectives/) — post-hoc session writeups

## Getting started with the suite

If you want to run a migration rather than read the docs, jump to [GETTING-STARTED.md](../GETTING-STARTED.md) at the repo root — it walks through installing the skills, generating a kickoff prompt, and handing off between sessions.
