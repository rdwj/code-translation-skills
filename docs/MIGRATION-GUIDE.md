# A Practitioner's Guide to Large-Scale Python 2 to 3 Migration

## 1. Introduction

This document is a technical design guide for practitioners undertaking a large-scale Python 2 to Python 3 migration. It covers the problem space, the strategic approach, and the reasoning behind the decisions that shape a successful migration project. It is not a tutorial or a step-by-step walkthrough. It assumes you understand Python and are familiar with the general contours of the Py2/Py3 divide.

The companion document, [PLAN.md](../PLAN.md), contains the detailed specifications for the migration skills organized across six phases, including inputs, outputs, gate criteria, and rollback procedures for each. This guide is the "why" -- PLAN.md is the "what." Read this document first to understand the problem space and strategic thinking, then use PLAN.md as the operational reference.

The guide is written to be generic. While examples draw from industrial contexts (SCADA systems, mainframe data, CNC automation) to illustrate the kinds of complexity that arise in long-lived codebases, the principles and approach apply to any large-scale Py2-to-Py3 migration. A web application migration will encounter fewer encoding exotics but the same structural challenges: dependency ordering, bytes/string boundaries, serialization compatibility, and the need for phased rollback.

### Why This Document Exists

The Python 2 end-of-life date was January 1, 2020. Yet significant Python 2 codebases remain in production, particularly in industries where software life cycles are measured in decades rather than years. Industrial control systems, financial processing platforms, scientific computing infrastructure, and government systems all contain Python 2 code that was written when Python 2 was the only production-quality option and that has continued to function reliably enough that rewriting it was never prioritized.

These migrations present challenges that differ materially from the typical web application migration that dominates the available documentation. The codebases are larger, older, and less well-tested. The original developers may be unavailable. The data flows are more diverse, spanning binary protocols, legacy encodings, and serialization formats that were never designed for cross-version compatibility. The risk tolerance is lower, because failures in industrial and financial systems have consequences beyond user inconvenience.

This guide addresses those challenges directly. It is the product of analyzing how large-scale migrations actually succeed and fail, and distilling those patterns into a structured approach.

### Conventions Used in This Document

Throughout this document, "Py2" and "Py3" are used as shorthand for Python 2 (specifically 2.7, the last release) and Python 3 (the target version, which varies by project). Code examples are annotated with comments indicating which interpreter they target. When discussing the `str` type, the context is always specified because `str` means different things in Py2 (bytes) and Py3 (text) -- this ambiguity is, of course, the central challenge of the entire migration.

The term "module" refers to a single `.py` file. "Package" refers to a directory with an `__init__.py` file. "Conversion unit" refers to a module or a cluster of tightly-coupled modules that are converted together as a single atomic operation.

Phase numbers (0-5) and skill numbers (e.g., Skill 3.1) reference the specifications in PLAN.md. Gate criteria and rollback procedures are defined in detail in PLAN.md for each phase; this document discusses the reasoning behind them at the strategic level rather than repeating the operational detail.


## 2. Migration Approaches

There are four established approaches to migrating a Python 2 codebase to Python 3, each with distinct tradeoffs. Understanding them is necessary background for the phased hybrid approach recommended here.

### 2.1 Automated Tooling

Three tools dominate the automated conversion landscape. They share a common architecture -- parse Python 2 source into an AST, apply a set of "fixers" that rewrite specific patterns, and emit Python 3-compatible source -- but they differ in what they produce and how they handle the transition period.

**`2to3`** ships with Python and is the oldest of the three. It applies a set of fixers that rewrite Python 2 syntax to Python 3. It produces Python-3-only output, which means the moment you run it, your code no longer works on Python 2. For a small codebase where you can afford a clean break, this is the simplest path. For anything larger, losing the ability to run on Python 2 during the transition period is a significant risk, because it forces a big-bang cutover: either all the code works on Python 3 or you revert everything.

`2to3` handles most syntax changes correctly -- `print` statements, `except` syntax, dictionary iteration methods, `xrange`, `raw_input`, `has_key`, octal literals, and relative imports. It also handles some library renames (`ConfigParser` to `configparser`, `Queue` to `queue`, etc.). Where it struggles is with anything that requires semantic understanding of the code, particularly the bytes/string divide. When `2to3` encounters a Python 2 `str`, it cannot determine whether it represents bytes or text, because that distinction does not exist in the Python 2 type system. It makes a best guess, and the guess is often wrong in codebases that handle binary data.

**`futurize`** (from the `python-future` library) takes a different approach. Instead of producing Python-3-only output, it produces code that is compatible with both Python 2 and Python 3 by inserting compatibility imports from the `future` package. A `futurize`-converted file can be run on either interpreter, enabling incremental migration: you can convert one module at a time and the rest of the codebase continues to run on Python 2.

`futurize` operates in two stages. Stage 1 applies safe, minimal transformations that are unlikely to break anything: adding `from __future__ import` statements, fixing `print` and `except` syntax, and similar. Stage 2 applies more aggressive transformations that bring the code closer to Python 3 idioms but may require the `future` package at runtime. The staged approach lets you apply Stage 1 broadly as a preparatory step and Stage 2 selectively to modules that are ready for it.

The tradeoff is that the intermediate state -- code littered with `from builtins import ...` and `from future import ...` -- is harder to read and introduces a runtime dependency on the `future` package. The compatibility shims also have a small performance cost, and they obscure the "real" Python 3 idioms behind a compatibility layer.

**`modernize`** is similar to `futurize` but uses the `six` library instead of `future` for compatibility. `six` is lighter-weight (a single file, no subpackages) and more widely used in the Python ecosystem, but it provides less future-proofing -- it is a compatibility bridge that papers over differences rather than a forward-looking shim that makes Python 2 code look like Python 3 code. In practice, the choice between `futurize` and `modernize` is often a matter of team preference and existing dependencies; if the codebase already uses `six`, `modernize` is the natural fit.

All three tools share a fundamental limitation: they handle syntax changes competently but struggle with semantic changes. When Python 2 code uses `str` -- which could mean either bytes or text depending on context -- no automated tool can determine the developer's intent. That determination requires understanding the data flowing through the code, which requires human judgment or at minimum a deep analysis of data flows. The tools can flag these locations, but they cannot fix them reliably.

### 2.2 Test-Driven Migration

The test-driven approach treats the migration as a behavioral preservation problem. You write characterization tests against the Python 2 code that capture its actual behavior -- not what it *should* do, but what it *does* do right now. Then you convert the code. Then you verify the tests pass on Python 3. Any test failure is a potential migration bug.

This is the gold standard for correctness. The reasoning is straightforward: if the code produced output X under Python 2, and it produces output X under Python 3, the migration has not changed the code's observable behavior. If it produces output Y, something has changed, and you need to determine whether that change is acceptable (e.g., dictionary repr format changed, which is cosmetic) or a bug (e.g., a bytes/string confusion changed the data content).

The problem is cost. Large legacy codebases typically have low test coverage, and writing comprehensive characterization tests retroactively is expensive. For a codebase with hundreds of modules, writing exhaustive tests for everything before you start converting is impractical -- the test-writing effort alone could exceed the conversion effort. The practical approach is to focus test generation on the highest-risk areas: module boundaries where data types could change, data ingestion paths where encoding matters, serialization points where type information is persisted, and any code that mixes bytes and text operations.

There is also a subtlety around what "characterization" means. A characterization test captures behavior, but some behavior is accidental. Python 2 code that silently converts between bytes and unicode via implicit ASCII encoding is "working" only in the narrow sense that it does not raise an exception with the current test data. That behavior will (correctly) change under Python 3. Characterization tests need to be tagged so that the team knows which tests document intentional behavior (should be preserved) and which document accidental behavior (may need updating after conversion).

### 2.3 Incremental / Strangler-Fig

Rather than converting everything at once, the incremental approach makes the codebase dual-compatible module by module. You add `from __future__` imports to surface Python 3 behavior under Python 2, fix the issues that arise, then gradually bring each module to full Python 3 compatibility. At any point during the migration, the codebase runs on Python 2, and an increasing fraction of it also runs on Python 3.

This is how Dropbox, Instagram, and Facebook actually executed their migrations. Dropbox's migration of over a million lines of Python 2 code took approximately three years and was done incrementally, with modules being converted and tested individually against the existing Python 2 codebase. Instagram ran both Python 2 and Python 3 interpreters in production simultaneously, routing individual requests to one or the other, so they could compare behavior at the request level before committing to the switch.

The advantage of the incremental approach is that it limits blast radius. A bad conversion in one module does not break the entire codebase. You can ship incremental progress, and if a conversion introduces a bug, you can revert that specific module without unwinding everything else.

The disadvantages are meaningful. First, it is slow -- the overhead of maintaining dual compatibility, running tests on both interpreters, and managing the intermediate state is substantial. Second, the intermediate state (some modules converted, some not, compatibility shims everywhere) is messy to maintain. Third, cross-module data contracts become fragile during the transition period, especially around bytes/string semantics. A converted module might return `str` (text) from a function that previously returned `str` (bytes), and the unconverted caller might pass that text to a function expecting bytes. These cross-boundary issues are the hardest to detect because neither module is individually wrong -- the bug exists only at the interface between them.

### 2.4 Big-Bang Conversion

Run `futurize` across everything, fix what breaks, ship it. This works for small codebases (a few thousand lines) where one person can hold the entire system in their head and the test suite covers all critical paths. At scale, it produces a massive diff that is difficult to review, difficult to debug, and impossible to roll back partially. If something goes wrong in production, your only option is to revert everything.

The big-bang approach also concentrates all the risk into a single event. If the conversion surfaces 500 issues, you need to fix all 500 before you can ship. If you fix 499 and the last one takes three weeks to resolve, those 499 fixes are blocked from reaching production. The incremental approach, by contrast, lets you ship fixes as they are ready.

### 2.5 The Recommended Approach

For a large codebase, the most effective strategy is a phased, file-by-file approach that combines the strengths of the methods above:

1. **Analyze** the codebase to understand its structure, risk profile, and data layer before changing anything.
2. **Prepare** by generating targeted characterization tests for high-risk areas and establishing dual-interpreter CI.
3. **Convert mechanically** in dependency order, applying automated syntax transformations and validating each unit before proceeding.
4. **Resolve semantics** that automation cannot handle, surfacing decisions to humans where judgment is required.
5. **Verify** behavioral equivalence between the Python 2 and Python 3 code paths.
6. **Cut over** to Python 3 with canary deployment and a defined rollback window.

This approach gives you the speed of automated tooling where it is safe (syntax changes), the correctness guarantees of test-driven migration where it matters (semantic changes), and the risk management of incremental migration throughout (per-module rollback, gates between phases).

### 2.6 Why the Hybrid Approach Works at Scale

The hybrid approach's advantage becomes clearer when you consider the failure modes of each pure approach and how the hybrid addresses each one.

Pure automated conversion fails when the tools make incorrect semantic decisions. In a codebase with binary protocol handling, the tool might convert `str` (bytes) to `str` (text) in a function that parses Modbus frames, silently corrupting the data. The error may not surface until the corrupted data reaches a physical actuator. The hybrid approach limits automated conversion to the mechanical syntax changes where the tools are reliable, and defers semantic changes to human-supervised Phase 3.

Pure test-driven migration fails on cost. A million-line codebase with 15% test coverage needs approximately 200,000 lines of new tests to reach 80% coverage, and those tests need to be written *before* conversion begins. At a rate of 50 meaningful test lines per developer-day, that is 4,000 developer-days of test writing before a single line of production code is converted. The hybrid approach focuses test generation on the highest-risk areas (data layer, module boundaries) and uses automated conversion plus gate checks to verify the lower-risk areas.

Pure incremental migration fails on duration. Making every module individually dual-compatible, with full `six` or `future` scaffolding, is methodical but slow. Each module requires multiple rounds of changes: add compatibility imports, fix the breakage they surface, add more imports, fix more breakage. The intermediate state is fragile and the compatibility scaffolding obscures the code's intent. The hybrid approach uses future imports as a diagnostic tool (Phase 1) and then converts whole modules in one pass (Phase 2), producing cleaner intermediate states.

The key insight is that different parts of the migration have different risk profiles, and each approach is best suited to a specific risk band:

- Automated tooling is optimized for low-risk, high-volume syntax changes (Phase 2).
- Test-driven migration is appropriate for high-risk semantic changes where behavioral correctness must be verified (Phase 3 and Phase 4).
- Incremental deployment with canary routing is the right strategy for the production cutover, where the risk is operational rather than code-level (Phase 5).

The hybrid approach matches the technique to the risk, using each approach where it is strongest and avoiding it where it is weakest.

The remainder of this document elaborates on the reasoning behind each element.


## 3. Dependency Analysis

Before converting any code, you need to understand the structure of the codebase. Which modules depend on which? Which clusters of modules are tightly coupled and need to be converted together? What is the safe ordering for conversion? Without this analysis, you are converting modules in an arbitrary order and hoping that cross-module interactions do not create subtle bugs.

### 3.1 Why Dependency Analysis Matters

Converting modules in the wrong order creates cross-boundary type confusion. Consider two modules, A and B, where A imports and calls functions from B. If you convert A to Python 3 semantics while B is still Python 2, data flowing across the A-B boundary may silently change type. A `str` in Python 2's B is bytes; a `str` in Python 3's A is text. If A passes its `str` to B, or B passes its `str` to A, neither side gets what it expects. The bug manifests not as an exception but as corrupted data -- a UnicodeDecodeError if you are lucky, silently mangled content if you are not.

Converting leaf dependencies first -- modules that nothing else depends on -- and working inward toward the core avoids this problem. When you convert a leaf module, no other module's behavior changes because no other module calls the leaf with data that could be type-confused. The leaf's own tests verify that it works correctly under Python 3. Then, when you convert the next module inward, its dependencies are already on Python 3 and the boundaries are stable.

Dependency analysis also reveals conversion clusters: groups of modules with mutual imports or heavy bidirectional coupling that must be converted as a unit. Any cycle in the import graph creates such a cluster. You cannot topologically sort a cycle, so all modules in the cycle must be converted simultaneously. Attempting to convert half of a tightly coupled cluster creates an unstable intermediate state where type semantics differ within what is effectively a single logical component.

Finally, the dependency graph gives you a critical-path analysis. The longest chain of dependent modules determines the minimum calendar time for the migration. If module Z depends on Y depends on X depends on ... depends on A, and each conversion takes a week, the chain determines the minimum duration regardless of how many people work in parallel. Identifying "gateway" modules -- modules that block large subgraphs from proceeding -- lets you prioritize them for early conversion to maximize parallelism.

### 3.2 Lightweight Approaches Over Graph Databases

A question that frequently arises in migration planning is whether to build a graph database of the codebase using a tool like Neo4j or JanusGraph. The appeal is understandable: the dependency graph is, literally, a graph, and graph databases are purpose-built for graph queries.

In practice, a full graph database is overkill for this problem. It introduces infrastructure overhead -- a server to run, a query language to learn (Cypher or Gremlin), data to load and keep synchronized as the codebase changes -- without providing capabilities that simpler approaches cannot. The queries you need to run (topological sort, cycle detection, cluster identification, shortest path) are standard graph algorithms that run efficiently on an in-memory adjacency list. The codebase is not going to have millions of modules; even a very large codebase has at most a few thousand Python files, which is trivial for in-memory processing.

**AST-based import analysis** is the simplest and most effective approach. Python's `ast` module parses every `.py` file and extracts `import` and `from ... import` statements. The result is a complete dependency graph represented as a dictionary, computed in seconds even for large codebases. No infrastructure required. You can topologically sort it, detect cycles, find clusters, and determine migration order entirely in memory.

```python
import ast
from pathlib import Path
from collections import defaultdict

def build_dependency_graph(root: Path) -> dict[str, set[str]]:
    """Build a module dependency graph from a codebase root."""
    graph = defaultdict(set)
    for filepath in root.rglob("*.py"):
        module = str(filepath.relative_to(root)).replace("/", ".").removesuffix(".py")
        try:
            tree = ast.parse(filepath.read_bytes())
        except SyntaxError:
            continue  # Log and skip unparseable files
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    graph[module].add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    graph[module].add(node.module)
    return dict(graph)
```

This is not production code -- it does not handle relative imports, package `__init__.py` files, or conditional imports inside functions. But it illustrates the principle: the dependency graph is a few dozen lines of standard-library Python, not a database deployment.

**Call graph analysis** goes deeper than imports. Tools like `pyan` or a custom `ast.NodeVisitor` that tracks function calls across module boundaries tell you which functions in module B are actually used by module A. This matters because a module might import a large library but only use one function -- the risk profile of that dependency is very different from a module that uses dozens of functions from the imported library. Call graph analysis also identifies the specific interfaces that need to be stable during conversion: if module A only calls `B.parse_record()`, then you know exactly which function's bytes/string behavior you need to verify.

A practical middle ground is to build the import graph first (cheap, fast, gives you the conversion ordering) and then selectively run call graph analysis on high-risk module pairs identified by the import graph. You do not need call-level granularity for the entire codebase; you need it for the boundaries where conversion risk is highest.

**Type boundary analysis** is the dependency analysis that is specific to Python 2-to-3 migration. At every point where data crosses a module boundary -- function arguments, return values, shared data structures, global state -- you need to determine whether that data could be a Python 2 `str` (and therefore ambiguously bytes-or-text). This is not a generic dependency problem; it requires understanding the semantic types flowing through the code.

A targeted AST pass that examines function signatures (looking for parameters used in string operations vs. byte operations), return statements (looking for encode/decode calls or string formatting), and assignments to shared data structures (looking for module-level variables accessed from other modules) provides this information without the overhead of a full type inference engine. The goal is not to infer all types -- that is a research problem -- but to flag the boundaries where type confusion is most likely.

