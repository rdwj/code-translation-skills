# Exploration Chat: Python 2 to 3 Migration Skill Suite

This is the original brainstorming conversation that kicked off the code-translation-skills project. It covers the initial approach discussion, phased architecture design, and the decision to build a suite of targeted Claude Code skills rather than a single monolithic converter.

---

> **wjackson:** Let's use your skill builder skill to create a skill for converting python 2 to python 3, given a large legacy codebase. Some proposals are to use 2to3, or perhaps write tests for the old code, and then the same test for the new code, and then write the new code, etc. What are some good ways to think about going about this project? Let's discuss those best practices and then once we settle on an approach, let's create a skill for it.

**Thought process**

Great topic — Python 2 to 3 migration on a large codebase is one of those projects that sounds mechanical but has a lot of subtle pitfalls. Let me share some thinking on the major approaches, and then we can settle on what the skill should encode.

## Key Approaches

**1. Automated tooling (2to3, futurize, modernize)**

`2to3` is the classic tool, but it produces Python 3-only output. For a large codebase, `futurize` (from `python-future`) is often better because it can produce code that's compatible with *both* Python 2 and 3, letting you migrate incrementally. `modernize` is similar but uses `six` instead of `future`. The big caveat: these tools handle syntax changes well (print statements, dictionary methods, etc.) but struggle with semantic changes — especially around string/bytes handling, which is usually the hardest part of any migration.

**2. Test-driven migration (your proposal)**

This is the gold standard for correctness. The idea is: write characterization tests against the Python 2 code that capture its actual behavior, then convert the code, then verify the tests still pass under Python 3. The challenge is that for a *large* legacy codebase, test coverage is often low and writing comprehensive tests retroactively is expensive. But for critical modules, it's worth it.

**3. Incremental / strangler-fig approach**

Rather than converting everything at once, you make the codebase dual-compatible module by module. You add `from __future__` imports, fix syntax issues, handle the bytes/str divide, and gradually get modules passing under both interpreters. This is how most large organizations (Dropbox, Instagram, Facebook) actually did it.

**4. Big-bang conversion**

Run `2to3` or `futurize` across everything, fix what breaks, ship it. Works for smaller codebases but is risky at scale because you get a massive diff that's hard to review and debug.

## What I'd Recommend Encoding in the Skill

A phased, file-by-file approach that combines the best of these:

1. **Analysis phase** — scan the file for Python 2-isms, categorize by risk (syntax-only vs. semantic changes like str/bytes, `__unicode__`/`__str__`, integer division, etc.)
2. **Test generation** — write characterization tests for the existing behavior before touching anything
3. **Automated conversion** — apply `futurize` or equivalent transformations
4. **Manual semantic fixes** — handle the things automation can't (bytes/str boundaries, library replacements, encoding issues)
5. **Verification** — run both old and new tests, diff outputs, flag anything suspicious

The skill would take a Python 2 file (or module), walk through these phases, and produce the converted code plus tests.

What's your thinking — does that phased approach resonate, or would you weight it differently? For instance, are you more interested in the "make it dual-compatible" path (so you can run both interpreters during transition) vs. a clean "produce Python 3-only output" approach? And how much emphasis on test generation vs. trusting the automated tooling?

---

> **wjackson:** I like this approach. Would it be advantageous to create a graph database of the current codebase? What would that help us with? Are there other approaches that are better?

Great question. Let me think through the graph database idea and its alternatives.

## Graph Database of the Codebase

Building a dependency graph of the codebase would give you a few concrete advantages:

**What it helps with:**

* **Migration ordering** — you can topologically sort modules so you convert leaf dependencies first and work inward. This prevents the situation where you convert module A, but it imports module B which still uses Python 2 idioms that leak across the boundary (especially bytes/str contamination).
* **Impact analysis** — when you change a module, you can immediately see everything that depends on it and might break. This is especially valuable for shared utilities and internal libraries that dozens of modules import.
* **Identifying conversion clusters** — tightly coupled modules that import each other heavily should probably be converted together as a unit, not individually. A graph makes those clusters visible.
* **Progress tracking** — you can visualize what's been converted vs. what remains, and see if there are bottleneck modules blocking large subgraphs.

**The downsides:**

Building and maintaining a full graph database (Neo4j, etc.) adds infrastructure overhead that may not be justified. For most codebases, you don't need a *database* — you need a  *dependency analysis* .