**Cluster detection** identifies groups of modules that should be converted together. Beyond import cycles (which are mandatory clusters), you can identify clusters by computing the "coupling coefficient" between module pairs: the number of cross-boundary function calls, shared data structures, and common imports. Modules with high coupling are candidates for joint conversion, because converting them separately creates too many intermediate boundary issues. The clustering does not need to be perfect; it needs to group the obvious cases (mutual imports, shared state machines, protocol handler + protocol parser pairs) and flag the ambiguous cases for human review.

### 3.3 Practical Dependency Analysis Workflow

The dependency analysis workflow should produce four concrete artifacts:

**The import graph** as a JSON adjacency list. Each module maps to the list of modules it imports. Internal imports (within the codebase) are distinguished from external imports (third-party packages and standard library). Only internal imports matter for conversion ordering; external imports matter for library compatibility analysis (Phase 0) and library replacement (Phase 3).

```json
{
    "src.scada.modbus_reader": {
        "internal": ["src.scada.protocol_base", "src.data.encoding_utils"],
        "external": ["struct", "serial", "logging"]
    },
    "src.scada.protocol_base": {
        "internal": ["src.data.encoding_utils"],
        "external": ["abc", "struct"]
    }
}
```

**The topological order** as an ordered list of conversion units. Leaf modules (modules that import nothing internal, or only import modules that are already listed) come first. Clusters are represented as a single entry containing multiple modules. The order is not unique -- there may be multiple valid orderings -- but any valid topological order guarantees that when you convert a module, all its internal dependencies have already been converted.

**The cluster map** showing which modules are grouped into conversion units and why. Mandatory clusters (import cycles) are distinguished from recommended clusters (high coupling but no cycle). Each cluster has a risk assessment based on the number of bytes/string boundaries between the clustered modules and the complexity of the shared interfaces.

**The critical path** identifying the longest dependency chain. This is the minimum number of serial conversion steps, regardless of parallelism. If the critical path has 50 modules and each takes an average of 2 days to convert through Phase 2, the critical-path calendar time for Phase 2 is approximately 100 days. This number is essential for project planning and should be presented to stakeholders as a constraint, not an estimate that can be compressed by adding people.

### 3.4 Third-Party Library Compatibility

Dependency analysis extends to third-party libraries, though the analysis is different. For internal modules, you control the conversion; for third-party libraries, you need to determine whether a Python-3-compatible version exists.

The Phase 0 analysis should produce a library compatibility inventory:

- **Already compatible**: Libraries that support both Py2 and Py3 (or Py3-only) in their current or latest version. These require only a version bump.
- **Compatible with newer version**: Libraries where the Py2-compatible version does not support Py3, but a newer version does. These require a version bump and potentially API changes.
- **No Py3 support**: Libraries that were never ported to Py3. These are migration blockers that require finding an alternative library, forking and porting, or reimplementing the functionality.
- **Abandoned**: Libraries that are no longer maintained. Even if they technically work on Py3, depending on unmaintained code is a risk.

For each library in the "no Py3 support" or "abandoned" category, the analysis should identify which modules in the codebase use it, what functionality they use, and what the alternatives are. This information feeds directly into the Phase 3 Library Replacement Advisor.

The library compatibility analysis is time-sensitive: the Python packaging ecosystem evolves. A library that had no Py3 support six months ago may have gained it since. The analysis should check the current state of each library on PyPI, not rely on cached or assumed information. For each library, check the latest version on PyPI, its declared Python version support (the `python_requires` metadata), and the latest activity date (to assess abandonment risk).

In legacy codebases, it is common to find vendored (copied into the codebase) versions of third-party libraries. These appear as internal code in the import graph but are actually external dependencies pinned to a specific (often very old) version. The Phase 0 analysis should detect vendored code (by comparing against known library source code or by looking for third-party license files) and treat it as an external dependency that needs a version bump or replacement.


## 4. The Data Layer

The data layer is typically the highest-risk area in a Python 2 to 3 migration, and the one where automated tooling provides the least help. The fundamental issue is that Python 2's `str` type is semantically ambiguous: it represents both binary data and text, with implicit encoding conversions happening silently at runtime. Python 3 enforces a strict separation between `bytes` (binary data) and `str` (text). Code that relied on the ambiguity -- which is to say, most Python 2 code that handles non-trivial data -- must be explicitly resolved.

This section covers the specific data-layer concerns in detail because they are both the most technically complex and the most commonly underestimated aspect of the migration.

### 4.1 The Encoding Landscape

A common misconception is that the bytes/string divide only matters for "internationalized" applications. In reality, it affects any code that reads data from external sources, because the interpretation of that data as bytes or text must be made explicit in Python 3.

Python 2 code that "works" often does so only because all test data happens to be ASCII, where bytes and text have identical byte-level representations. The ASCII range (0x00-0x7F) is a shared subset of virtually every encoding in use: UTF-8, Latin-1, Windows-1252, even EBCDIC (for letters and digits, though not punctuation). When all your data is ASCII, you never hit the encoding boundaries, and you never discover that your code has implicit assumptions about encoding that will fail under Python 3.

The moment non-ASCII data arrives -- a UTF-8 encoded string with accented characters, a sensor reading with high-byte values, an EBCDIC record from a mainframe, a filename with CJK characters -- the implicit conversions that Python 2 performed silently become explicit errors in Python 3. The errors take one of two forms:

1. `UnicodeDecodeError`: code tried to decode bytes as text using an incorrect codec (or no codec, defaulting to ASCII). For example, `b'\xc3\xa9'.decode('ascii')` raises this error because `0xC3` is not a valid ASCII byte.
2. `TypeError`: code passed `bytes` where `str` was expected or vice versa. For example, `'hello' + b'world'` raises this error in Python 3 because you cannot concatenate text and bytes.

These errors are the migration's primary symptom, and they surface the underlying problem: the code never specified what encoding it was using, because Python 2 did not require it to.

This has a direct implication for test strategy. Characterization tests generated during the migration must be encoding-aware. A test suite that only uses ASCII data will not catch the encoding bugs that Python 3 will surface in production. Test generation should deliberately inject:

- Non-ASCII UTF-8 text: accented characters (e, u, n), CJK text, emoji, mathematical symbols.
- Data that is valid in one encoding but invalid or different in another. The byte `0xE9` is the character "e with acute accent" in Latin-1, but it is an incomplete UTF-8 sequence (UTF-8 requires two bytes starting with `0xC3 0xA9` for the same character). Injecting `0xE9` into a path that assumes UTF-8 will trigger a `UnicodeDecodeError` that ASCII test data would never hit.
- Binary data that contains byte sequences resembling valid text. Sensor readings, protocol headers, and random binary data may coincidentally contain valid UTF-8 sequences, leading to code that "works" on some data and fails on other data non-deterministically.
- EBCDIC-encoded data for codebases that process mainframe data. EBCDIC's byte values differ completely from ASCII; a test that verifies EBCDIC handling with ASCII test data is testing nothing.

### 4.2 Serialized Data and Persistence

Serialization is a particularly insidious migration problem because it lives outside the source code. The code may be perfectly converted to Python 3, but if it reads data that was serialized under Python 2, the deserialization will produce unexpected results.

The canonical example is `pickle`. A pickled Python 2 `str` object deserializes as `bytes` in Python 3, not `str`. A pickled Python 2 `unicode` object deserializes as `str` in Python 3. This means that any pickled data structure containing `str` values will have its string fields come back as `bytes` when loaded under Python 3. If the application then tries to use those fields as text (concatenating with other strings, formatting into output, comparing with string literals), it will get `TypeError`s.

The problem is compounded by the fact that pickle is used in many places beyond explicit `pickle.dump` calls. Redis and Memcached clients often pickle Python objects before storing them. Session middleware in web frameworks may pickle session data. Message queues may pickle task arguments. ORM libraries may pickle cached query results. Any of these can contain Py2-style `str` values that will deserialize incorrectly under Py3.

The scope of the concern extends beyond pickle to any persistence mechanism that encodes Python type information:

- **`pickle` and `cPickle`**: The most common case. Pickle protocol versions 0, 1, and 2 are compatible across Python versions in the sense that Py3 can read data pickled by Py2, but the types of the deserialized objects change as described above. Pickle protocols 3+ are Py3-only and cannot be read by Py2 at all.
- **`marshal`**: The `marshal` module's format is explicitly not guaranteed to be compatible across Python versions. It is intended for `.pyc` files, which Python regenerates as needed. Any use of `marshal` for persistence (writing to files, sending over network) is extremely fragile across version boundaries. In practice, `marshal` persistence is rare, but it does occur in some legacy codebases.
- **`shelve`**: Built on `pickle` and `dbm`, `shelve` databases inherit all of pickle's type-change issues plus the potential for `dbm` format incompatibilities between Py2 and Py3. A `shelve` database created under Py2 may not be openable under Py3 depending on the `dbm` backend used.
- **Custom serialization**: Classes implementing `__getstate__` and `__setstate__`, manual `struct` packing, custom binary formats, protocol buffers with Python-2-specific field types. These require case-by-case analysis. The key question for each is: does the serialized format include type information that will change meaning between Py2 and Py3?
- **JSON and YAML**: Generally safe since they have their own type systems (JSON strings are always Unicode, JSON has no bytes type). However, Python 2 code may rely on `json.dumps()` returning `str` (bytes) rather than `str` (text). Under Py3, `json.dumps()` returns `str` (text). Code that passes the JSON output to a function expecting bytes (e.g., `socket.send(json.dumps(data))`) will break.

For a concrete example, consider what happens when Python 3 loads a Py2-pickled dictionary:

```python
# Python 2: pickle a dictionary with str keys and values
import pickle
data = {'name': 'sensor-01', 'status': 'active', 'reading': 42.5}
with open('state.pkl', 'wb') as f:
    pickle.dump(data, f, protocol=2)

# Python 3: load the same pickle
import pickle
with open('state.pkl', 'rb') as f:
    data = pickle.load(f)
# data is now: {b'name': b'sensor-01', b'status': b'active', b'reading': 42.5}
# Note: string keys and values are bytes, not str!

# This breaks:
print(data['name'])       # KeyError: 'name' (key is b'name', not 'name')
print(data[b'name'])      # b'sensor-01' (bytes, not str)
```

The fix depends on the context. For Py3 to load Py2 pickles with string values as text, you can use:

```python
data = pickle.load(f, encoding='latin-1')  # Py2 str -> Py3 str (via latin-1)
```

The `encoding='latin-1'` parameter tells pickle to decode Py2 `str` values using Latin-1, which is a lossless byte-to-character mapping (every byte 0x00-0xFF maps to a character). This preserves the data but may produce incorrect text if the original data was not Latin-1 (e.g., if it was UTF-8, the multi-byte sequences will be decoded as individual Latin-1 characters, producing garbled text). For data that was genuinely ASCII, `encoding='latin-1'` works correctly because ASCII is a subset of Latin-1.

The migration plan must include an inventory of every serialization point and a strategy for handling existing serialized data. The strategies include:

1. **Migration scripts**: Deserialize under Python 2, re-serialize under Python 3. This is the most thorough approach but requires both interpreters to be available and access to all the serialized data. The script runs under Python 2 to load the data, converts it to a neutral format (JSON, for instance), and then a Python 3 script loads the neutral format and re-serializes in the Py3 format. For databases and file-based persistence, this is usually feasible. For distributed caches (Redis, Memcached), it may be easier to simply flush the cache and accept a cold-start performance penalty.

2. **Compatibility layers**: Write deserialization code that detects whether data was serialized under Py2 or Py3 and handles both formats. The `encoding='latin-1'` approach described above works for fields where the Py2 `str` was actually ASCII or Latin-1 text, but for binary data fields, `encoding='bytes'` (which keeps them as `bytes`) may be more appropriate. When a single pickle contains both text and binary fields, neither option is universally correct -- the compatibility layer must know the semantic type of each field. This per-field knowledge is exactly what the Phase 0 data layer analysis provides.

3. **Clean break**: Drop the existing serialized data and start fresh. This is the simplest approach and is acceptable for caches, temporary files, session data, and any other transient storage. It is unacceptable for persistent databases, configuration stores, and any data that has business value. The decision about which data can be dropped and which must be migrated should be made during Phase 0 and documented in the migration readiness report.

For large-scale serialization migration, a phased approach within the data migration itself is often necessary. First, update the code to read both old-format and new-format data (dual-read capability). Then migrate the data to the new format. Then remove the old-format read code. This "expand/migrate/contract" pattern avoids a big-bang data migration and allows the data to be migrated gradually.

### 4.3 Binary Protocols

Industrial codebases frequently communicate with hardware devices using binary protocols. Modbus over serial or TCP for SCADA systems, OPC-UA for industrial automation, DNP3 for electric utilities, BACnet for building automation, MQTT with binary payloads for IoT sensors, and a variety of proprietary serial protocols for specific equipment. These protocols use packed binary data, typically constructed and parsed with `struct.pack` and `struct.unpack`.

Binary protocol code may actually be *easier* to migrate than text-handling code, provided it already treats data as bytes throughout. The `struct` module works with `bytes` in both Python 2 and Python 3, and protocol-level code that stays in the bytes domain requires minimal changes. A Modbus frame parser that reads bytes from a socket, unpacks register values with `struct.unpack`, and returns integers is doing everything in the bytes domain and will likely work unchanged on Python 3.

The risk materializes at the boundary where binary protocol data becomes "text." Consider this common pattern in industrial code:

```python
# Python 2 -- this "works" because str is bytes
register_value = struct.unpack('>H', data[3:5])[0]
status_text = "Sensor %s reading: %d" % (sensor_id, register_value)
log_file.write(status_text + "\n")
```

Under Python 2, `sensor_id` could be either `str` (bytes) or `unicode`, and the `%` formatting would handle both via implicit conversion. Under Python 3, if `sensor_id` comes from a bytes source (e.g., a serial device identification packet), it is `bytes`, and `"Sensor %s"` formatting will produce `"Sensor b'SEN-001'"` instead of `"Sensor SEN-001"` -- including the `b''` prefix in the output. This is not an exception; it is silently wrong output.

Every such boundary must be identified and explicitly resolved. The resolution requires a decision: decode the bytes to text at the protocol layer (with a specific encoding), or change the downstream code to handle bytes. The first approach is cleaner but requires knowing the encoding; the second approach avoids the encoding question but means text-oriented operations (formatting, logging, display) need to work with bytes, which is unnatural in Python 3.

For most industrial protocols, the encoding of text fields is specified in the protocol documentation. Modbus device identifications are typically ASCII. OPC-UA uses UTF-8 for all string values. DNP3 uses ASCII for device names. Knowing the protocol's encoding specification lets you decode at the protocol parsing layer, which keeps the rest of the application in the text domain.

### 4.4 Mainframe Data

Mainframe systems typically use EBCDIC encoding, which assigns completely different byte values than ASCII or UTF-8. The letter 'A' is `0xC1` in EBCDIC but `0x41` in ASCII. The digit '0' is `0xF0` in EBCDIC but `0x30` in ASCII. Even the space character differs: `0x40` in EBCDIC, `0x20` in ASCII.

Python 2 code that processes mainframe data may use hardcoded byte constants for field delimiters, record separators, or control characters. These constants are EBCDIC-specific but appear in the code as bare integers or single-character strings without any indication of their encoding context. A field delimiter that appears as `'\x6b'` in the source code is a comma in EBCDIC (cp500) but the letter 'k' in ASCII. Without documentation or access to the original developers, determining the intent requires examining the data files alongside the code.

Python's `codecs` module supports several EBCDIC variants:

| Code Page | Name | Usage |
|-----------|------|-------|
| `cp037` | EBCDIC US/Canada | IBM mainframes, North America |
| `cp500` | EBCDIC International | IBM mainframes, international |
| `cp1047` | EBCDIC Open Systems | Unix System Services on z/OS |
| `cp1140` | EBCDIC US with Euro | Updated cp037 with Euro sign |

Determining which EBCDIC variant is in use matters because the code pages differ in their mapping of punctuation and special characters. The uppercase letters A-Z and digits 0-9 are the same across all EBCDIC variants, but characters like curly braces, square brackets, and the pipe symbol differ. If the data contains only alphanumeric characters and basic punctuation, the variant may not matter. If it contains programming-language syntax, configuration file delimiters, or data with special characters, using the wrong variant produces incorrect output.

The correct Py3 migration is to add explicit `decode('cp500')` or equivalent at the ingestion point, converting EBCDIC bytes to Unicode text as early as possible in the data pipeline. However, identifying which code paths handle EBCDIC data requires either documentation, sample data files, or pattern recognition (looking for byte constants in the EBCDIC range that do not make sense as ASCII).

A useful heuristic for detecting EBCDIC in code: if the source contains byte constants in the range `0xC1`-`0xE9` (the EBCDIC letter range) where the corresponding ASCII characters would not make sense in context, the code is likely handling EBCDIC data. For example, a record parser that checks for `data[0] == '\xC1'` is testing whether the first byte is the letter 'A' in EBCDIC; the same byte is a Latin-1 control character (A-with-tilde) and an incomplete UTF-8 sequence, neither of which makes sense as a record-type indicator.

A particularly tricky case is code that performs manual byte-level manipulation of EBCDIC data -- testing individual bytes against hardcoded constants, swapping byte ranges, or performing arithmetic on character values. This code cannot be mechanically converted; it must be understood and rewritten to use `codecs.decode` and `codecs.encode` or the `ebcdic` third-party library.

### 4.5 Fixed-Width Parsing

G-code (CNC machine instructions), M-code (machine auxiliary functions), fixed-width record formats (COBOL-style), EDI transaction sets, and other positional text formats are parsed using string indexing: `line[0:3]` extracts a field at a known offset and width. This pattern is simple in Python 2 because `str` indexing always returns a `str` of length 1. In Python 3, the behavior depends on the type:

```python
# Python 3
text = "HELLO"
text[0]      # 'H' -- a str of length 1, as expected

binary = b"HELLO"
binary[0]    # 72 -- an int, not b'H'
binary[0:1]  # b'H' -- a bytes of length 1 (slicing preserves type)
```

The difference between indexing (returns `int` for `bytes`) and slicing (returns `bytes` for `bytes`) is a common source of bugs in migrated code. Python 2 code that reads a file in binary mode and indexes individual bytes will get integers instead of characters under Python 3, breaking any subsequent comparison with character literals.