## Lighter-Weight Alternatives That Get You 80% There

**AST-based import analysis** — Python's `ast` module can parse every file and extract imports in a few seconds. You get the full dependency graph as a dictionary without any database infrastructure. You can topologically sort it, find clusters, and determine migration order all in memory.

**Call graph analysis** — tools like `pyan`, `pycallgraph`, or even a simple `ast.NodeVisitor` that tracks function calls across modules. This goes deeper than imports — it tells you which *functions* in module B are actually used by module A, so you know which interfaces matter most.

**Type boundary analysis** — this is the one that's really Python-2-to-3-specific. The hardest bugs come from str/bytes confusion at module boundaries. Rather than a full graph database, what you actually want is to identify every point where data crosses a module boundary and flag whether that data could be `str` (which means different things in Py2 vs Py3). A targeted AST pass looking at function signatures, return values, and shared data structures gives you this.

## My Recommendation for the Skill

I'd skip a full graph database and instead build the dependency analysis directly into the skill as an  **analysis phase** :

1. **AST-based import graph** — lightweight, no infrastructure, gives you migration ordering
2. **Boundary type analysis** — identify str/bytes risks at module interfaces
3. **Cluster detection** — find tightly coupled module groups that should be converted together
4. **Migration plan generation** — produce an ordered list of conversion units based on the graph

This gives you all the benefits of the graph database approach without the overhead. The skill would use this analysis to determine *what order* to convert files in and *what to watch out for* at each step, then apply the phased conversion process we discussed earlier.

The full flow would be something like: analyze the codebase structure → generate a migration plan → for each conversion unit (in dependency order), run the test-generation → automated-conversion → manual-fix → verification cycle.

Does that feel right? Should we also think about how the skill handles things like Python 2-only third-party dependencies (libraries that were never ported), or do you want to scope it to just the user's own code? Once we nail down the scope, I think we're ready to build it.

---

> **wjackson:** This feels right. Let's talk about project phasing and phase-appropriate skills. It seems that rather than one big skill, we might need a lot of targeted skills, and a phased approach that potentially includes gates, rollback planning, etc.

**Thought process**

You're absolutely right, and this is where the thinking gets really interesting. A monolithic "convert this file" skill glosses over the fact that a real migration is a *project* with distinct phases, different concerns at each phase, and decision points where you need to stop and assess before moving forward.

Let me lay out how I'd think about the skill architecture.

## The Phase Model

**Phase 0 — Discovery & Assessment**

Before you touch a single line of code. What do we actually have? How bad is it? What's the risk profile?

Skills needed: a **Codebase Analyzer** that builds the dependency graph, categorizes every Python 2-ism it finds (syntax-only vs. semantic), measures existing test coverage, flags third-party libraries that may not have Py3 versions, and produces a migration readiness report. This is the skill that tells you "this project is 6 weeks" vs. "this project is 6 months."

Gate: Stakeholder review of the assessment. You don't proceed until someone signs off on the scope and timeline.

**Phase 1 — Foundation**

Make the codebase *migration-ready* without actually migrating anything. This is the phase most people skip, and it's why their migrations go sideways.

Skills needed: a **Future Imports Injector** that safely adds `from __future__ import print_function, division, unicode_literals, absolute_import` across the codebase — these are backward-compatible with Python 2 but start surfacing Py3 behavior. A **Test Scaffold Generator** that writes characterization tests for modules that lack coverage, especially at module boundaries. And a **CI Configuration Skill** that sets up dual-interpreter testing so you have a safety net going forward.

Gate: CI is green on Python 2 with all the `__future__` imports in place. Test coverage on critical-path modules meets a threshold you define. If adding `__future__` imports broke things, *that's information* — those are your highest-risk modules.

Rollback: trivial at this phase, you're just reverting additive changes.

**Phase 2 — Mechanical Conversion**

Now you start converting, in dependency order (leaf modules first), one conversion unit at a time.

Skills needed: a **Conversion Unit Planner** that takes the dependency graph from Phase 0 and determines the next safe unit to convert. An **Automated Converter** that applies futurize-style AST transformations — print statements, dictionary methods, `xrange`, `iteritems`, exception syntax, etc. This should be a separate skill from the semantic work because it's high-confidence, low-risk work that can move fast.

Gate: Each conversion unit passes its tests under Python 2 *and* Python 3 before you move to the next. If a unit fails, you stop and investigate — you don't pile up broken conversions.

Rollback: per-unit. Each conversion is its own branch/commit, so you can revert a single unit without unwinding everything.

**Phase 3 — Semantic Fixes**

This is where the hard work lives. The automated tools got you 70-80% of the way; now you handle the cases that require human judgment.

Skills needed: a **Bytes/String Boundary Analyzer** that identifies every point where data crosses a module boundary and could be affected by the str/bytes split — this is the single biggest source of Py3 migration bugs. A **Library Replacement Advisor** that maps Python 2-only libraries to their Py3 equivalents and generates the necessary changes. And a **Semantic Fix Applier** that handles integer division, `__unicode__` → `__str__`, iterator vs. list returns, comparison operator changes, etc.

Gate: Full test suite passes under Python 3. Integration tests pass. No encoding errors in logs during test runs.

Rollback: more complex here because semantic fixes can be interleaved. This is where you want each fix tagged and documented.

**Phase 4 — Verification & Hardening**

Skills needed: a **Behavioral Diff Generator** that runs the same inputs through both Py2 and Py3 code paths and flags any output differences. A **Performance Benchmarker** that catches regressions (Py3 can be faster or slower depending on the pattern). A **Migration Completeness Checker** that scans for any remaining Py2-isms, `six` usage that should be cleaned up, or `future` compatibility shims that are no longer needed.

Gate: Production-readiness signoff. No behavioral diffs, no performance regressions, no remaining Py2 artifacts.

**Phase 5 — Cutover & Cleanup**

Skills needed: a **Compatibility Shim Remover** that strips out `six`, `future`, `__future__` imports, and any dual-compatibility code. A **Dead Code Detector** that finds Py2-only code paths that are now unreachable.

Gate: CI switched to Python 3-only. Old interpreter removed from the pipeline.

## The Orchestration Layer

Beyond the phase-specific skills, you'd want two cross-cutting skills:

A **Migration State Tracker** that maintains a record of what's been converted, what phase each module is in, what gates have been passed, and what's blocking. Think of it as the project management layer.

A **Rollback Plan Generator** that, at each phase, can produce the exact steps to undo the current phase's changes. This is especially important in Phases 2 and 3 where you might need to revert a single module without affecting others.

## The Key Insight

The reason this decomposition matters is that different skills need different levels of autonomy. The Phase 2 mechanical conversion can be highly automated — the skill can just run. But Phase 3 semantic fixes need to surface decisions to the human ("this function returns bytes in Py2 and str in Py3 — which is correct for your use case?"). And the gate checks are explicitly about *stopping* and requiring human judgment before proceeding.