The migration strategy for fixed-width parsing depends on whether the data is semantically bytes or text.

**Text-based fixed-width formats** (ASCII G-code, most CSV files, human-readable report formats) should be read with an explicit encoding: `open(path, 'r', encoding='ascii')` or `open(path, 'r', encoding='utf-8')`. All indexing operations work unchanged because the data is `str` in Python 3 and indexing `str` returns `str`.

```python
# G-code parsing -- text mode, works unchanged on Py3
with open(gcode_path, 'r', encoding='ascii') as f:
    for line in f:
        command = line[0:1]    # 'G' or 'M' -- str in both Py2 and Py3
        code = line[1:3]       # '01', '28', etc. -- str in both
        if command == 'G':
            process_g_code(int(code), line[3:].strip())
```

**Binary record formats** should be read with `open(path, 'rb')`. Here is where the indexing behavior change matters:

```python
# Python 2
data = open(path, 'rb').read()
record_type = data[0]        # '\x01' -- a str of length 1
if record_type == '\x01':    # comparison works

# Python 3
data = open(path, 'rb').read()
record_type = data[0]        # 1 -- an int, not b'\x01'
if record_type == b'\x01':   # silently False: int != bytes (no TypeError, just wrong)
if record_type == 0x01:      # correct: compare int to int

# Or use slicing to preserve bytes type:
record_type = data[0:1]      # b'\x01' -- a bytes of length 1
if record_type == b'\x01':   # comparison works
```

The slicing approach (`data[0:1]` instead of `data[0]`) is often the easiest migration path because it requires only changing index expressions without changing the comparison logic. The integer comparison approach (`data[0] == 0x01`) is more explicit but requires changing every comparison site.

**Mixed formats** -- records with both text and binary fields at known offsets -- require the most careful handling. The record must be read as bytes, and text fields must be decoded individually:

```python
# A fixed-width record with mixed fields
def parse_sensor_record(record: bytes) -> dict:
    """Parse a 64-byte sensor record with mixed text/binary fields.

    Layout:
        Bytes  0-7:   Device ID (ASCII text)
        Bytes  8-11:  Timestamp (uint32, big-endian)
        Bytes 12-15:  Reading (float32, big-endian)
        Bytes 16-31:  Location name (ASCII text, space-padded)
        Bytes 32-63:  Raw calibration data (binary, opaque)
    """
    return {
        'device_id': record[0:8].decode('ascii').strip(),
        'timestamp': struct.unpack('>I', record[8:12])[0],
        'reading': struct.unpack('>f', record[12:16])[0],
        'location': record[16:32].decode('ascii').strip(),
        'calibration': record[32:64],  # stays as bytes
    }
```

This pattern -- read as bytes, decode text fields at extraction -- is the correct general approach for mixed-format data. It keeps the record boundary handling in the bytes domain (where positional offsets are byte offsets, as expected) and converts to text only for fields that are semantically text.

### 4.6 Mixed and Legacy Databases

Long-lived codebases accumulate database formats. A system that started with flat files in the 1990s may have added DBF (dBase) files for relational data, SQLite for local caching, PostgreSQL or MySQL for the main application database, and Redis for sessions or queuing. Each database technology has its own encoding behavior, and the Python database drivers have their own encoding configuration.

Under Python 2, most database drivers returned `str` (bytes) for text columns by default, unless explicitly configured to return `unicode`. Code that consumed database results treated them as `str` and passed them around freely. Under Python 3, most drivers default to returning `str` (text), which is generally the correct behavior. But code that passes database results to functions expecting bytes will break.

The specific concerns by database type:

- **SQLite**: Under Python 2, `sqlite3` returns `str` for TEXT columns if the text is ASCII-compatible, and `unicode` if it contains non-ASCII characters. Under Python 3, it always returns `str` (text). Code that handled both types via `isinstance` checks needs simplification.
- **PostgreSQL (psycopg2)**: Under Python 2, `psycopg2` returns `str` for `TEXT`/`VARCHAR` columns. Under Python 3, it returns `str` (text). The `bytea` type returns `bytes` in both versions. The migration concern is code that assumed text columns return bytes.
- **MySQL (pymysql, mysqlclient)**: Similar to PostgreSQL. The `charset` connection parameter affects encoding behavior in both versions but in different ways.
- **DBF files**: The `dbfread` or `dbf` libraries handle encoding, but legacy code may use custom DBF parsers that read raw bytes and do not handle encoding explicitly.
- **Flat files**: Fixed-width and delimited flat files are the most common database format in legacy industrial codebases. Encoding is usually implicit (whatever the system's default encoding was when the code was written). Migration requires identifying and specifying the encoding explicitly.

The Phase 0 analysis must produce a complete inventory of all database connections, their encoding configurations, and the code paths that consume their output. This inventory, combined with the encoding analysis and serialization inventory, forms the foundation for the entire data layer migration strategy.

### 4.7 The Data Layer Migration Strategy

Given the complexity of data layer concerns, the migration strategy for data-handling code follows a specific pattern that is worth articulating explicitly.

**Step 1: Classify every data path.** For each place where data enters the application (file read, socket receive, database query, serial port read, HTTP request body), determine whether the data is semantically bytes or text. Some are obvious: Modbus register data is bytes, user-facing error messages are text. Others are ambiguous: a CSV file could be text (human-readable records) or bytes (raw sensor dumps).

**Step 2: Establish encoding contracts.** For each data path classified as text, determine the encoding. Often this information exists in protocol specifications, database configuration, or file format documentation. When it does not, inspect sample data. Look for:

- BOM markers at the start of files (indicates UTF-8 with BOM, UTF-16, or UTF-32).
- Byte patterns in the high range (0x80-0xFF). If all high bytes come in multi-byte sequences following UTF-8 rules, the data is likely UTF-8. If high bytes appear individually, the data is likely Latin-1, Windows-1252, or another single-byte encoding.
- Byte patterns that make sense as EBCDIC. If the letter 'A' appears at byte value 0xC1 instead of 0x41, the data is EBCDIC.
- The `chardet` or `charset-normalizer` library can automate encoding detection on sample data, though the results should be verified.

**Step 3: Decode at the boundary.** The principle is: decode bytes to text as early as possible (at the ingestion point), and encode text to bytes as late as possible (at the output point). This keeps the interior of the application in the text domain, where string operations work naturally. The boundary is the place to add explicit `decode()` calls with the determined encoding, and the boundary is the place to add explicit `encode()` calls for output.

```python
# Before (Python 2 -- encoding is implicit)
data = serial_port.read(100)
record = parse_fixed_width(data)
log.info("Received: %s", record['sensor_name'])

# After (Python 3 -- encoding is explicit)
raw_data = serial_port.read(100)           # bytes
text_data = raw_data.decode('ascii')       # str (text) -- decode at boundary
record = parse_fixed_width(text_data)      # all text from here
log.info("Received: %s", record['sensor_name'])
```

**Step 4: Keep binary data as bytes.** Data that is semantically bytes -- protocol frames, encryption outputs, hash values, raw file content that will be written byte-for-byte to another file -- should stay as `bytes` throughout. Do not decode it. Functions that operate on binary data should be annotated with `bytes` parameters and return types, making the contract explicit.

**Step 5: Handle the ambiguous cases explicitly.** Some data is genuinely both: a protocol frame that contains text fields embedded in a binary structure, for instance. For these, decode the text fields individually at the point of extraction, and keep the overall structure as bytes. Document the encoding of each text field.

```python
# A protocol frame with embedded text fields
def parse_device_info(frame: bytes) -> dict:
    """Parse device information from a binary protocol frame."""
    device_id = frame[0:8].decode('ascii').strip()    # text field: ASCII
    firmware = frame[8:16].decode('ascii').strip()     # text field: ASCII
    serial_num = frame[16:24]                          # binary field: stays as bytes
    return {
        'device_id': device_id,      # str
        'firmware': firmware,         # str
        'serial_number': serial_num,  # bytes
    }
```

This approach -- classify, contract, decode at boundary, keep binary as binary, handle ambiguity explicitly -- provides a systematic method for resolving the data layer issues that are the migration's hardest challenge.


## 5. Linting Strategy

Linting in a migration project serves a fundamentally different purpose than linting in normal development. In normal development, linting enforces code quality standards. In a migration, linting is an active migration driver: it discovers issues, prevents regression, and enforces progress. The linting strategy should evolve through three tiers that correspond to the migration phases.

### 5.1 Discovery

Before any code is changed, run every available Python 2-to-3 compatibility checker against the codebase and collect the results as a machine-readable baseline. This baseline serves two purposes: it quantifies the scope of the migration (how many issues, of what types, in which modules), and it provides a reference point for measuring progress as the migration proceeds.

**`pylint --py3k`** is the primary discovery tool. It is purpose-built for this problem and produces categorized warnings for Python 2 idioms that will break or behave differently under Python 3. Its output is machine-readable (JSON or parseable text) and can feed directly into the codebase analysis. The `--py3k` mode checks for over 20 specific Python 2 patterns, including `dict.has_key()`, `print` statements, long suffixes, backtick repr, `<>` operator, and more.

**`pyupgrade --py3-plus`** in dry-run mode shows what automated rewrites are possible. Running `pyupgrade --py3-plus --keep-percent-format path/to/file.py` in check mode (without writing) produces a diff of what it would change. This is valuable not as a linting tool per se, but as a way to estimate how much of the migration is mechanically automatable versus requiring manual intervention.

**`flake8`** with the **`flake8-2020`** plugin catches forward-incompatible patterns that the other tools miss. The `flake8-2020` plugin specifically targets patterns that break on Python 3.10 and later, such as string comparisons with `sys.version` that assume the version string starts with a single digit (`sys.version[0] == '3'` works on Python 3.0-3.9 but not on 3.10+ where `sys.version` starts with "3.1"). These are the kind of subtle issues that survive an initial migration and only break years later on a version upgrade.

**Custom AST-based checks** can supplement these tools for project-specific patterns. If the codebase has domain-specific conventions (e.g., all SCADA data handlers must use explicit encoding, all mainframe ingestion must go through a specific adapter module), custom lint rules can verify that these conventions are maintained through the migration. The `ast` module makes it straightforward to write checkers for specific patterns:

```python
import ast

class BytesStringMixingChecker(ast.NodeVisitor):
    """Flag operations that mix bytes and string literals.

    Uses ast.Constant (Python 3.8+). The older ast.Bytes and ast.Str
    node types were removed in Python 3.12.
    """

    def _is_bytes(self, node):
        return isinstance(node, ast.Constant) and isinstance(node.value, bytes)

    def _is_str(self, node):
        return isinstance(node, ast.Constant) and isinstance(node.value, str)

    def visit_BinOp(self, node):
        if isinstance(node.op, ast.Add):
            if (self._is_bytes(node.left) and self._is_str(node.right)) or \
               (self._is_str(node.left) and self._is_bytes(node.right)):
                print(f"Line {node.lineno}: mixing bytes and str in concatenation")
        self.generic_visit(node)
```

The aggregate results of all discovery linters form the lint baseline. This baseline should be stored as a structured artifact (JSON) so that progress can be measured automatically. As the migration progresses, re-running the discovery linters and comparing against the baseline shows exactly how many issues have been resolved and how many remain.

### 5.2 Prevention

Once modules begin progressing through conversion phases, lint rules must prevent regression. A module that has been converted to Phase 2 should not have `dict.has_key()` reintroduced by a developer who is not aware of the migration state. The lint configuration for each module should correspond to its current migration phase, creating a progressive set of requirements.

This requires a mechanism to associate lint configurations with individual files or modules. Several approaches work:

- **Per-directory configuration files**: Place `.pylintrc` or `setup.cfg` in each package directory with the appropriate strictness level. This works well for package-level granularity but not for individual files within the same package that are at different phases.
- **Comment-based directives**: Add a header comment like `# migration-phase: 2` to each file and write custom lint rules that read this directive and adjust their behavior accordingly. This gives per-file granularity.
- **External configuration mapping**: Maintain a separate mapping file (JSON or YAML) that maps file paths to migration phases, and have lint rules read this mapping to determine which checks apply. This is the most flexible approach and integrates naturally with the migration state tracker.

Pre-commit hooks are the enforcement mechanism. When a developer modifies a file, the pre-commit hook determines the file's migration phase (from the state tracker or a configuration file), selects the appropriate lint ruleset, and runs the checks. If the change introduces a regression -- a Python 2 idiom in a file that has been converted past that point -- the commit is blocked with a message explaining which rule was violated and why.

The progressive nature of the lint configuration is important. An unconverted module gets discovery rules only (informational, not blocking). A module that has completed Phase 1 gets rules requiring `__future__` imports to be present and blocking the introduction of new Python 2 idioms. A module that has completed Phase 2 gets rules requiring all Python 2 syntax to be eliminated. The lint configuration is effectively a codification of the module's migration contract: "this module has reached this level of Py3 compatibility, and it must not regress."

### 5.3 Enforcement

In the later phases of migration (Phase 3 and beyond), linting shifts from preventing regression to enforcing quality standards on the converted code.

**`mypy`** in strict mode validates that type annotations are present and correct. Since type annotations are being added as part of Phase 3 work, `mypy` becomes the gate that ensures the annotations are not merely present but actually useful -- catching type errors that would otherwise be runtime failures. Gradual typing is the right approach: start with `--ignore-missing-imports` and `--allow-incomplete-defs`, then progressively tighten the configuration as annotation coverage improves.

The `mypy` configuration should be per-module, matching the migration phase. A module at Phase 3 might use `--check-untyped-defs` (check function bodies even without annotations), while a module at Phase 4 might require `--strict` (all functions annotated, all code checked). This prevents `mypy` from blocking progress on modules that are still being annotated while enforcing strictness on modules that are supposed to be complete.

**`bandit`** checks for security regressions. The Python 2-to-3 migration can inadvertently introduce security issues, particularly around encoding confusion. A bytes/string mixup in input validation could bypass a security check that worked under Python 2's implicit conversions. `bandit` does not specifically target migration issues, but its general security checks (SQL injection, command injection, insecure deserialization) are worth running on newly converted code to ensure the conversion did not weaken any existing security measures.

**Custom rules that flag `six` or `future` usage** in modules that have completed Phase 3 ensure that compatibility shims are being removed as planned, not accumulating as permanent technical debt. A module that has passed Phase 3 should not need `six.moves.urllib` -- it should use `urllib.request` directly. A lint rule that flags these patterns encourages timely cleanup.

The progression from discovery to prevention to enforcement creates a ratchet mechanism. Each module can only move forward through the phases, and the linting infrastructure makes backward movement mechanically difficult. This is important in a long-running migration where many developers are working concurrently. Not everyone has the full migration context in their head, and the lint rules encode that context into automated checks that run on every commit.

### 5.4 The Lint Progression in Practice

To make the progressive lint configuration concrete, here is what the effective ruleset looks like for a module at each migration phase:

**Unconverted (Phase 0)**: Discovery rules only. Run `pylint --py3k` and `flake8-2020` in informational mode. No blocking. The output feeds the Phase 0 analysis.

**Phase 1 complete**: The module has `__future__` imports and characterization tests. Lint rules require:
- All four `__future__` imports present at the top of the file.
- No new `dict.has_key()`, `print` statements (without function syntax), or other Py2 idioms introduced in new code.
- These rules *block commits* -- a developer cannot accidentally regress a Phase-1-complete module.

**Phase 2 complete**: The module has been mechanically converted. All Python 2 syntax has been removed. Lint rules require:
- Everything from Phase 1, plus:
- No `xrange`, `raw_input`, `unicode()`, `long()`, backtick repr, `<>`, or `exec` statements.
- No relative imports (all imports are absolute or explicit-relative).
- No Python 2-only exception syntax.
- `pyupgrade --py3-plus` reports no further changes needed.

**Phase 3 complete**: The module has been semantically fixed. Lint rules require:
- Everything from Phase 2, plus:
- `mypy` passes with `--check-untyped-defs` (or stricter, depending on project policy).
- No `six` or `future` library usage.
- No `# type: ignore` comments without an explanation.
- All public functions have type annotations.
- `bandit` reports no new security findings.

**Phase 4 complete**: The module has been verified. Lint rules require:
- Everything from Phase 3, plus:
- `mypy --strict` passes.
- No migration-related `TODO` or `FIXME` comments remain.
- No `__future__` imports (they are cosmetic clutter on Py3).
- No `sys.version_info` conditionals.

This progression means that as a module advances, the bar for code changes to that module gets higher. A developer working on a Phase-4-complete module cannot introduce `dict.has_key()`, cannot skip type annotations on new functions, and cannot add `six` usage -- the pre-commit hook catches it. The linting infrastructure acts as institutional memory, encoding the migration decisions into automated enforcement.


## 6. Target Version Considerations

Migrating from Python 2 does not mean simply "make it run on Python 3." The target Python 3 minor version determines which standard library modules are available, which deprecations have become errors, and which new features and idioms can be leveraged. The gap between Python 3.9 and Python 3.13 is substantial, and the choice of target version has practical consequences for the cost and scope of the migration effort.

### 6.1 Version-Specific Breaking Changes

**Python 3.9** introduced built-in generic types (`list[str]` instead of `typing.List[str]`), deprecating the `typing` module generics. It also added the `zoneinfo` module, replacing `pytz` for timezone handling in many cases. Python 3.9's security support ended in October 2025, so it is no longer a recommended target for new migrations, but codebases already targeting it will encounter a relatively stable platform with few surprises.

**Python 3.10** brought structural pattern matching (`match`/`case`) and significantly improved error messages. The improved error messages are genuinely useful during a migration. When a converted file has a syntax error, Python 3.10+ provides suggestions like "did you mean `print(x)` instead of `print x`?" or "did you forget a comma?" that are more helpful than a bare `SyntaxError` during debugging. Pattern matching is a new feature, not a migration concern, but it may be attractive enough to justify targeting 3.10+ if you are already touching every file.

**Python 3.11** delivered a 10-60% performance improvement over 3.10 (via the Faster CPython project), added `tomllib` to the standard library (a TOML parser), and introduced exception groups with `except*`. The performance improvement is relevant to the verification phase: performance benchmarks against Python 2 should account for the fact that Python 3.11+ is substantially faster than earlier 3.x releases, which may mask regressions in specific code paths. `asyncio.TaskGroup` was also added, relevant for codebases that use asynchronous I/O.

**Python 3.12** introduced the most disruptive set of breaking changes since the original Py2/Py3 split:

- **`distutils` removed entirely.** Any code using `from distutils import ...` must be migrated to `setuptools` (for packaging functionality) or `sysconfig` (for platform-specific paths and configuration). This is a hard `ImportError`, not a deprecation warning. Given that `distutils` was the standard packaging tool for over a decade, many legacy codebases use it pervasively.
- **Approximately 20 standard library modules removed.** The full list: `aifc`, `audioop`, `cgi`, `cgitb`, `chunk`, `crypt`, `imghdr`, `mailcap`, `msilib`, `nis`, `nntplib`, `ossaudiodev`, `pipes`, `sndhdr`, `spwd`, `sunau`, `telnetlib`, `uu`, `xdrlib`. Any import of these modules becomes an `ImportError`. Of these, `cgi` (CGI scripting) and `telnetlib` (Telnet client) are the most likely to appear in legacy codebases. `cgi.FieldStorage` was widely used in older web applications, and `telnetlib` appears in network management and automation code.
- **`wstr` removed from the Unicode C API.** C extensions that accessed the `wstr` field of Unicode objects (an internal representation used for compatibility with Windows `wchar_t` APIs) must be updated. This affects extensions compiled against Python 3.0-3.11 that used `PyUnicode_AS_UNICODE()` or accessed the `wstr` field directly.
- **f-string grammar relaxed.** Nested quotes, backslashes in expressions, and comments inside f-strings are now allowed. This is not a breaking change but a new capability that `pyupgrade` can take advantage of when targeting 3.12+.

**Python 3.13** continued the removal trajectory and introduced two major experimental features. The free-threaded build (no GIL) is available as an experimental option for CPU-bound parallelism, though most code will not benefit from it without explicit adaptation. The experimental JIT compiler is a performance optimization that is transparent to application code. For C extensions, 3.13 continued removing deprecated C API functions, further narrowing the set of available APIs. The `pathlib.Path` class became abstract, breaking code that subclassed it directly (uncommon, but worth checking).

### 6.2 Implications for Migration Tooling

These version differences mean that a tool targeting Python 3.9 and a tool targeting Python 3.12 must make different decisions about the same code:

- Code importing `cgi` is fine for target 3.9-3.11 but broken for 3.12+. The tool must suggest a replacement (`http.server` for simple CGI, or a web framework).
- Code using `distutils` is fine for target 3.9-3.11 but broken for 3.12+. The tool must suggest migration to `setuptools`.
- Code with C extensions using `wstr` or `PyUnicode_AS_UNICODE()` is fine for 3.9-3.11 but broken for 3.12+.
- Code using `typing.List[str]` works on all versions but triggers deprecation warnings on 3.9+ and can be modernized to `list[str]`.
- Code using `telnetlib` needs a third-party replacement (`telnetlib3`, or a different approach) for 3.12+.

Every tool and skill that generates or transforms code must accept a `target_version` parameter. This parameter controls:

1. Which standard library replacements are suggested (e.g., `cgi` replacement only needed for 3.12+).
2. Which deprecation warnings are treated as errors versus informational.
3. Which new idioms are available for use (e.g., pattern matching only for 3.10+, `list[str]` only for 3.9+).
4. Which C API compatibility checks are version-appropriate.
5. Whether `distutils` usage is flagged as a blocker or merely a deprecation.

The Phase 0 analysis should produce a version compatibility matrix showing the incremental cost of targeting each version. For many codebases, the jump from 3.11 to 3.12 is substantially more expensive than the jump from 3.9 to 3.11, due to the `distutils` removal and stdlib module purge.

### 6.3 Choosing a Target Version

The target version decision involves balancing three factors:

**Support lifecycle.** Each Python minor version has approximately 5 years of support (2 years active, 3 years security-only). Targeting an older version means it will reach end-of-life sooner, potentially requiring another migration. Python 3.9's security support ended in October 2025, 3.10 ends in October 2026, 3.11 in October 2027, 3.12 in October 2028, and 3.13 in October 2029. Check the [Python Developer's Guide](https://devguide.python.org/versions/) for current status. A migration that takes a year to complete should target at least 3.11 to ensure several years of supported runtime after completion.

**Migration cost.** As described above, the cost increment from 3.11 to 3.12 is larger than from 3.9 to 3.11 for most codebases. If the codebase uses `distutils`, `cgi`, `telnetlib`, or any of the other removed stdlib modules, targeting 3.12+ adds a library replacement task on top of the core Py2-to-Py3 migration. This is not prohibitive -- it is additional scope that must be planned for.

**Ecosystem compatibility.** Third-party libraries increasingly drop support for older Python 3 versions. A library that requires 3.10+ cannot be used if your target is 3.9. Conversely, some older libraries may not yet support 3.13. The Phase 0 library compatibility analysis should identify any constraints imposed by the library ecosystem.

The practical recommendation for most migrations starting in 2025-2026 is to target **Python 3.11 or 3.12**. Python 3.11 avoids the 3.12 stdlib removals and has the best performance characteristics of any 3.x release at the time of writing. Python 3.12 is the better long-term choice if the additional migration cost of handling the stdlib removals is acceptable, because it provides a longer support window and benefits from continued ecosystem evolution. Python 3.13 is too new for a conservative migration target -- its experimental features (no-GIL, JIT) may have ecosystem compatibility issues with some third-party libraries.

This decision should be made before Phase 1 begins and held fixed throughout the migration. Changing the target version mid-migration invalidates previous conversion decisions and requires re-running gate checks. If you realize mid-migration that you need a different target version (e.g., a critical library requires 3.12+), treat it as a scope change with appropriate re-planning.


## 7. The Phase Model

The migration is organized into six phases (0 through 5), each with defined purposes, gate criteria, and rollback procedures. Phases are sequential at the project level -- you must complete Phase 0 before starting Phase 1 -- but concurrent at the module level. While the project is in the "Phase 2/3" period, individual modules will be at different phases depending on their position in the dependency graph and the resolution of their specific issues.

The phase model is not a waterfall. It is a pipeline: as early modules complete Phase 2 and enter Phase 3, later modules may still be entering Phase 2. The phases define what *kind* of work is done, not when all modules must be at the same stage.

### 7.1 Phase 0: Discovery and Assessment

Phase 0 answers the question: what do we have? Before touching a single line of production code, the project needs a comprehensive understanding of the codebase's structure, its data flows, its risk profile, and its readiness for migration. Skipping or shortcutting Phase 0 is the single most common cause of migration project failure, because it leads to incorrect scope estimates, missed risk areas, and surprises during conversion that should have been anticipated.

The core deliverable is a migration readiness report. The report is not a formality; it is the artifact that determines scope, timeline, and risk, and it should be treated with the same rigor as a design document for a new system.

The report covers:

- **Dependency graph.** The import graph of the entire codebase, with topological sort for migration ordering and cluster detection for tightly-coupled module groups. The graph should distinguish between internal dependencies (between modules in the codebase) and external dependencies (third-party packages), because the migration strategy differs.
- **Py2-ism inventory.** Every Python-2-specific pattern in the codebase, categorized by type. The primary categorization is syntax-only issues (automatable, low risk) versus semantic issues (requiring human judgment, high risk). The syntax/semantic distinction is the primary risk stratification mechanism. A secondary categorization by domain (print statements, exception handling, dictionary methods, bytes/string, integer division, metaclasses, etc.) helps with planning the Phase 2 and Phase 3 work.
- **Test coverage.** Per-module test coverage data, which determines where characterization tests must be generated before conversion can safely proceed. Modules with zero test coverage that sit on the critical path are the highest priority for test generation.
- **Version compatibility matrix.** For each candidate target Python 3 version, what breaks? How many modules use `distutils`? How many import removed stdlib modules? How many C extensions use deprecated APIs? This matrix informs the target version decision.
- **Data layer analysis.** The full data layer inventory: encoding patterns, serialization formats, binary protocol usage, database connections, and every point where bytes become text. This is discussed in detail in Section 4.

**C extensions and native code** must be identified in Phase 0 because they follow a fundamentally different migration path from pure Python code. C extensions (`*.c` files compiled against the Python C API), Cython modules (`*.pyx`, `*.pxd`), `ctypes` bindings, CFFI usage, and SWIG-generated wrappers all interact with the Python runtime at a level where the Py2-to-Py3 API changes are not just behavioral but structural.

Key C API changes that affect extensions:

- **`Py_UNICODE` removal.** The old fixed-width Unicode representation (`Py_UNICODE`, which was `wchar_t` on most platforms) was deprecated in Python 3.3 when PEP 393 introduced flexible string storage. Extensions using `Py_UNICODE` arrays must migrate to the PEP 393 API (`PyUnicode_DATA`, `PyUnicode_READ`, etc.) or, more practically, to string conversion functions that handle the internal representation automatically.
- **`PyCObject` deprecation.** `PyCObject` (used to wrap C pointers as Python objects) was deprecated in Python 3.1 and removed in Python 3.2, replaced by `PyCapsule`. Any extension using `PyCObject_FromVoidPtr` must switch to `PyCapsule_New`.
- **`tp_print` slot removal (3.12+).** The `tp_print` slot in the type struct, which was the C-level mechanism for the `print` statement's object formatting, was removed in 3.12. Extensions that set this slot must remove it.
- **`wstr` removal (3.12+).** The `wstr` and `wstr_length` fields of the Unicode object struct were removed in Python 3.12. Extensions that accessed these fields (via `PyUnicode_AS_UNICODE()` or direct struct access) must be updated.

If the codebase includes C extensions where the source is available, they can be assessed and migrated as part of the project, though the migration requires different skills (C development, Python C API knowledge) than the Python code migration. If it includes binary-only extensions (`.so` or `.pyd` files without source), those are potential migration blockers that must be identified as early as possible, because the mitigation (finding alternative libraries, requesting updated versions from vendors, or reimplementing in pure Python) takes time.

**Third-party library compatibility** should also be assessed in Phase 0. For each `import` of an external package, determine whether the currently-pinned version supports Python 3, whether a newer version exists that does, or whether no Python 3 version exists at all. The last category represents potential migration blockers: if a module depends on a library that has no Py3 version and no alternative, that module cannot be converted until the dependency issue is resolved. These blockers should surface early so that mitigation (finding alternatives, contributing Py3 support upstream, or reimplementing the functionality) can begin in parallel with the rest of the migration.

The gate for Phase 0 is stakeholder review and sign-off on the assessment report. The sign-off should be an explicit decision, not a passive acknowledgment. Stakeholders need to understand and accept the scope (how many modules, what risk profile), the timeline (critical path duration, estimated total effort), the target version (and its implications for stdlib compatibility), and the identified blockers (C extensions without source, libraries without Py3 versions). Nothing has been changed, so there is nothing to roll back. The assessment either provides sufficient confidence to proceed, or it surfaces blockers that must be resolved before the migration can begin.

### 7.1.1 The Migration Readiness Report

The migration readiness report deserves elaboration because it is the single most important artifact in the entire project. It determines whether the migration proceeds, how long it takes, and where the risk concentrates. A good readiness report has four sections:

**Scope assessment.** Total lines of code, number of Python files, number of packages, number of test files, overall test coverage percentage. Lines of code categorized by risk: low-risk (syntax-only issues), medium-risk (standard library replacements, common semantic patterns), high-risk (bytes/string boundary issues, binary protocol handling, EBCDIC data, custom serialization). This gives stakeholders a concrete sense of the project's size and complexity.

**Dependency analysis.** The dependency graph visualization (or a summary for very large codebases), the number of conversion clusters, the critical path length, and the list of gateway modules. The critical path length in particular should be highlighted, because it sets a hard lower bound on the migration timeline that cannot be reduced by adding resources.

**Risk inventory.** A prioritized list of specific risks with their locations in the codebase and their mitigation strategies. For example: "The `scada.modbus` package uses `struct.pack/unpack` with string format arguments that will be bytes in Py3. 47 call sites. Mitigation: Phase 3 bytes/string fixer with protocol-specific encoding rules." Or: "The `reports.pdf_generator` module uses the `pdflib` library version 2.1, which has no Py3 version. Mitigation: replace with `reportlab` or `fpdf2` in Phase 3."

**Recommendation.** Based on the analysis: target Python version, estimated timeline (broken into phases), required team size and skills, and go/no-go recommendation. If the analysis reveals migration blockers (binary-only C extensions, critical libraries with no Py3 path), the recommendation should include the cost and timeline for resolving those blockers before the migration can proceed.

A useful heuristic for estimating Phase 2 and Phase 3 effort: Phase 2 (mechanical conversion) typically takes 15-30 minutes per module for leaf modules and 1-2 hours per module for more complex modules, including review time. Phase 3 (semantic fixes) time varies enormously: a module with no bytes/string issues might take 30 minutes; a module at the center of the data layer with EBCDIC handling, protocol parsing, and serialization might take 2-5 days. The Phase 0 risk categorization drives the Phase 3 estimate. If 20% of modules are high-risk, those 20% will consume 80% of the Phase 3 effort.

### 7.2 Phase 1: Foundation

Phase 1 makes the codebase migration-ready without actually converting anything. The goal is to establish the safety nets, surface hidden issues, and create the infrastructure that supports the rest of the migration. Phase 1 is the phase most often skipped or shortchanged, and the consequence is that Phase 2 and Phase 3 are harder and riskier than they need to be.

**Future imports** are the primary mechanism for surfacing Python 3 behavior under Python 2. Adding `from __future__ import print_function, division, absolute_import, unicode_literals` to every Python file causes Python 2 to adopt Python 3's behavior for these specific features. The code still runs on Python 2, but it runs with Python 3 semantics for the imported features, flushing out assumptions that will break under Python 3.

The four future imports differ substantially in their risk profile, and this difference matters for the application order.

**`print_function`** is the lowest risk. It changes `print` from a statement to a function, so `print "hello"` becomes a `SyntaxError` and must be written as `print("hello")`. Because the old syntax simply fails to parse, any breakage is immediate and obvious. The fix is unambiguous: add parentheses. In most codebases, this can be applied globally with a single `futurize` Stage 1 pass, and the resulting breakage (if any) is trivially fixable.

**`absolute_import`** is also low risk. It changes import resolution to use absolute imports by default, so `import email` in a package that contains a local `email.py` will import the standard library `email` module instead of the local one. The fix for any breakage is to use explicit relative imports: `from . import email`. This is a good change regardless of the migration because relative imports are clearer and less fragile.

**`division`** is moderate risk. It changes the `/` operator from integer (floor) division to true division when both operands are integers. Without this import, `1/2` evaluates to `0` (floor division); with it, `1/2` evaluates to `0.5` (true division). Code that relies on integer division must use `//` instead of `/`. The risk is that this is a *silent behavior change* -- the code does not raise an exception, it just produces a different result. If the result is used in a way where the difference matters (array indexing, loop bounds, protocol field calculation), the bug can be subtle. If the code has good test coverage, the tests will catch it. If not, the bug may not surface until production.

**`unicode_literals`** is the highest risk and the most valuable. It changes every unadorned string literal from `bytes` to `unicode` in Python 2. This is the most disruptive future import because it changes the type of the most common expression in Python code. A string literal `"hello"` that was previously `str` (bytes) becomes `unicode` (text).

This breaks code that passes string literals to APIs expecting bytes:
- C extension functions that accept `const char*` may receive an unexpected Unicode object.
- `struct.pack('4s', "test")` passes a unicode string where bytes are expected.
- File paths on some operating systems where the filesystem API expects bytes.
- Socket operations where `send()` expects bytes.
- Binary protocol constructors where string literals are used as byte constants.

However, this breakage is *desirable* because it surfaces exactly the issues that will occur under Python 3. Every module that breaks when `unicode_literals` is added is a module that has bytes/string confusion that must be resolved. The list of breaking modules is one of the most valuable outputs of Phase 1 -- it identifies the highest-risk modules for Phase 3 semantic fixes.

The best practice is to apply `unicode_literals` separately from the other three imports, with targeted testing after each batch. Apply `print_function`, `absolute_import`, and `division` first (lower risk), verify CI is green, then apply `unicode_literals` in batches ordered by risk (leaf modules first, critical-path modules last), testing after each batch.

The `unicode_literals` import deserves a deeper discussion because it is both the most disruptive and the most informative of the four. When you add `unicode_literals` to a module under Python 2, every undecorated string literal becomes `unicode` instead of `str` (bytes). This means:

```python
from __future__ import unicode_literals

# Under Python 2, these are now unicode, not bytes:
name = "hello"           # type: unicode (was str)
path = "/tmp/data.txt"   # type: unicode (was str)
header = "Content-Type"  # type: unicode (was str)
delimiter = ","          # type: unicode (was str)

# These remain bytes (explicit b prefix):
magic_bytes = b"\x89PNG"  # type: str (bytes), explicit
```

Code that breaks after adding `unicode_literals` falls into predictable categories:

- **C extension calls**: `ctypes` functions, `cffi` calls, and hand-written C extensions that expect `const char*` may receive a Unicode object instead of bytes. The fix is to add `b""` prefix to string literals passed to C code, or to call `.encode('ascii')` at the call site.
- **Socket and serial operations**: `socket.send("data")` passes unicode to a function expecting bytes. Fix: `socket.send(b"data")` or `socket.send("data".encode('ascii'))`.
- **Struct packing**: `struct.pack('4s', "test")` passes unicode where bytes are expected. Fix: `struct.pack('4s', b"test")`.
- **File operations in binary mode**: `f.write("data")` to a file opened with `mode='wb'` passes unicode to a bytes-mode write. Fix: `f.write(b"data")` or change to text mode.
- **Dictionary keys**: Code that uses string literals as dictionary keys and then looks up the same keys with bytes (or vice versa) will find that the keys no longer match. This is rare but possible.
- **Regular expressions on bytes**: `re.search("pattern", bytes_data)` mixes unicode pattern with bytes data. Fix: `re.search(b"pattern", bytes_data)`.

Each of these breakages is valuable information. A module that breaks in 15 places when `unicode_literals` is added is a module with 15 bytes/string boundary issues that *must* be resolved for Python 3 compatibility. Without `unicode_literals`, these issues would not surface until Phase 3 or, worse, in production after cutover. With `unicode_literals`, they surface under Python 2, where the code is still in its known-working state and the fixes can be verified against existing behavior.

The list of modules that break, and the specific breakage patterns, becomes a key input to Phase 3 planning. Modules with many `unicode_literals` breakages are high-risk for Phase 3 and should be prioritized for test generation and careful human review during semantic fixes.

**Characterization test generation** is the other major Phase 1 activity. Characterization tests capture the existing behavior of code that lacks adequate test coverage. The distinction between characterization tests and correctness tests is important:

- **Characterization tests** assert that the code does what it currently does. They document the as-is behavior. Some of that behavior may be accidental (silently swallowing encoding errors), incorrect (truncating non-ASCII data), or implementation-dependent (relying on dictionary ordering). Characterization tests may need to be updated after conversion if the migration intentionally changes behavior.
- **Correctness tests** assert that the code does what it *should* do, according to a specification. These should not change during the migration.

Both types are valuable, but they serve different purposes in the migration. Characterization tests catch unintentional behavior changes (migration bugs). Correctness tests catch intentional behavior changes that went too far (over-migration).

Test generation must be encoding-aware, as discussed in Section 4.1. Tests should deliberately exercise:

- Non-ASCII UTF-8 text (accented characters like "caf\u00e9", CJK text, emoji, mathematical symbols).
- Data valid in one encoding but different in another (the byte `0xE9` is "e with acute accent" in Latin-1 but an incomplete UTF-8 sequence).
- Binary data containing byte sequences that look like valid text.
- Mixed-encoding inputs (a file with UTF-8 headers and Latin-1 body data).
- Empty strings, null bytes, BOM markers, and other edge cases.

Property-based testing with `hypothesis` is particularly valuable for data transformation functions. Unlike example-based tests (which test specific inputs chosen by the developer), `hypothesis` generates inputs automatically based on a strategy specification, explores edge cases the developer might not think of, and when a failure is found, reduces it to the minimal failing example. For a data transformation function that should preserve round-trip integrity (e.g., serialize then deserialize produces the original data), `hypothesis` can generate thousands of random inputs and verify the property holds for all of them:

```python
from hypothesis import given, strategies as st

@given(data=st.binary())
def test_serialize_roundtrip(data):
    """Serialized data should deserialize to the original."""
    serialized = serialize_record(data)
    deserialized = deserialize_record(serialized)
    assert deserialized == data

@given(text=st.text(alphabet=st.characters(blacklist_categories=('Cs',))))
def test_encoding_roundtrip(text):
    """Text should survive encode/decode with UTF-8."""
    encoded = text.encode('utf-8')
    decoded = encoded.decode('utf-8')
    assert decoded == text
```

The `hypothesis` strategies for text generation can be configured to include or exclude specific character categories (surrogates, control characters, private use area), making them ideal for encoding-aware testing. A strategy like `st.text(alphabet=st.characters(min_codepoint=0x80))` generates only non-ASCII text, targeting the exact scenarios that are most likely to reveal encoding bugs.

**Dual-interpreter CI** establishes the ongoing safety net. From Phase 1 forward, every change to the codebase is tested under both Python 2 and Python 3. Initially, Python 3 failures are informational -- the codebase is not expected to pass on Python 3 yet. As modules progress through conversion, the expectation tightens: converted modules must pass on both interpreters, and eventually Python 3 becomes the primary and Python 2 is informational-only.

Setting up dual-interpreter CI involves several components, each with practical considerations:

**CI matrix configuration.** The CI system must run the test suite under both Python 2.7 and the target Python 3 version. For CI systems that support matrix builds (GitHub Actions, GitLab CI, Azure Pipelines), this is a configuration addition. For Jenkins, it typically means adding a parallel stage. The Python 2 build should continue to use the existing test configuration; the Python 3 build should start as a copy and be tuned as needed.

**Local testing with tox.** Developers need to verify their changes against both interpreters before pushing. `tox` provides this capability with a simple configuration:

```ini
[tox]
envlist = py27, py311

[testenv]
deps =
    pytest
    -r requirements.txt
commands =
    pytest {posargs:tests/}
```

This ensures that `tox` runs the test suite under both Python 2.7 and Python 3.11, catching cross-interpreter issues before they reach CI.

**Test reporting.** CI output must clearly indicate which interpreter produced each failure. A test that fails on Py3 but passes on Py2 is a migration issue (expected during early phases). A test that fails on Py2 is a regression (unexpected after Phase 1). A test that fails on both interpreters is a general bug. Without clear interpreter labeling in the test output, developers waste time investigating failures in the wrong context.

**Allowed failures.** Initially, the Python 3 test run should be informational, not blocking. The codebase is not expected to pass on Py3 until modules complete Phase 2. Marking the Py3 run as "allowed failure" means that CI stays green on Py2 (which is the production interpreter) while providing visibility into Py3 progress. As modules complete Phase 2 and Phase 3, the allowed-failure scope narrows: converted modules should be tested strictly on Py3, while unconverted modules remain informational.

**Interpreter availability.** Both Python 2.7 and the target Python 3 version must be available in the CI environment. This may require installing Python 2.7 explicitly, as many modern CI base images no longer include it. Docker images with both interpreters, or tools like `pyenv` for managing multiple Python versions, can address this.

**Custom lint rules** codify the migration standards into automated checks. Phase 1 is when the progressive lint configuration is established: each module gets a lint configuration corresponding to its migration phase, and pre-commit hooks enforce the appropriate configuration. The lint rules are the automated encoding of the project's migration contracts.

The gate for Phase 1 is: CI is green on Python 2 with all future imports in place, test coverage on critical-path modules meets a defined threshold, and the lint baseline shows no regressions from the Phase 0 baseline. If adding future imports broke tests, those modules have been identified as high-risk and their issues have been triaged (either fixed, deferred to Phase 3, or accepted as risk with a waiver).

Rollback at this phase is trivial because all changes are additive: new `__future__` imports, new test files, new CI configuration, new lint rules. Reverting the commits restores the original state with no side effects.

### 7.3 Phase 2: Mechanical Conversion

Phase 2 applies automated syntax transformations to the codebase, module by module, in dependency order. This is the high-volume phase -- it handles the approximately 70-80% of changes that are pure syntax, low risk, and mechanically determinable. The goal is to get through the mechanical work as quickly and safely as possible, reserving human attention for the semantic work in Phase 3.

The transformations applied in Phase 2 are well-defined and unambiguous:

| Python 2 Pattern | Python 3 Equivalent | Notes |
|---|---|---|
| `print "hello"` | `print("hello")` | Already handled by Phase 1 future import |
| `except Exception, e:` | `except Exception as e:` | Syntax only |
| `dict.has_key(k)` | `k in dict` | Semantically identical |
| `dict.iteritems()` | `dict.items()` | Returns view, not list (see Phase 3) |
| `dict.itervalues()` | `dict.values()` | Returns view, not list (see Phase 3) |
| `dict.iterkeys()` | `dict.keys()` | Returns view, not list (see Phase 3) |
| `xrange(n)` | `range(n)` | Returns iterator, not list |
| `raw_input()` | `input()` | Old `input()` was `eval(raw_input())` |
| `unicode(s)` | `str(s)` | Type rename |
| `long(n)` | `int(n)` | Types unified |
| `` `x` `` | `repr(x)` | Syntax only |
| `x <> y` | `x != y` | Syntax only |
| `exec code` | `exec(code)` | Statement to function |
| `0777` | `0o777` | Octal literal syntax |
| `from foo import *` (relative) | `from .foo import *` | Explicit relative import |

A note on the `dict.iteritems()` to `dict.items()` conversion: in Python 2, `dict.items()` returns a list (copying all key-value pairs into a new list), while `dict.iteritems()` returns a lazy iterator. In Python 3, `dict.items()` returns a *view* (lazy, but also supports set operations like intersection). The mechanical conversion from `iteritems()` to `items()` is always correct, but the conversion from `dict.items()` (Py2, returns list) to `dict.items()` (Py3, returns view) may cause issues if the calling code modifies the dictionary during iteration or uses list-specific operations on the result. These cases belong in Phase 3.

Similarly, `raw_input()` to `input()` is syntactically simple but semantically significant. Python 2's `input()` function evaluated the user's input as a Python expression (`input("x: ")` with input `42` returns the integer `42`), which is a security risk. Python 2's `raw_input()` returned the input as a string, which is what Python 3's `input()` does. The conversion is correct as long as the codebase uses `raw_input()`. If any code uses Python 2's `input()` (the eval-ing version), the mechanical conversion would change its behavior from "evaluate as expression" to "return as string." The Phase 0 analysis should flag any use of Python 2's `input()` as a semantic concern.

The `unicode()` to `str()` conversion is similarly subtle. In Python 2, `unicode(x)` calls `x.__unicode__()` if available, or `x.__str__()` plus an implicit ASCII decode. In Python 3, `str(x)` calls `x.__str__()`. If a class has both `__str__` and `__unicode__` methods that return different values, the conversion changes which method is called. This is flagged for Phase 3 review.

Each conversion unit -- a single module or a cluster of tightly-coupled modules as determined by the Phase 0 analysis -- is converted and validated independently. The validation requires passing tests under both Python 2 and Python 3 before the next unit begins. This per-unit gating prevents error accumulation: if a conversion breaks something, it is caught immediately rather than buried under subsequent conversions.

The conversion ordering matters. Converting leaf modules first means that when you convert module A, all of A's dependencies have already been converted and are stable on both interpreters. This eliminates the cross-boundary type confusion discussed in Section 3.1. In practice, the conversion order is determined by the topological sort of the dependency graph, with clusters treated as single units.

**Build system and packaging changes** also belong in Phase 2 because they are mechanical and can be planned from the Phase 0 analysis.

Changes to address:

- **`setup.py`**: Update `python_requires` to reflect Python 3 compatibility. Add Trove classifiers for `Programming Language :: Python :: 3`. If targeting 3.12+, replace `distutils` imports with `setuptools` or `sysconfig`.
- **`pyproject.toml` / `setup.cfg`**: If the project has not yet adopted modern packaging, the migration is a reasonable time to make the transition, though it is not strictly required for the Py2-to-Py3 migration itself.
- **Dependency specifications**: `requirements.txt`, `Pipfile`, and similar files may reference Python-2-only versions of libraries. Each dependency must be checked for Py3 compatibility and updated to a version that supports both Py2 and Py3 (during the transition period) or Py3-only (after cutover).
- **Shell scripts and Makefiles**: Any script that invokes `python` by name may need to invoke `python3`, or the environment must be configured so that `python` resolves to Python 3. The `#!/usr/bin/env python` shebang line is ambiguous on systems where Python 2 is the default; `#!/usr/bin/env python3` is explicit.
- **Container images**: Base images must include Python 3. If the project uses multi-stage builds, all stages must be updated. If both interpreters are needed during the transition, the image must include both.
- **CI configuration**: Test matrices must include the target Python 3 version. The dual-interpreter CI from Phase 1 should already be in place.

The gate for Phase 2 is: each conversion unit passes its tests under both interpreters before the next unit begins, no lint regressions have been introduced, and the migration state tracker shows all units in the current batch as green.

Rollback is per-unit. Each conversion unit is its own commit or branch, and reverting a single unit does not affect others because conversions proceed in dependency order (leaf-first). A reverted leaf module returns to its pre-conversion state; nothing else depends on it having been converted.

### 7.3.1 The Mechanical Conversion Workflow

The per-unit conversion workflow is worth describing explicitly because its discipline is what makes Phase 2 safe at volume.

For each conversion unit (a module or cluster), the workflow is:

1. **Branch.** Create a branch from the current main. The branch name should encode the conversion unit: `migration/phase2/scada-modbus-reader` or similar.

2. **Convert.** Run the automated converter against the module. This applies all the mechanical transformations listed in the table above. The converter should produce a diff for review.

3. **Lint.** Run the Phase 2 lint rules against the converted code. Any remaining Py2 syntax that the converter missed should be flagged.

4. **Test on Python 2.** Run the module's tests (including characterization tests from Phase 1) under Python 2. They should still pass, because the conversions produce dual-compatible code (when combined with the `__future__` imports from Phase 1 and the `six`/`future` compatibility shims).

5. **Test on Python 3.** Run the same tests under Python 3. Syntax-only conversions should pass. If tests fail, investigate: is the failure a syntax issue (the converter missed something), a test issue (the test itself uses Py2 syntax), or a semantic issue (the failure indicates a bytes/string or other semantic problem that belongs in Phase 3)?

6. **Review.** A human reviews the diff. The review should be fast because the changes are mechanical and predictable, but it catches edge cases the converter missed: a `dict.items()` call inside a loop that modifies the dictionary, a `map()` result that is indexed later, or a `unicode()` call on an object whose `__unicode__` method does something non-trivial.

7. **Merge.** Merge the branch. Update the migration state tracker to record that the module has completed Phase 2.

8. **Verify.** Run the full test suite (not just the converted module's tests) on the main branch after the merge, to catch any cross-module interactions that the per-unit testing missed.

Steps 1 through 7 are per-unit and can be parallelized across multiple modules (as long as the dependency ordering is respected). Step 8 is per-merge and catches integration issues. If step 8 fails, the merge is reverted and the conversion unit is sent back for investigation.

This workflow produces approximately one commit per conversion unit, each with a clean diff that is reviewable, revertible, and documented. After Phase 2 completes, the git history shows a clear sequence of mechanical conversions, each self-contained.

### 7.4 Phase 3: Semantic Fixes

Phase 3 handles the changes that require human judgment. These are transformations where the correct fix depends on the developer's intent, not just syntax rules. This is the hardest phase, the phase where the most time will be spent, and the phase where the migration's quality is determined.

**The bytes/string divide** is the single most important semantic concern. For each boundary where data crosses between modules or between internal code and external systems, someone must determine: is this data semantically bytes (binary data that should remain as `bytes`) or text (human-readable content that should be `str`)? The answer is not always obvious, and it often requires understanding the data's origin, its destination, and everything that happens to it in between.

Section 4 described the data layer risks in detail -- the silent `b''` prefix in string formatting, the EBCDIC byte constant ambiguity, the pickle deserialization type changes. In Phase 3, these risks become concrete fix decisions. Each bytes/string boundary identified in Phase 0 now requires a resolution: where exactly in the call chain should `bytes` become `str` (or vice versa)?

For each boundary, the options typically are:

- **Decode at the source layer** (e.g., `serial_port.read(8).decode('ascii')` right at the protocol parser). This is cleanest -- it keeps the rest of the application in the text domain -- but requires knowing the encoding and trusting that the source data is consistently encoded.
- **Decode at the consumption layer** (e.g., decode in the formatting function that needs text). This localizes the fix but scatters `isinstance` checks and `.decode()` calls throughout the codebase.
- **Introduce an adapter** (e.g., a `DeviceIdentifier` class that always presents text). This is architecturally cleanest but requires more refactoring than a targeted fix.

The migration tooling should identify these boundaries, present the options, and explain the tradeoffs. It should not make the decision autonomously, because the wrong choice can create subtle bugs that pass all tests but produce incorrect output in production.

The decision framework for each bytes/string boundary is:

1. **Determine the data's origin.** Where does this data come from? A file? A network socket? A database? A hardware device? The origin often determines the initial type: network and file I/O produce bytes; database drivers typically produce text; hardware devices produce bytes.

2. **Determine the data's destination.** Where does this data go? To a display function (needs text)? To a file write (needs bytes in binary mode, text in text mode)? To a network socket (needs bytes)? To a database (needs text, usually)? The destination determines the required type.

3. **Determine the encoding.** If the data needs to cross from bytes to text (or vice versa), what encoding should be used? This information comes from protocol specifications, file format documentation, database configuration, or analysis of sample data.

4. **Determine the conversion point.** Where in the code should the decode (bytes to text) or encode (text to bytes) call be placed? The principle is: as close to the boundary as possible. Decode at the point of ingestion; encode at the point of output. This keeps the interior of the application in a single type domain.

5. **Document the decision.** Record the encoding, the conversion point, and the reasoning in the migration state tracker. This documentation is essential for maintainability and for auditing the migration's correctness.

**Dynamic language features** that changed semantically between Python 2 and Python 3 also require judgment. Unlike the syntax changes in Phase 2, these are cases where the automated tools cannot determine the correct fix because it depends on the developer's intent.

*Metaclass syntax.* The `__metaclass__` class attribute in Python 2 becomes the `metaclass=` keyword argument in the class definition. The syntactic transformation is straightforward (`class Foo(metaclass=Meta):` instead of `class Foo: __metaclass__ = Meta`), but metaclass code is often complex and the interaction between the metaclass and the class body may depend on Python-version-specific behavior. In particular, the `__prepare__` method (which allows metaclasses to customize the class namespace before the class body executes) is only available via the `metaclass=` syntax, not via `__metaclass__`. If a metaclass relies on `__prepare__`, the conversion is not just syntactic.

*Integer division.* The `/` operator performs floor division on integers in Python 2 but true division in Python 3. Phase 1's `from __future__ import division` already applied Python 3 semantics, so the immediate breakage should have been caught. However, code written after the future import was added may still use `/` where `//` was intended, and code that constructs integers dynamically (e.g., from configuration or user input) may have division operations that were not tested with the Phase 1 future import because the operand types were not known at test time.

*Comparison operators.* Python 2's `__cmp__` method was removed in Python 3. Classes that implement `__cmp__` must instead implement the rich comparison methods (`__lt__`, `__le__`, `__eq__`, `__ne__`, `__gt__`, `__ge__`). The `functools.total_ordering` decorator can reduce boilerplate by deriving the other methods from `__eq__` and one ordering method, but it has a performance cost: each comparison method call goes through an extra layer of Python function calls. For comparison-heavy code (sorting large datasets), this can be measurable.

*Boolean coercion.* Python 2's `__nonzero__` was renamed to `__bool__` in Python 3. The transformation is a simple rename, but automated tools sometimes miss it because `__nonzero__` is uncommon and some tools do not have a fixer for it.

*String representation.* Python 2 has `__str__` (returns bytes) and `__unicode__` (returns unicode). Python 3 has `__str__` (returns text) and `__bytes__` (returns bytes). The correct mapping is: Py2 `__unicode__` becomes Py3 `__str__`, and Py2 `__str__` becomes either Py3 `__bytes__` or is removed entirely. If the class used the `@python_2_unicode_compatible` decorator from Django or `six`, the conversion is handled by the decorator and the fix is to remove the decorator.

*Lazy iterators.* `map()`, `filter()`, and `zip()` return lists in Python 2 but iterators (lazy) in Python 3. `dict.keys()`, `.values()`, and `.items()` return lists in Python 2 but view objects in Python 3. Code that indexes the result (`dict.keys()[0]`), takes its `len()`, passes it to a function that needs a list, or iterates it multiple times must be updated. The correct fix depends on the usage:

- If the code iterates once and discards: the iterator/view is fine, no change needed.
- If the code indexes or slices: wrap in `list()`.
- If the code calls `len()`: wrap in `list()`, or use `len(dict)` directly for dict views.
- If the code modifies the collection during iteration: wrap in `list()` to take a snapshot (this was a bug in Py2 that happened to work for lists but fails for views).

*Sorting comparators.* `sorted()` and `list.sort()` no longer accept a `cmp` parameter. Code using custom comparison functions must be converted to use `key` functions, potentially via `functools.cmp_to_key()`. The conversion is not always straightforward because comparison functions and key functions express different things: a comparison function compares two items and returns their relative order, while a key function maps each item to a sort key that is compared using the default comparison.

For simple cases, the comparison function can be replaced with a direct key function:

```python
# Python 2
sorted(records, cmp=lambda a, b: cmp(a.priority, b.priority))

# Python 3 -- direct key function (preferred)
sorted(records, key=lambda r: r.priority)
```

For complex comparison logic that cannot be expressed as a key extraction, `functools.cmp_to_key` provides a mechanical conversion:

```python
# Python 2
sorted(records, cmp=complex_comparison_function)

# Python 3 -- cmp_to_key adapter
from functools import cmp_to_key
sorted(records, key=cmp_to_key(complex_comparison_function))
```

The `cmp_to_key` adapter creates a wrapper class for each element that implements `__lt__` by calling the original comparison function. This works correctly but has a performance cost: each comparison allocates a wrapper object and invokes a Python function call. For small lists, the cost is negligible. For sorting large datasets (millions of records), the overhead can be significant, and converting the comparison function to a key function (even if it requires creating a tuple or custom comparable object) may be worthwhile.

*Dictionary ordering.* Dictionaries are insertion-ordered as of Python 3.7 (and as an implementation detail in CPython 3.6). This affects migration in two directions, both of which are worth understanding even though neither typically causes test failures.

Code that depended on dictionary ordering in CPython 2 (which was deterministic per-run but not guaranteed by the language specification) will continue to work on Py3, though possibly with a different iteration order since the hash function and internal storage format changed. Code that worked around non-ordered dictionaries (`OrderedDict`, sorting keys before iteration, using lists of tuples instead of dicts) may now have unnecessary complexity that can be simplified. `OrderedDict` is not wrong in Py3 -- it is just redundant for most use cases. It does still differ from regular dicts in two ways: `OrderedDict` equality comparison considers insertion order, and it provides the `move_to_end()` method. If the code uses neither of these features, `OrderedDict` can be replaced with a regular dict during Phase 5 cleanup.

Tests that assert on dictionary string representations (`str(d) == "{'a': 1, 'b': 2}"`) may fail because the iteration order changed. These tests should be rewritten to compare dict contents directly (`assert d == {'a': 1, 'b': 2}`) rather than their string form.

**The type annotation opportunity.** If the migration is already touching every file in the codebase, adding type annotations during Phase 3 is a high-value investment. Type annotations are effectively Python-3-only in practice, so they cannot be added until a module has been converted. The bytes/string boundary analysis from Phase 0 provides particularly valuable type information: functions that accept `bytes` versus `str` should be annotated explicitly, creating machine-checkable documentation of the data contracts that are the most common source of migration bugs.

Adding type annotations enables `mypy` as a gate checker. A `mypy`-clean module provides substantially stronger guarantees than a module with only runtime tests, because `mypy` checks all code paths, including error-handling branches and edge cases that may not be exercised by the test suite. The combination of runtime tests (behavioral correctness) and static type checking (type correctness) provides defense in depth against the two major categories of migration bugs: behavioral changes that existing tests would catch, and type errors that only surface in code paths not exercised by the test suite.

The practical approach to type annotation during migration is gradual:

1. Start with function signatures on public interfaces. These are the boundaries where type confusion is most dangerous, and they are the easiest annotations to write because the function's usage across the codebase constrains its type.

2. Add `bytes` vs `str` annotations everywhere the Phase 0 data layer analysis identified a boundary. These annotations serve as executable documentation of the encoding decisions made in Phase 3. A function annotated as `def parse_record(data: bytes) -> dict[str, str]` documents that it accepts binary data and returns text fields.

3. Use `Union[str, bytes]` sparingly and flag it as technical debt. A function that accepts both `str` and `bytes` is a function whose encoding contract is unclear. It may be correct (e.g., a utility that handles both text and binary logging), but it should be a conscious choice, not a leftover ambiguity.

4. Configure `mypy` progressively: start with `--ignore-missing-imports` (third-party libraries may lack type stubs), add `--check-untyped-defs` (check function bodies even without annotations), and eventually reach `--strict` (everything annotated, everything checked).

### 7.4.1 Library Replacements

Library replacement is a discrete sub-problem within Phase 3 that deserves its own discussion. The Python 2-to-3 migration renamed, reorganized, or removed a substantial number of standard library modules. Third-party libraries may also require replacement.

Standard library renames are mechanical:

| Python 2 Module | Python 3 Equivalent | Notes |
|---|---|---|
| `ConfigParser` | `configparser` | Case change only |
| `Queue` | `queue` | Case change only |
| `cPickle` | `pickle` | Py3 auto-selects C implementation |
| `cStringIO` | `io.StringIO` / `io.BytesIO` | Split by type |
| `HTMLParser` | `html.parser` | Package restructure |
| `commands` | `subprocess` | API change -- not just a rename |
| `thread` | `_thread` or `threading` | `threading` preferred |
| `urllib` + `urllib2` + `urlparse` | `urllib.parse`, `urllib.request`, `urllib.error` | Reorganized into submodules |
| `httplib` | `http.client` | Package restructure |
| `Cookie` | `http.cookies` | Package restructure |
| `repr` | `reprlib` | Renamed |

The `urllib` family is the most disruptive because it went from three separate modules to three submodules of a single package, and the function names and call signatures changed. Code using `urllib2.urlopen()` becomes `urllib.request.urlopen()`, but code using `urllib2.Request()` becomes `urllib.request.Request()` with potential changes to how data and headers are passed. For complex `urllib2` usage, replacing with the `requests` library may be simpler than converting to the new `urllib`.

For modules removed in Python 3.12 (`cgi`, `telnetlib`, `uu`, etc.), the replacement is not a rename but a genuine migration to a different library or approach. `cgi.FieldStorage` has no direct replacement in the stdlib; web applications should use a framework (Flask, Django, FastAPI) or the `multipart` library. `telnetlib` can be replaced by `telnetlib3` (a third-party library) or by switching to `paramiko` for SSH-based automation. `uu` (uuencoding) can be replaced by `base64` for most use cases.

The gate for Phase 3 is: the full test suite passes under Python 3, integration tests pass, no encoding errors appear in logs during test runs, all bytes/string boundaries have been explicitly annotated, and type hints are present on all public interfaces.

Rollback at this phase is more complex than Phase 2 because semantic fixes are interleaved and may depend on each other. A bytes/string fix in module A may be predicated on a bytes/string fix in module B that A depends on. Each semantic fix should be a separate, well-documented commit. The migration state tracker records dependencies between fixes so that rollback order is clear.

### 7.5 Phase 4: Verification and Hardening

Phase 4 proves that the migration is correct. The goal is not to find more issues to fix (that was Phase 3) but to demonstrate, with evidence, that the converted code behaves identically to the original -- or that any behavioral differences are understood, documented, and accepted.

**Behavioral diff generation** is the primary verification technique. The same inputs are run through both the Python 2 and Python 3 code paths, and every output is compared: return values, standard output, standard error, files written, network requests made, database queries executed. The comparison must account for expected differences and flag unexpected ones.

Expected differences between Py2 and Py3 output include:

- Dictionary `repr()` format may differ (ordering changed, `u''` prefix removed from string keys).
- Exception message text may differ.
- `str` objects are displayed without the `u''` prefix that Py2's `unicode` type had.
- Numeric precision in floating-point output may differ slightly.
- Iteration order of sets is not guaranteed and may differ between runs, let alone between interpreters.

Unexpected differences -- any change in the *content* of outputs, as opposed to their *format* -- are potential migration bugs. Each unexpected difference should be investigated, categorized (migration bug, test sensitivity to formatting, genuine behavior change), and either fixed or documented.

This is distinct from unit testing. Unit tests verify that the code meets its specification. Behavioral diff testing verifies that the migration preserved the code's behavior, including behaviors that may not be part of any specification. For a codebase where the original developers are unavailable and the specification is incomplete or absent, behavioral equivalence is the strongest correctness guarantee available.

The behavioral diff process in practice works as follows. For each test case (or for each real-world input scenario), the test harness:

1. Runs the test under Python 2, capturing all outputs: function return values, stdout, stderr, files created or modified, database rows written, network requests sent.
2. Runs the same test under Python 3, capturing the same outputs.
3. Compares the outputs, applying "expected difference" filters that strip known formatting changes (dictionary repr format, unicode string prefix, etc.).
4. Reports any remaining differences as potential migration bugs.

For simple function-level testing, this can be implemented as a pytest fixture:

```python
import subprocess
import json

def run_under_interpreter(interpreter, script, args):
    """Run a script under a specific Python interpreter and capture output."""
    result = subprocess.run(
        [interpreter, script] + args,
        capture_output=True,
        text=True,
        timeout=60
    )
    return {
        'stdout': result.stdout,
        'stderr': result.stderr,
        'returncode': result.returncode,
    }

def test_behavioral_equivalence():
    py2_result = run_under_interpreter('python2', 'process_data.py', ['input.dat'])
    py3_result = run_under_interpreter('python3', 'process_data.py', ['input.dat'])

    # Apply expected-difference filters
    py2_stdout = normalize_output(py2_result['stdout'])
    py3_stdout = normalize_output(py3_result['stdout'])

    assert py2_stdout == py3_stdout, (
        f"Behavioral diff detected:\n"
        f"Py2: {py2_stdout[:200]}\n"
        f"Py3: {py3_stdout[:200]}"
    )
    assert py2_result['returncode'] == py3_result['returncode']
```

For integration testing of services, the approach extends to HTTP request/response comparison, database state comparison, and file output comparison. The key engineering challenge is the `normalize_output` function, which must strip expected differences without masking real bugs. This function evolves over the course of Phase 4 as new expected differences are identified and documented.

**Performance benchmarking** catches regressions that correctness testing misses. Python 3 is not uniformly faster or slower than Python 2; the characteristics differ by operation. String operations are generally faster in Python 3 because Unicode is the native type and there are no implicit encoding conversions. Integer arithmetic changed when `int` and `long` were unified. I/O may be slower if Python 3's default UTF-8 encoding adds decode overhead on data that Python 2 passed through as bytes.

Benchmarks should be designed with statistical rigor: multiple runs (at least 10, ideally 30+), confidence intervals, outlier detection, and warm-up runs to account for JIT effects (relevant for Python 3.13+) and import caching. The benchmark should measure:

- **Wall-clock time**: The most relevant metric for user-facing performance, but the noisiest. Background processes, system load, and I/O contention all affect wall-clock time.
- **CPU time**: Isolates Python execution time from I/O wait and system overhead. More stable than wall-clock time for CPU-bound operations.
- **Memory usage**: Both peak allocation and steady-state usage. Python 3's string representation can use more memory for non-ASCII text (it uses 1, 2, or 4 bytes per character depending on the content, versus Python 2's `unicode` type, which used a fixed 2 bytes (UCS-2) or 4 bytes (UCS-4) per character depending on the build's `--enable-unicode` setting).
- **I/O operations**: Relevant for codebases with heavy file or network I/O. Python 3's default UTF-8 encoding adds decode overhead on read and encode overhead on write that Python 2's byte-pass-through did not have.

A performance regression that exceeds the acceptable threshold (typically 10-15% for most applications, tighter for latency-sensitive services) should be investigated before proceeding. Common migration-related performance issues include unnecessary `list()` wrapping of iterators, redundant `encode()`/`decode()` round-trips, and `isinstance()` checks added for bytes/str compatibility that are no longer needed on Py3-only code.

**Encoding stress testing** goes beyond normal test coverage by deliberately using adversarial inputs designed to trigger encoding failures that normal testing misses. Test vectors should include:

- BOM (Byte Order Mark) markers at the start of files. UTF-8 files sometimes have a BOM (`\xef\xbb\xbf`), which some parsers strip and some do not. Python 3's `utf-8-sig` codec handles BOM-prefixed UTF-8; the plain `utf-8` codec does not.
- Surrogate pairs (U+D800 through U+DFFF). These are technically invalid in UTF-8 but appear in data produced by some systems (notably, certain Windows APIs encode characters above U+FFFF as surrogate pairs in UTF-16 and some transcoding tools preserve them incorrectly as surrogate code points in UTF-8).
- Null bytes embedded in text data. Python handles null bytes in strings, but many C extensions, file formats, and external tools treat null as a string terminator.
- Mixed encodings within a single data stream (a file with UTF-8 headers and Latin-1 body data, or a database with UTF-8 in some columns and Latin-1 in others).
- The "mojibake" scenario: data that was double-encoded (e.g., UTF-8 text encoded as Latin-1, then re-encoded as UTF-8, producing garbled multi-byte sequences).
- EBCDIC data with characters that have no ASCII equivalent.
- Binary data that coincidentally contains valid UTF-8 sequences, which could cause a codec to "succeed" on data that should not be decoded at all.

Each data ingestion path should be tested with each relevant encoding vector. The goal is to ensure that no plausible production data can trigger an unhandled encoding error.

The encoding stress test matrix can be large. If the codebase has 30 data ingestion paths and 10 encoding vectors, that is 300 test combinations. Not all combinations are relevant (EBCDIC vectors are only relevant for mainframe data paths), but the relevant subset should be tested exhaustively. The test results should be documented as a first-class artifact -- a matrix where each row is a data path, each column is an encoding vector, and each cell is PASS, FAIL, or N/A (not applicable). A completed matrix with all relevant cells showing PASS is a strong indicator that the data layer migration is correct.

**Migration completeness checking** scans the entire codebase for any remaining artifacts from the migration process. This is a systematic sweep that looks for:

- Residual Python 2 syntax that was missed or deferred during Phase 2.
- `six` or `future` library usage that should have been resolved to direct Py3 code in Phase 3.
- `# type: ignore` comments that were added during the migration as workarounds and may no longer be needed.
- `TODO`, `FIXME`, or `HACK` comments added during conversion that indicate deferred work.
- `__future__` imports that are unnecessary on Python 3 (they are harmless but indicate the cleanup is incomplete).
- `sys.version_info` conditional blocks that can be simplified by removing the Py2 branch.
- Unused imports that were added for Py2/Py3 compatibility.
- `isinstance(x, bytes)` or `isinstance(x, str)` checks that were added as defensive measures during migration and may now be unnecessary if the type contracts are properly established.

Each finding should be categorized: "must fix before cutover" (remaining Py2 syntax, broken compatibility shims), "should fix before cutover" (unnecessary `six` usage, redundant isinstance checks), and "can fix after cutover" (`__future__` imports, cosmetic TODOs). The completeness checker's output feeds the Phase 5 cleanup work.

### 7.5.1 When Verification Fails

Phase 4 verification will almost certainly reveal issues in the first pass. The question is not whether issues will be found but how many and how severe. The response to verification failures follows a triage process:

**Behavioral diff is cosmetic.** The output differs in format but not in content. Dictionary repr changed, exception messages are worded differently, float precision changed in the last decimal place. These are documented as "expected differences" and excluded from future diff comparisons.

**Behavioral diff is a known semantic change.** The Py2 code was relying on implicit behavior that Py3 handles differently, and the change is correct. For example, Py2 code that accidentally relied on `int / int` floor division, and the Py3 code now performs true division, producing a different (correct) result. These should be accompanied by a test update that documents the intentional behavior change.

**Behavioral diff is a migration bug.** The Py3 code does something wrong that the Py2 code did right. The module is rolled back to Phase 3, the specific issue is identified and fixed, and the module re-enters Phase 4 for verification. The rollback should be tracked in the migration state, including what the bug was and how it was fixed, so that similar issues in other modules can be checked proactively.

**Performance regression is significant.** A code path is measurably slower under Py3. The first step is to determine whether the regression is inherent to Py3 (unlikely for most operations) or a consequence of the migration (e.g., an unnecessary `list()` wrapping a dict view that is only iterated once, or a decode/encode round-trip that could be eliminated). Most migration-related performance regressions are fixable. Inherent Py3 performance differences (rare) should be documented and accepted.

**Encoding stress test fails.** A data path cannot handle a specific encoding input without error. This indicates a missing or incorrect `decode()` call, a wrong codec, or a data path that was classified as text but is actually bytes (or vice versa). The module goes back to Phase 3 for the specific boundary fix. The encoding stress test failure is often the most valuable kind of Phase 4 finding, because it identifies exactly the production data scenario that would have caused a runtime error after cutover.

The gate for Phase 4 is: zero unexpected behavioral diffs between Python 2 and Python 3, no performance regressions beyond accepted thresholds, encoding stress tests pass for all data paths, and the completeness checker reports 100% (or all remaining items have documented waivers). If verification reveals issues, the affected modules are rolled back to Phase 3 for additional semantic work.

### 7.6 Phase 5: Cutover and Cleanup

Phase 5 is the transition from "the code works on both interpreters" to "the code runs on Python 3 in production." For batch-processing systems, this may be as simple as changing the interpreter path in the deployment configuration or cron job. For production services that handle live traffic, a more careful approach is warranted.

**Canary deployment** is the established pattern for production service migration. Rather than switching all traffic to Python 3 at once, you run both interpreters in parallel and route an increasing percentage of traffic to Python 3. Instagram used request-level feature flags, routing individual HTTP requests to either the Python 2 or Python 3 backend and comparing the responses for correctness. A typical ramp schedule is:

1. **1%** -- Smoke test. Verify that the Py3 backend starts, handles requests, and produces output. Watch error rates for any spike.
2. **5%** -- Early validation. Compare Py3 responses against Py2 responses for the same requests. Investigate any differences.
3. **25%** -- Broader validation. Look for performance differences, edge cases triggered by diverse traffic, and encoding issues with real-world data.
4. **50%** -- Sustained load. Verify stability under production-level traffic. Run for a defined period (e.g., 48 hours) before proceeding.
5. **100%** -- Full traffic on Py3. Py2 remains deployable as a rollback option.

Each step should be held for a defined observation period before proceeding. The observation period should be long enough to capture at least one cycle of the codebase's typical workload patterns: if the system processes daily reports, hold each step for at least 24 hours; if it processes monthly summaries, the soak period for 100% should include a month-end cycle.

For non-service codebases -- batch processors, data pipelines, CLI tools, scheduled jobs -- the canary pattern adapts. Instead of traffic routing, you run both interpreters on the same input and compare outputs:

```bash
# Run the batch job under both interpreters
python2 /opt/app/process_daily.py --input /data/today/ --output /tmp/py2_output/
python3 /opt/app/process_daily.py --input /data/today/ --output /tmp/py3_output/

# Compare outputs
diff -r /tmp/py2_output/ /tmp/py3_output/
```

For data pipelines, you can run the Py3 version in "shadow mode" -- processing the same input as the Py2 version but writing to a separate output location. Once the shadow outputs match the production outputs for a sufficient period, you switch production to Py3.

For CLI tools, the canary is simpler: deploy the Py3 version alongside the Py2 version with a different name (`tool3` vs `tool`), let users opt in, collect feedback, and eventually alias `tool` to the Py3 version.

The canary deployment infrastructure needs:

- Parallel deployment configurations: both interpreters running simultaneously, with identical code, data, and configuration except for the interpreter.
- Traffic routing: load balancer configuration that routes a configurable percentage to each backend. Feature flags are an alternative for request-level routing.
- Output comparison: middleware or sidecar that captures Py2 and Py3 responses for the same inputs and flags differences.
- Monitoring dashboards: error rates, latency (p50, p95, p99), and throughput per interpreter. A latency spike or error rate increase on the Py3 backend is a signal to pause the ramp.
- Automatic rollback triggers: if the Py3 error rate exceeds a configurable threshold (e.g., 2x the Py2 error rate), route all traffic back to Py2 automatically.

After the ramp reaches 100% and the soak period completes without issues, the cleanup phase begins.

**Compatibility shim removal** strips out all the dual-compatibility code that was added during the migration. This includes:

- `from __future__ import ...` statements (unnecessary on Py3, but harmless; removal is cosmetic).
- `six` library usage, replaced with direct Py3 equivalents (`six.moves.urllib` becomes `urllib.request`, `six.text_type` becomes `str`, etc.).
- `python-future` library usage, replaced with direct Py3 equivalents.
- `sys.version_info` conditional blocks, simplified by removing the Py2 branch and keeping only the Py3 code.
- `try: from X import Y / except ImportError: from Z import Y` blocks that handle Py2/Py3 import differences, replaced with the Py3 import.

`pyupgrade --py3X-plus` (where X is the target minor version) automates much of this cleanup. It rewrites code to use idioms that are only available on the target version and later: `list[str]` instead of `List[str]` (3.9+), native `open()` encoding parameter instead of `io.open()`, direct `str` and `bytes` instead of `six.text_type` and `six.binary_type`. The transformations are safe and mechanical, and the resulting code is both cleaner and slightly faster (removing the `six`/`future` function call overhead).

**Dead code detection** identifies code that was only reachable under Python 2 and is now unreachable:

- `if sys.version_info < (3, 0):` blocks and their contents.
- Utility functions that were only called from Py2 compatibility code.
- Modules that were imported solely for Py2 support.
- `__future__` import handling code (code that conditionally imported `__future__` or checked for the presence of future imports).

Dead code should be flagged for human review rather than auto-removed. Dead code detection is inherently approximate: static analysis cannot fully account for dynamic dispatch, `getattr()`, `importlib`, plugin systems, or other dynamic access patterns. A function that appears dead may be called through:

- String-based dispatch: `getattr(module, function_name)()` where `function_name` comes from configuration.
- Plugin registration: a function registered with a plugin system that invokes it by name.
- Entry points: functions referenced in `setup.py` or `pyproject.toml` console_scripts or gui_scripts.
- Tests: functions that are only called from test code, which may not be in the main source tree.
- External callers: functions that are part of a library's public API and may be called by code outside the repository.

Flagging dead code with confidence scores helps reviewers focus their attention. A confidence scheme might look like:

- **High confidence** (safe to remove): No call sites found anywhere in the repository, not referenced in configuration, not part of a public API, not referenced in tests. Example: a utility function in a `_py2_compat.py` file that is imported by no one.
- **Medium confidence** (likely safe, verify before removing): Only called from other dead code, or only called inside `if sys.version_info < (3, 0):` blocks. Example: a `__cmp__` method on a class that also has `__lt__` and `__eq__`.
- **Low confidence** (flag but do not recommend removal): Found in a module that is imported dynamically, part of a class that may be subclassed externally, or has a generic name that could match a framework convention. Example: a `handle()` method that might be invoked by a web framework's URL dispatcher.

The gate for Phase 5 is: production has been running on Python 3 for a defined soak period with no issues, all stakeholders have signed off on the cutover, and the compatibility shim removal has been completed. After the soak period, the Python 2 deployment configuration is retired and rollback to Python 2 is no longer possible. This is the point of no return, and it should be treated as such -- the soak period should be long enough that low-frequency code paths (end-of-month reports, quarterly aggregations, annual batch jobs, disaster recovery procedures) have had at least one natural execution cycle.


## 8. Orchestration

Three cross-cutting concerns span all phases and provide the coordination layer that holds the migration together. These are not phase-specific activities but ongoing processes that operate throughout the project's duration.

### 8.1 Migration State Tracking

A large-scale migration involves hundreds of modules progressing through six phases at different rates. Some modules advance quickly (well-tested, pure syntax issues, no data layer concerns). Others are blocked for weeks on a single bytes/string decision that requires understanding the data's provenance. Without a persistent, authoritative record of each module's status, the project quickly becomes opaque.

The migration state tracker maintains a record for every module in the codebase. Each record includes:

- The module's current phase (0 through 5).
- The history of phase transitions, with timestamps and the evidence that supported each transition (gate check results).
- Risk factors identified in Phase 0 (binary protocol handling, EBCDIC data, no existing tests, C extension dependency, etc.).
- Current blockers (dependencies not yet converted, pending human decisions, failing tests).
- A log of decisions made during conversion, with rationale. This is particularly important in codebases where the original developers are unavailable. When a future maintainer asks "why was this decoded as CP-1047 instead of CP-500?", the answer should be in the state tracker, not lost in someone's memory or a Slack conversation.

The state tracker also enforces dependency constraints. A module cannot advance to Phase 3 if a module it depends on is still in Phase 2, because the dependency's bytes/string semantics may not yet be stable. The tracker knows the dependency graph (from the Phase 0 analysis) and blocks premature advancement automatically.

Aggregate metrics from the state tracker provide stakeholder visibility:

- Percentage of modules at each phase, presented as a dashboard or burndown chart.
- A risk heatmap showing which modules are high-risk and their current status.
- Projected completion dates based on current velocity (modules per week through each phase).
- Blockers and their impact (which modules are blocked, and how many downstream modules are blocked as a result).

The state tracker's data model should be simple and inspectable. A JSON file checked into the repository is preferable to a separate database, because it is versioned alongside the code, requires no infrastructure, and can be read by any tool. The tradeoff is that concurrent updates require merge conflict resolution, but in practice the state tracker is updated by skills (which operate sequentially on each module) and by humans (who update blockers and decisions), not by parallel automated processes.

The decision log deserves particular emphasis. In a migration of a legacy codebase where the original developers are unavailable, every semantic decision is an act of interpretation: "this data appears to be EBCDIC based on byte patterns in sample files, so we decode with CP-500." If that interpretation is wrong, someone needs to be able to find it, understand the evidence that led to it, and correct it. If the interpretation is right but looks surprising to a future maintainer, the rationale prevents unnecessary re-investigation.

A good decision log entry contains:

```json
{
    "date": "2026-03-15",
    "module": "src.mainframe.record_parser",
    "phase": 3,
    "decision": "Decode mainframe records using cp1047 (EBCDIC Open Systems)",
    "alternatives_considered": [
        "cp500 (EBCDIC International) -- rejected because sample data contains Unix newlines (0x15 in cp1047, 0x25 in cp500)",
        "Manual byte translation -- rejected because codecs module handles this correctly"
    ],
    "evidence": "Examined 50 sample records from data/mainframe_exports/. Byte 0x15 appears at record boundaries, which is the newline character in cp1047 but the NL control character in cp500. Records decode cleanly with cp1047; cp500 produces garbled output for records containing newlines.",
    "decided_by": "jsmith",
    "reversible": true,
    "reversal_impact": "Change codec in record_parser.py line 47 and re-run Phase 3 encoding tests"
}
```

This level of documentation may seem excessive for an individual decision, but in a migration with hundreds of such decisions across dozens of modules, the aggregate documentation is what makes the project auditable and the results trustworthy.

### 8.2 Rollback Planning

The ability to undo a change is a prerequisite for making the change confidently. Each phase has a different rollback profile, and the rollback strategy must be planned explicitly rather than assumed. "We can always revert" is not a rollback plan -- it is an aspiration. A rollback plan specifies exactly what gets reverted, in what order, and how to verify that the revert was successful.

**Phase 1 rollback** is trivial. All Phase 1 changes are additive: new `__future__` imports, new characterization tests, new CI configuration. Reverting the commits restores the original state with no side effects. The tests added in Phase 1 are characterization tests that document existing behavior; removing them does not change the code's behavior, only the coverage.

**Phase 2 rollback** operates per conversion unit. Because conversions proceed in dependency order (leaf modules first), reverting a single unit does not affect units that were converted before it (those are further from the core and do not depend on the reverted unit). Each conversion unit is its own commit or branch, so the revert is a `git revert` of that commit. After the revert, the module is back at Phase 1, and its tests should pass on Python 2 (they did before conversion).

**Phase 3 rollback** is more complex. Semantic fixes may depend on each other: a bytes/string fix in module A may be predicated on a bytes/string fix in module B that A depends on. If you revert the fix in B, A may break. The state tracker records these dependencies (as edges in a fix-dependency graph), so rollback must proceed in reverse dependency order: revert A first, then B. Each semantic fix should be a separate commit with a message that documents what it depends on and what depends on it.

**Phase 4** has no code changes to roll back; it is a verification phase. If verification fails for a module, the response is to roll that module back to Phase 3 for additional semantic work. The gate checker records which criteria failed and why, providing guidance for the Phase 3 rework.

**Phase 5 rollback** means reverting to the Python 2 deployment. During the canary soak period, the Python 2 deployment configuration must remain deployable -- not just the code, but the infrastructure configuration, container images, and dependency specifications. This requires maintaining the Py2 deployment pipeline and not dismantling it until the soak period is over. After the soak period ends and compatibility shims are removed (which changes the code so it no longer runs on Py2), rollback is no longer feasible.

Rollback plans should be tested periodically. At a minimum, test the Phase 2 rollback procedure after the first few conversion units to verify that the per-unit revert process works as expected. Test the Phase 3 rollback procedure after the first semantic fix to verify that the dependency tracking is correct. It is not sufficient to believe that rollback is possible; the procedure must be executed in a test environment to verify that it actually works.

A practical rollback test for Phase 2 looks like:

1. Convert a module (apply the Phase 2 automated converter, run tests, verify green on both interpreters).
2. Merge the conversion commit.
3. Revert the commit: `git revert <commit-hash>`.
4. Run the full test suite under Python 2. It should pass (the module is back at Phase 1).
5. Run the full test suite under Python 3 for previously-converted modules. They should still pass (the revert does not affect them).
6. Verify the migration state tracker correctly shows the module back at Phase 1.

If any step fails, the rollback process has a gap that needs to be fixed before more conversions proceed. Common issues include:

- The conversion commit modified files outside the conversion unit (a shared `__init__.py`, for instance). The revert of the conversion commit also reverts the shared file change, which may affect other conversion units.
- The test suite has test-ordering dependencies: tests for converted modules that run before the reverted module's tests may set up state that the reverted module's tests depend on (or vice versa).
- The migration state tracker was not updated to reflect the revert, leading to a stale state that blocks or incorrectly enables other modules.

Discovering these issues early (when one module has been converted) is far better than discovering them late (when 50 modules have been converted and the rollback is critical).

The rollback test should be incorporated into the project's standard operating procedure: after the first 3-5 conversion units in Phase 2, perform a full rollback test. After the first semantic fix in Phase 3, perform a Phase 3 rollback test. These tests take time but they validate the safety net that enables the rest of the migration to proceed with confidence.

### 8.3 Gate Checking

Gates are the decision points between phases. They are explicitly about stopping and requiring judgment before proceeding. The purpose of a gate is not to add process for its own sake but to create a decision point where the evidence is assembled and a human (or in some cases, an automated policy) determines whether it is sufficient to proceed.

A gate check runs all the criteria for the current phase, produces a pass/fail result for each criterion with supporting evidence, and blocks advancement if any criterion is not met. The evidence is concrete: test suite pass rates, lint compliance reports, coverage measurements, encoding test results, performance benchmark data. The gate check does not interpret the evidence -- it presents it. The decision to proceed is made by the project lead or the responsible engineer.

Gate criteria should be configurable. The defaults in PLAN.md are reasonable starting points, but different organizations and codebases have different risk tolerances. A codebase with comprehensive existing tests may be able to use a lower coverage threshold for Phase 1 (the existing tests already provide the safety net). A codebase running safety-critical systems may require a higher behavioral-diff threshold for Phase 4 (even cosmetic differences might indicate a deeper issue).

Gates also support waivers: criteria that have been explicitly accepted as risk by stakeholders. A waiver is not the same as ignoring a failed criterion. A waiver is a documented decision: "we acknowledge that module X does not meet the coverage threshold, and we accept the risk because the module is scheduled for replacement in Q3 and full coverage is not worth the investment." Waivers are tracked in the migration state alongside other decisions, providing an audit trail for why certain modules were advanced despite not meeting all criteria.

The gate checker should integrate with CI so that pull requests automatically trigger gate checks for the affected modules. A pull request that modifies a module at Phase 2 should automatically run the Phase 2 gate checks (does the code pass tests on both interpreters? are there any lint regressions?) as part of the PR review process. This makes gate checking a normal part of the development workflow rather than a separate ceremony.

### 8.4 Orchestrating Concurrent Work

In a multi-developer migration, multiple modules will be in active conversion simultaneously. The orchestration layer must handle this concurrency without creating conflicts.

The dependency ordering provides the primary concurrency control. Two modules can be converted in parallel if neither depends on the other (directly or transitively). The conversion unit planner identifies these parallelizable groups, and the migration state tracker enforces the ordering constraints.

However, there are subtleties that simple dependency ordering does not capture:

**Shared utility modules.** A utility module used by many other modules is a serialization point: it must be converted before anything that depends on it, and many modules depend on it. If the utility module has bytes/string boundary issues (which utility modules often do, because they are generic), its Phase 3 resolution blocks a large fraction of the codebase from proceeding past Phase 2. These "gateway" modules should be identified in Phase 0 and prioritized for early conversion.

**Cross-cutting concerns.** Some changes affect many modules simultaneously. A decision about encoding conventions (e.g., "all file I/O in the codebase uses UTF-8 unless explicitly specified otherwise") affects every module that reads or writes files. This decision should be made once, documented in the migration state, and applied consistently. If different developers make different encoding assumptions in different modules, the resulting codebase will be inconsistent.

**Merge conflict management.** When two developers convert modules in parallel and both touch a shared file (a package `__init__.py`, a configuration file, a shared constants module), the merges can conflict. The conversion unit planner should identify shared files and either assign them to a single conversion unit or schedule their conversion in a single pass. In practice, the most common conflict source is the migration state tracker itself; serializing updates to the tracker (e.g., through a CI bot that updates the tracker on each merge) avoids this.

**Communication overhead.** Each semantic decision in Phase 3 potentially affects other modules. If developer A decides that a utility function returns `bytes`, developer B (who is converting a module that calls that function) needs to know. The migration state tracker's decision log is the communication mechanism: decisions are recorded centrally, and developers check the log for their dependencies before making decisions about their own modules. This is more reliable than verbal communication or Slack messages, which are ephemeral and easy to miss.


## 9. Implementation Priority

Not all 26 skills need to be built before the migration can begin. The skills have a natural dependency order -- some skills produce output that other skills consume -- and the implementation should follow that order. Building skills that are not yet needed wastes effort that could be spent on the migration itself.

### Tier 1: Foundation (Build First)

The first tier contains the four skills that everything else depends on.

The **Migration State Tracker** comes first because all other skills read from and write to it. It defines the data model (what a module state record looks like, how decisions are logged, how dependencies are tracked) that other skills produce and consume. Without it, there is no shared understanding of the project state, and coordination between skills is ad-hoc at best.

The **Codebase Analyzer** comes next because its output -- the dependency graph, the Py2-ism inventory, the risk categorization, the version compatibility matrix -- is the input to nearly every subsequent skill. You cannot plan conversions without the dependency structure, generate targeted tests without the risk profile, or make target-version decisions without the compatibility analysis.

The **Data Format Analyzer** addresses the highest-risk area of the migration. Given the variety of data sources in a typical legacy codebase -- files in multiple encodings, databases with implicit encoding assumptions, binary protocols, serialized objects in multiple formats -- a dedicated analysis of the data layer is critical for planning Phase 3 work accurately and avoiding surprises.

The **Gate Checker** enforces discipline from day one. Without automated gate enforcement, phase transitions are governed by human judgment, which under schedule pressure tends toward optimism ("the tests mostly pass, let's move on"). The gate checker provides an objective, repeatable assessment that supports good decision-making.

### Tier 2: Enable Phase 1 (Build Next)

The second tier enables Phase 1 work to begin while the Phase 0 analysis is still being refined.

The **Lint Baseline Generator** runs existing linters against the codebase and produces the baseline for measuring progress. This is a quick win with high informational value -- it quantifies the scope of mechanical work and identifies the most common issue categories.

The **Future Imports Injector** makes the first real code changes. Its output -- the list of modules that broke when future imports were added, particularly `unicode_literals` -- is directly useful for risk assessment and for prioritizing test generation.

The **Test Scaffold Generator** builds the safety net that all subsequent conversion work relies on. The encoding-aware test generation is particularly valuable because it creates tests that catch the most dangerous class of migration bugs before they reach Phase 3.

The **Conversion Unit Planner** takes the Phase 0 dependency graph and produces the ordered conversion plan. This plan determines the work schedule for Phase 2 and should be available before Phase 2 begins.

### Tier 3: Core Conversion

The third tier contains the skills that perform the actual migration work.

The **Automated Converter** is the workhorse of Phase 2, handling mechanical syntax transformations at volume.

The **Bytes/String Boundary Fixer** is the most important Phase 3 skill, handling the highest-risk semantic problem in the migration.

The **Library Replacement Advisor** handles standard library and third-party library migrations, which are necessary for Py3 compatibility.

The **Dynamic Pattern Resolver** handles the remaining semantic changes: metaclasses, integer division, comparison operators, iterator changes, and similar.

### Tier 4: Quality Assurance

The fourth tier provides verification capabilities. These skills are not needed until modules begin reaching Phase 4, so they can be built while Tier 3 skills are executing against Phase 2 and Phase 3 work.

The **Behavioral Diff Generator** provides the primary verification mechanism.

The **Encoding Stress Tester** validates the data layer migration with adversarial inputs.

The **Migration Completeness Checker** ensures nothing was missed or deferred without documentation.

The **Performance Benchmarker** catches performance regressions.

### Tier 5: Polish and Cutover

The remaining skills are valuable but can be built on demand or handled manually in the interim. The Serialization Boundary Detector, C Extension Flagger, CI Dual-Interpreter Configurator, Custom Lint Rule Generator, Build System Updater, Type Annotation Adder, Canary Deployment Planner, Compatibility Shim Remover, Dead Code Detector, and Rollback Plan Generator all fall into this tier. Some (like the CI configurator) may already be within the team's expertise. Others (like the Canary Deployment Planner) are not needed until Phase 5, which may be months away. Prioritizing them lower does not diminish their importance; it reflects the practical reality that the migration cannot wait for all 26 skills to be fully built before work begins.


### 9.1 Why Not Build Everything First

The tiered approach is a deliberate decision, not a concession to resource constraints. Building all 26 skills before starting the migration would take months, during which the migration makes no progress. More importantly, the skills built later benefit from the experience gained during earlier phases. The Bytes/String Boundary Fixer (Tier 3) will be more effective if it is built after the Data Format Analyzer (Tier 1) has been run against the actual codebase, because the real data patterns inform the fixer's design. The Encoding Stress Tester (Tier 4) benefits from the encoding edge cases discovered during Phase 3 semantic fixes, which reveal the specific encoding scenarios that the codebase actually encounters.

Building skills just-in-time also allows the project to adapt. If Phase 0 analysis reveals that the codebase has no C extensions, the C Extension Flagger can be deprioritized permanently. If Phase 1 reveals that `unicode_literals` causes minimal breakage, the bytes/string risk assessment can be revised downward. Building all skills upfront commits resources to solving problems that may not exist.

The exception is the four Tier 1 skills, which must be built before the migration begins because they provide the infrastructure that all other work depends on. These are the minimum viable product for the migration project.


## 10. Common Failure Modes

Before discussing the architectural principles that inform the phase model, it is worth enumerating the failure modes that the phased approach is designed to prevent. These are patterns observed in migrations that went poorly, and the phase model's structure is a direct response to each one.

**Failure: Converting code without understanding the data layer.** A team runs `futurize` across the codebase, fixes the syntax errors, gets the tests passing, and ships. Two weeks later, a batch job that processes mainframe data starts producing corrupted output because EBCDIC byte constants in the parser were silently converted to Unicode characters. Phase 0's data layer analysis and Phase 3's boundary-by-boundary semantic fixes prevent this by ensuring every data path is explicitly analyzed before it is converted.

**Failure: Converting modules in the wrong order.** A team converts their utility library to Py3 semantics, but the utility library's callers are still Py2. The utility library's functions now return `str` (text), but the callers expect `str` (bytes). The callers "work" -- no exceptions are raised -- but the data flowing through the system has silently changed type, and the corruption is not detected until a downstream consumer encounters it. Phase 2's dependency-ordered conversion prevents this by converting leaf modules first and working inward.

**Failure: No rollback plan.** A team converts 50 modules over three months, discovers a deep semantic issue in module 15, and realizes they need to revert to the Py2 version. But modules 16-50 depend on module 15's Py3 behavior, so reverting module 15 breaks modules 16-50. The rollback becomes an all-or-nothing proposition, and the team loses three months of work. Phase-specific rollback planning with dependency tracking prevents this.

**Failure: Skipping characterization tests.** A team converts a module, runs the existing tests (which were written to test correct behavior, not to characterize the code's actual behavior), and the tests pass. In production, the converted code handles an edge case differently from the Py2 version. The existing tests did not cover this edge case because it was not part of the specification. Phase 1's characterization test generation creates tests that capture the code's actual behavior, including edge cases that are outside the specification.

**Failure: Not testing with non-ASCII data.** A team converts a web application, runs the test suite (which uses ASCII test data), and everything passes. In production, a user with an accented name triggers a `UnicodeDecodeError` in a code path that was "working" under Py2 only because all test data was ASCII. Phase 1's encoding-aware test generation and Phase 4's encoding stress testing prevent this by deliberately exercising non-ASCII data paths.

**Failure: Treating the migration as purely technical.** A team focuses on code conversion and neglects build system updates, deployment configuration, CI matrices, shebang lines, and documentation. The code is Py3-compatible but the build system still invokes `python2`, the Docker image still uses a Py2 base image, and the deployment script still references `/usr/bin/python`. Phase 2's build system updater and Phase 5's cleanup ensure that the non-code infrastructure is updated alongside the code.

**Failure: Inadequate soak period.** A team completes Phase 4 verification, passes all gates, and cuts over to Python 3. Two weeks later, the monthly billing batch job runs for the first time on Py3 and fails because it processes data in a format that the daily jobs do not encounter. The monthly job was not exercised during the soak period because the soak period was only 10 days. Phase 5's soak period should be long enough to capture at least one cycle of every recurring job, including monthly, quarterly, and annual processes.

**Failure: Removing compatibility code too early.** A team removes `six` and `__future__` imports before the soak period is complete, then discovers an issue that requires rolling back to Python 2. The rollback is impossible because the code no longer runs on Py2 -- the compatibility shims that enabled dual-interpreter execution have been removed. Phase 5's structure addresses this by keeping the compatibility code in place throughout the soak period and only removing it after the soak period completes successfully.

**Failure: Inconsistent encoding decisions across modules.** Different developers working on different modules make different encoding assumptions. Module A decodes serial port data as ASCII at the read point. Module B, which receives the same data through a different path, assumes it is still bytes. Data flowing from A through a shared utility to B changes type mid-pipeline. The orchestration layer's decision log and cross-developer communication (Section 8.4) prevents this by recording encoding decisions centrally and making them visible to all developers working on related modules.

Each of these failures is avoidable, and the phase model is designed to make them difficult to commit. The gates between phases are the mechanism: you cannot proceed to Phase 2 without Phase 0's data layer analysis, you cannot proceed to Phase 3 without Phase 2's per-unit test verification, and you cannot proceed to Phase 5 without Phase 4's encoding stress tests. The gates do not prevent all possible failures -- they prevent the *structural* failures that arise from doing things in the wrong order or skipping essential steps.


## 11. Architectural Insight: Autonomy Levels

The decomposition into phases and skills is not just an organizational convenience. It reflects a fundamental insight about the different levels of autonomy required at different stages of the migration.

Phase 2 mechanical conversion can run largely unattended. The transformations are well-defined, the correct output is deterministic for each input pattern, and the gate check (tests pass on both interpreters) is a binary assessment. A tool that applies these transformations, runs the tests, and reports pass or fail needs minimal human supervision. Operator attention is needed only when a conversion unit fails its gate check, which should be infrequent if the Phase 0 analysis correctly identified the syntax-only issues.

Phase 3 semantic fixes must surface decisions to humans. The bytes/string divide, integer division semantics, comparison operator replacements, metaclass behavior -- these are questions where the correct answer depends on understanding the code's purpose, its data flows, and its operational context. A tool that makes these decisions autonomously will sometimes make the wrong decision, and the cost of a wrong decision (a subtle runtime bug that passes all tests but produces incorrect output in production) exceeds the cost of pausing to ask a human. The right design for Phase 3 tooling is: identify the issue, propose options with tradeoffs, present to a human, apply the human's decision.

Gate checks are explicitly about stopping and requiring judgment. The purpose of a gate is not to add ceremony but to create a decision point where a human evaluates whether the accumulated evidence (test results, lint reports, coverage metrics, behavioral diffs, performance benchmarks) is sufficient to proceed. Automating the evidence collection while keeping the proceed/stop decision manual is the right balance. Over time, as the team gains confidence in the migration process, some gates may be automated (e.g., Phase 2 advancement could be automatic if all tests pass), but the initial posture should be conservative.

A monolithic migration tool that tries to handle all of this in a single pass inevitably makes one of two mistakes: it is too autonomous (making semantic decisions it should not, producing plausible but incorrect conversions) or too conservative (stopping to ask about mechanical transformations it could handle independently, slowing down the high-volume Phase 2 work). The phased skill architecture avoids this by matching the level of autonomy to the nature of the work at each stage.

This insight extends to the design of individual skills. Within Phase 3, for example, the Bytes/String Boundary Fixer should present decisions to humans but also offer a recommended action based on heuristics (e.g., "this data originates from a serial port and is used in string formatting -- recommend decoding as ASCII at the serial port read"). The human can accept the recommendation with a single confirmation or override it with a different decision. This is faster than requiring the human to analyze each boundary from scratch, while still keeping the human in the decision loop for cases where the heuristic is wrong.

The skills should also be designed for re-entrancy. A skill that runs against a module and discovers 15 bytes/string boundaries should be able to process them in any order and resume after interruption. If a developer resolves 10 of the 15 boundaries today and the remaining 5 tomorrow, the skill should pick up where it left off without re-analyzing the entire module. This is important for Phase 3, where a single module might take several days to complete.

### 11.1 The Migration as a Pipeline

The phase model describes a pipeline, not a waterfall. At any given time during the migration, different modules are at different stages. While the first batch of modules is in Phase 4 verification, the second batch may be in Phase 3, the third batch in Phase 2, and the remaining modules may still be at Phase 0.

This pipelining is efficient because it keeps all skill teams productive simultaneously. The Phase 2 automated converter does not sit idle while the Phase 3 semantic fixes are being resolved; it processes the next batch of modules. The Phase 4 verification does not wait for all Phase 3 work to complete; it starts as soon as the first modules exit Phase 3.

The pipeline does have dependencies that limit parallelism. A module's dependencies must be at the same or later phase; the critical path sets the minimum timeline; and Phase 0 must complete (for the entire codebase) before Phase 1 begins (for any module). But within these constraints, the pipeline enables significant parallelism and keeps the migration moving forward continuously.

Visualized as a timeline for a hypothetical 100-module codebase:

```
Month 1:  Phase 0 (all modules) + Phase 1 (all modules)
Month 2:  Phase 2 (batch 1: 30 leaf modules)
Month 3:  Phase 2 (batch 2: 30 mid-level modules) + Phase 3 (batch 1)
Month 4:  Phase 2 (batch 3: 25 core modules) + Phase 3 (batch 2) + Phase 4 (batch 1)
Month 5:  Phase 2 (batch 4: 15 remaining) + Phase 3 (batch 3) + Phase 4 (batch 2)
Month 6:  Phase 3 (batch 4) + Phase 4 (batch 3)
Month 7:  Phase 4 (batch 4) + Phase 5 (canary deployment)
Month 8:  Phase 5 (soak period + cleanup)
```

This is illustrative, not prescriptive. Real timelines depend on the codebase's size, complexity, and risk profile. But the pipeline structure -- with multiple batches progressing through different phases concurrently -- is the general pattern that makes large-scale migration feasible within organizational patience.


## 12. References

The detailed specifications for all 26 skills -- including inputs, outputs, capabilities, gate criteria, and rollback procedures -- are in [PLAN.md](../PLAN.md).

PLAN.md also defines 12 shared reference documents that provide the domain knowledge skills need to operate. These include:

| Document | Content |
|---|---|
| `py2-py3-syntax-changes.md` | Complete catalog of Python 2 to 3 syntax differences |
| `py2-py3-semantic-changes.md` | Complete catalog of semantic differences |
| `stdlib-removals-by-version.md` | Standard library modules removed in each Py3 version |
| `encoding-patterns.md` | EBCDIC, binary protocols, mixed encoding detection |
| `scada-protocol-patterns.md` | Common IoT/SCADA data handling patterns |
| `serialization-migration.md` | Pickle, marshal, shelve Py2-to-Py3 migration guide |
| `encoding-test-vectors.md` | Test data for various encodings |
| `hypothesis-strategies.md` | Property-based testing strategies for data transformations |
| `bytes-str-patterns.md` | Common bytes/string patterns and their correct Py3 form |
| `industrial-data-encodings.md` | Encoding conventions for SCADA, CNC, mainframe data |
| `encoding-edge-cases.md` | Comprehensive encoding gotchas |
| `adversarial-encoding-inputs.md` | Test vectors for common encoding failure modes |

See the Reference Documents table in PLAN.md for the complete mapping of which skills depend on which reference documents, and the directory structure section for where each document lives in the project.

### 12.1 External References

The following external resources are valuable for practitioners working on Python 2-to-3 migrations:

**Python documentation:**
- The official [Python 3 porting guide](https://docs.python.org/3/howto/pyporting.html) covers the basics of writing code compatible with both Python 2 and 3.
- The [What's New](https://docs.python.org/3/whatsnew/index.html) pages for each Python 3 minor version document the specific changes, deprecations, and removals.
- The [C API changes](https://docs.python.org/3/whatsnew/3.12.html#c-api-changes) sections are essential for codebases with C extensions.

**Tool documentation:**
- `futurize` and `python-future`: https://python-future.org/
- `modernize` and `six`: https://pypi.org/project/modernize/ and https://pypi.org/project/six/
- `pyupgrade`: https://github.com/asottile/pyupgrade
- `pylint` Python 3 checker: `pylint --py3k` (documented in pylint's checker reference)
- `mypy`: https://mypy.readthedocs.io/

**Industry migration reports:**
- Instagram's Py2-to-Py3 migration (documented in various PyCon talks and engineering blog posts) is the canonical reference for canary deployment of a Python migration in a large-scale production service.
- Dropbox's multi-year migration of a million-line codebase is documented in conference talks and blog posts covering the incremental approach, the tooling they built, and the surprises they encountered.

**Standards and specifications:**
- PEP 3120: Using UTF-8 as the default source encoding (explains why Python 3 defaults to UTF-8).
- PEP 393: Flexible string representation (explains the internal storage changes that affect C extensions).
- PEP 3333: Python Web Server Gateway Interface (WSGI) updates for Python 3 (relevant for web application migrations).
- The `struct` module documentation for both Python 2 and Python 3, particularly the differences in how format strings are handled (Python 3 requires `bytes` format strings or `str` format strings depending on the operation).

### 12.2 Relationship to PLAN.md

This document and PLAN.md are designed to be read together. This document provides the strategic reasoning -- why the migration is structured as it is, what the risks are, and how the phase model addresses them. PLAN.md provides the operational detail -- what each skill does, what it takes as input, what it produces, and what gate criteria apply.

If you are a project lead or architect planning a migration, read this document first to understand the approach, then use PLAN.md to plan the specific work. If you are a developer building or using the migration skills, PLAN.md is your primary reference, with this document providing background when you need to understand why a skill is designed the way it is.

The two documents should not be read in isolation. This document refers to specific phases and skills by their PLAN.md designations (e.g., "Skill 3.1: Bytes/String Boundary Fixer"). PLAN.md's skill specifications assume familiarity with the strategic reasoning in this document (e.g., why leaf-first conversion ordering matters, why `unicode_literals` is the highest-risk future import, why encoding stress testing uses adversarial inputs).