A monolithic skill would either be too autonomous (making semantic decisions it shouldn't) or too conservative (stopping to ask about things it could handle on its own).

---

So the question becomes: where do we start building? I'd suggest starting with the **Phase 0 Codebase Analyzer** since everything else depends on its output, and it's immediately useful even before you commit to the full migration. Want to start there, or do you want to refine the phase model further first?

---

> **wjackson:** What else am I not thinking of? Would employing some lint rules up-front help in a project like this? What other ideas should we be discussing before we begin building?

**Thought process**

Really good instinct on linting — and there are several other dimensions I think are worth surfacing before we build.

## Linting as a Migration Tool

This is underappreciated. Linting isn't just a quality gate — it can be an  *active migration driver* .

**`pylint --py3k`** is purpose-built for this. It flags Python 2 idioms that will break or behave differently under Python 3. Running it *before* you start converting gives you a machine-readable inventory of issues, categorized by type. You could wire this into the Phase 0 analyzer as a data source rather than writing all your own detection logic.

**`flake8-2020`** catches patterns that are forward-incompatible. **`pyupgrade`** is interesting because it's not just a linter — it *rewrites* code to use newer Python idioms, and you can target a specific minimum version.

The broader idea:  **custom lint rules as migration guardrails** . Once you've converted a module, you want a lint rule that *prevents regression* — no one should be introducing `dict.has_key()` into a converted module. You could have a Phase 1 skill that generates project-specific lint configurations that get stricter as modules progress through phases. The linter becomes your gate enforcer.

## Things I Think You're Not Thinking About Yet

**1. Serialized data and persistence**

This is a sneaky one. If your codebase pickles objects, writes bytes to databases, caches serialized data in Redis/Memcached, or stores data in any format that encodes Python type information — you have a migration problem that  *no code converter will catch* . A pickled Python 2 `str` object will deserialize differently under Python 3. If your application has long-lived persisted state, you need a **Data Migration Analyzer** skill that identifies all serialization boundaries and storage formats. This could be its own phase between Verification and Cutover.

**2. The encoding time bomb**

We've mentioned bytes/str, but I want to emphasize how deep this goes. In Python 2, you could write code that "works" only because all your test data is ASCII. The moment real-world UTF-8 data hits it under Python 3, it explodes. Your test generator skill needs to be *encoding-aware* — it should deliberately inject non-ASCII data (accented characters, emoji, CJK text) into test cases to flush out these latent bugs. This is probably the single highest-value thing the skill suite could do that teams typically miss.

**3. C extensions and native code**

If the codebase has any C extensions, Cython modules, or ctypes bindings, those are a completely different migration path. The Python C API changed significantly between Py2 and Py3. This needs flagging in Phase 0 and probably its own skill or at least a clear "this is out of scope, here's what you need to do manually."

**4. The type annotation opportunity**

If you're already touching every file in the codebase, this is a once-in-a-project opportunity to add type hints. Type hints are effectively Python 3-only (you can do comment-style hints in Py2, but nobody does). A skill that adds basic type annotations during conversion — even just function signatures inferred from usage patterns — would dramatically increase the codebase's maintainability going forward. `mypy` then becomes another gate checker.

**5. Build system and packaging**

`setup.py` with `python_requires`, classifiers, conditional dependencies — all need updating. Docker base images change. CI matrices change. Deployment scripts that reference `python` vs `python3`. This is infrastructure work that lives outside the source code but will absolutely block your cutover if you forget about it. Needs its own skill or at least a checklist generator.

**6. Feature flags and canary deployment**

For production services, you probably don't want a hard cutover. You want to run both interpreters simultaneously, route a percentage of traffic to Py3, compare outputs, and gradually increase. This isn't a code conversion skill — it's a **Deployment Strategy Skill** that generates the infrastructure configuration for running parallel interpreters and comparing behavior. Instagram famously did this with a custom request-level flag that routed individual requests to Py2 or Py3 backends.

**7. Dynamic language features**

Metaclasses changed syntax (`__metaclass__` attribute vs. `metaclass=` keyword argument). `exec` changed from statement to function. `__import__` behavior changed. Relative imports became explicit. These are the patterns that automated tools handle *inconsistently* because the correct fix depends on intent. A **Dynamic Pattern Analyzer** that flags these and presents them as decision points would be valuable.

**8. Dictionary ordering**

Dicts are insertion-ordered in Python 3.7+. Code that accidentally depended on dict ordering in CPython 2 (which was deterministic per-run but not guaranteed) might "work" in Py3 but for the wrong reasons. Conversely, code that explicitly worked around non-ordered dicts might now have redundant `OrderedDict` usage. Minor, but worth flagging in cleanup.

## Revised Skill Architecture

So the full suite might look like:

**Cross-cutting / Orchestration:** Migration State Tracker, Rollback Plan Generator, Gate Checker

**Phase 0 — Discovery:** Codebase Analyzer (dependency graph + Py2-ism inventory), Serialization Boundary Detector, C Extension Flagger, Lint Baseline Generator

**Phase 1 — Foundation:** Future Imports Injector, Test Scaffold Generator (encoding-aware), CI Dual-Interpreter Configurator, Custom Lint Rule Generator

**Phase 2 — Mechanical:** Conversion Unit Planner, Automated Converter, Build System Updater

**Phase 3 — Semantic:** Bytes/String Boundary Fixer, Library Replacement Advisor, Dynamic Pattern Resolver, Type Annotation Adder

**Phase 4 — Verification:** Behavioral Diff Generator, Performance Benchmarker, Encoding Stress Tester, Completeness Checker

**Phase 5 — Cutover:** Canary Deployment Planner, Compatibility Shim Remover, Dead Code Detector

That's roughly 20 skills. Some of these could be combined — the question is granularity vs. manageability.

---

Where do you want to draw the line? We could build a few high-impact foundational skills (the Codebase Analyzer, the encoding-aware Test Generator, the Automated Converter) and let the rest be follow-ons. Or we could start with the orchestration layer — the Migration State Tracker — since it defines the data model everything else plugs into. What feels most valuable to start with?

---

> **wjackson:** What about destination version? There were a lot of changes from Python 3.11 to 3.12 to 3.13 for instance. Do we need to bake in considerations for that?
>
> I appreciate your focus on the data layer. That is probably under-appreciated in most projects, and especially in this one. We don't exactly know what we're walking into, so we need to be prepared for data that would have been sourced from IoT/SCADA types of devices (think water monitors for datacenters all the way to machine shop automation/CNC types of tools), and also from a mix of structured, semi-structured and unstructured data. The codebase is very old and is one of those projects where the developers aren't around anymore so we have to do some archaeology here. I wouldn't be surprised if there were data sourced from mainframes.
>
> Write a complete plan for what skills we want. Go ahead and include all the skills we discussed. Put the files at /Users/wjackson/Developer/code-translation-skills

**Thought process**

Excellent point on target version — and that context about the data landscape changes everything. EBCDIC from mainframes, binary protocols from SCADA/IoT, packed data from CNC controllers — this isn't a typical web app migration. Let me read the skill-creator docs and then write out the full plan.

**Reviewed skill-creator documentation and verified target directory does not exist**

Good — now I have the skill-creator framework down. Let me check filesystem access and then build out the full plan.

**Created code-translation-skills project directory**

Now let me write the comprehensive plan. This is going to be substantial given the scope of what we discussed.

---

> **wjackson:** My Internet connection is intermittent and I think we got stuck. Please check progress and continue.

**Thought process**

Let me check what we have so far and pick up where we left off.

**Listed project directory, found empty contents**

Directory exists but is empty — we got cut off before writing anything. Let me pick up and write the full plan now.

**Updated todo list**

API Error: Unable to connect to API (ECONNRESET)

---

> **wjackson:** Our Internet connection is back up. Please continue

**Thought process**

Good — let me write the full plan now. This is a big document so I'll build it in sections.

**Created comprehensive migration plan document for Python 2 to 3 codebase**

Now let me create the directory scaffolding for all the skills:

**Created complete directory scaffolding for Python 2→3 migration skill suite**

Let me verify the directories were created in the right place:

**Explored project directory and reviewed planning document**

The Bash agent created them in the wrong location. Let me create them properly using the filesystem tool:

**Failed to create directory structure due to missing parent directories**

The filesystem tool needs directories created level by level. Let me build the structure step by step:

**Created project directory structure with shared, orchestration, and five phase folders**

Good. Now the second level — skill directories:

**Created 7 project directories for phase-4 verification and phase-5 cutover workflows**

Now the third level — scripts/, references/, assets/ subdirectories for each skill. Let me batch these efficiently:

**Created 78 subdirectories across 26 skill folders**

Now let me verify the structure and update the todo list:

**Explored project directory structure and contents**

---

> **wjackson:** please continue

Everything is in place. Let me update the todo list to reflect completion:

**Created directory structure and wrote migration plan**

Everything is done. Here's what's been created at `/Users/wjackson/Developer/code-translation-skills/`:

**PLAN.md** — a comprehensive plan (~750 lines) covering:

* **Target version strategy** with breaking changes for 3.9 through 3.13 (including the 3.12 `distutils` removal and stdlib module purge, and 3.13's free-threaded mode and continued removals). Every skill accepts a `target_version` parameter.
* **Data layer deep-dive** specific to your codebase — EBCDIC from mainframes, packed binary from SCADA/Modbus, CNC G-code parsing, mixed encodings, legacy serialization formats. The plan calls this out as the highest-risk area and dedicates two Phase 0 skills (Data Format Analyzer and Serialization Boundary Detector) to it.
* **Linting strategy** with three tiers: discovery linters (Phase 0, `pylint --py3k`, `pyupgrade`, `flake8-2020`), prevention linters (Phase 1+, custom rules blocking regression), and enforcement linters (Phase 3+, `mypy`, `bandit`, strict mode). Progressive lint configs that get stricter as each module advances through phases.
* **26 skills across 6 phases** plus 3 cross-cutting orchestration skills, each with defined inputs, outputs, capabilities, and gate criteria
* **Implementation priority** in 5 tiers, starting with the Migration State Tracker and Codebase Analyzer
* **12 shared reference documents** that multiple skills depend on

**Full directory scaffolding** — all 26 skill directories with `scripts/`, `references/`, `assets/` subdirectories, plus `shared/references/` for cross-skill reference docs.
