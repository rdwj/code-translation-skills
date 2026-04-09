# OpenRewrite Research Findings

Researched 2026-04-08 to answer: can OpenRewrite serve as the Java AST transformation engine in the agent kit?

## Verdict

**Yes for Java. No for anything else.**

OpenRewrite solves the Java mechanical conversion problem almost exactly as we'd want it solved. Use it. Do not plan to use it for Python 2→3, JavaScript, TypeScript, C#, or Go — each needs its own engine.

## Core model

- **LST (Lossless Semantic Tree):** parses source preserving whitespace, comments, formatting, *and* carries full type attribution (resolved symbols, dependency info). Recipes mutate the LST, then OpenRewrite re-prints preserving original style.
- **Recipes:** three flavors — declarative YAML (compose existing recipes), Refaster templates (pattern/replacement), imperative Java (full visitor power). Recipes are composable, versioned via Maven coordinates, names stable as public API.
- **Languages in OSS core:** Java, Kotlin, Groovy, JavaScript, TypeScript, plus build/config formats (Maven XML, Gradle, YAML, XML, JSON, TOML, HCL, Properties, Dockerfile, Protobuf).

## Java 8 → 17 coverage

**This is OpenRewrite's flagship use case and it's mature.** The relevant library is [`rewrite-migrate-java`](https://github.com/openrewrite/rewrite-migrate-java), maintained by Moderne, battle-tested on Spring Boot 3, Dropwizard 5, AWS SDK v1→v2.

**Meta-recipes:**
- `org.openrewrite.java.migrate.Java8toJava11`
- `org.openrewrite.java.migrate.UpgradeToJava17` ← primary target
- `org.openrewrite.java.migrate.UpgradeToJava21`
- `org.openrewrite.java.migrate.UpgradeToJava25`

`UpgradeToJava17` chains ~28 sub-recipes including Java 11 upgrade as prerequisite, build file updates, deprecated-API removal, text block adoption, `instanceof` pattern matching.

**Language feature recipes (confirmed present):**
- `var` adoption: `UseVar`, `UseVarForPrimitive`, `UseVarForObject`, `UseVarForGenericMethodInvocations`
- Text blocks: `UseTextBlocks`
- Switch expressions: `SwitchCaseReturnsToSwitchExpression`, `SwitchCaseAssignmentsToSwitchExpression`, `SwitchExpressionYieldToArrow`
- Pattern matching: `SwitchPatternMatching` (JEP 441) + `instanceof` pattern matching in the meta
- Records: `LombokValueToRecord` exists; general `ClassToRecord` **was still open issue #391 at time of research — needs verification**
- Sealed classes: **no dedicated conversion recipe found** (likely because safe conversion requires whole-program knowledge of subclasses)
- Module system (JPMS): **no first-class `module-info.java` generator found — needs verification**
- Jakarta namespace: `JavaxMigrationToJakarta` (EE 9), `JakartaEE10`, `JakartaEE11`, plus dozens of library-specific variants (`JacksonJavaxToJakarta`, `EhcacheJavaxToJakarta`, etc.)
- Deprecated API removal: handled by upgrade meta-recipes

**Gaps to fill with LLM-powered transforms:**
- Sealed class conversion
- Class→record conversion (verify status)
- JPMS `module-info.java` generation
- Project-specific API surface changes

## Invocation for agents

**Recommended path:** Maven plugin in dry-run mode without modifying the user's POM.

```bash
mvn -U org.openrewrite.maven:rewrite-maven-plugin:dryRun \
    -Drewrite.activeRecipes=org.openrewrite.java.migrate.UpgradeToJava17 \
    -Drewrite.recipeArtifactCoordinates=org.openrewrite.recipe:rewrite-migrate-java:LATEST \
    -Drewrite.exportDatatables=true
```

This produces:
- **Unified diff patch file** at `target/site/rewrite/rewrite.patch` — primary agent signal, trivially parseable
- **CSV data tables** at `target/rewrite/datatables/*.csv` — structured "what changed where" data per recipe
- Console warnings per changed recipe

Then either `git apply rewrite.patch` or run `rewrite:run` to commit changes in place.

**No native JSON or SARIF output.** Plan to build a thin adapter (~50 lines of Python) that converts patch + CSVs into a normalized JSON schema as the stable contract between the agent kit and OpenRewrite.

**Alternative invocations:**
- **`rewrite-jbang`** (community): `jbang rewrite@maxandersen/rewrite-jbang --recipes <list> [--dry-run]`. Build-file-independent. Maintained by Max Andersen. Not blessed by Moderne; may lag upstream.
- **Moderne CLI (`mod`)**: official, cleanest UX, free for OSS with token. Introduces vendor dependency; probably skip for v1.

**Hard prerequisite:** OpenRewrite's type attribution depends on knowing the classpath. For real Java codebases, the agent kit must verify `mvn compile` (or `gradle compileJava`) passes before running recipes. Without classpath, recipes silently fail to match — see failure modes.

## Dry-run is first-class

`rewrite:dryRun` is exactly the "generate diff, present for review, then apply" flow we want. Matches Claude Code's existing review patterns. The agent shows the diff, user approves, then `git apply` or `rewrite:run`.

Can also be used as a CI gate via `failOnDryRunResults=true`.

## Custom recipes

**Start with YAML declarative composition only.** File at `src/main/resources/META-INF/rewrite/*.yml`:

```yaml
type: specs.openrewrite.org/v1beta/recipe
name: com.yourorg.MyMigration
displayName: My Migration
recipeList:
  - org.openrewrite.java.migrate.UpgradeToJava17
  - org.openrewrite.java.ChangePackage:
      oldPackageName: com.old
      newPackageName: com.new
```

**Agent use case:** generate these YAML files on the fly as the declarative glue between existing recipes. Lowest-risk, highest-leverage integration path.

**Defer imperative Java recipes** until you hit a concrete gap. When you do, use the [`rewrite-recipe-starter`](https://github.com/openrewrite/rewrite-recipe-starter) template. Expect a couple days per non-trivial recipe — steeper curve than the docs suggest.

## Licensing — pay attention

Three tiers per [OpenRewrite licensing docs](https://docs.openrewrite.org/licensing/openrewrite-licensing):

1. **Apache 2.0** — core engine, parsers, most foundational recipes
2. **Moderne Source Available License (MSAL)** — some recipes in higher-value packages. You can apply them to your own code freely; you cannot resell, wrap in a commercial product, or offer as a managed service.
3. **Moderne proprietary** — premium recipes and the multi-repo platform

**Critical gotcha:** `rewrite-migrate-java` contains **both** `apache-license-v2.txt` **and** `moderne-source-available-license.md`. It's a mixed-license repo — individual recipes may fall under either. Moderne has been moving popular migration recipes to MSAL over time.

**Impact on the agent kit:**
- Running recipes against user code — **fine** under either license
- Bundling/redistributing recipes in a commercial product — **risky under MSAL**, get legal review
- For internal/customer-code-only use, no issue

**Needs verification:** Check license header in the source file of each specific recipe we depend on. The split isn't cleanly separated by module.

## Non-Java languages: don't plan on it

- **Python:** `rewrite-python` repo was **archived January 2026**, code moved into Moderne platform. Python recipes are Moderne-CLI-only. **No Python 2 → 3 recipe exists, and probably never will.** For Python 2→3 use `lib2to3`, `libcst`-based tools, or Google's `pasta`.
- **Kotlin, Groovy, JS, TS:** supported in OSS core but maturity lower than Java. Few high-level migration recipes. Useful mainly for mechanical cleanup and style normalization.
- **C#, Go, Ruby, COBOL:** Moderne platform only, commercial.

**Implication for the kit:** OpenRewrite is the **Java engine**, not a universal engine. Each non-Java language needs its own adapter:

| Language | Candidate engine |
|---|---|
| Java | **OpenRewrite** |
| Python | libcst (mature, Facebook/Instagram origin) or lib2to3 for Py2→3 |
| JavaScript / TypeScript | jscodeshift or ts-morph |
| C# | Roslyn + analyzers |
| Go | `gofmt -r`, gopls, or dst |
| Ruby | RuboCop autocorrect, Parser gem |
| C / C++ | libclang, Clang tooling |

## Failure modes to plan for

1. **Type attribution failures cascade silently.** Unresolved dependency → LST built without types → recipes silently fail to match → build success, no changes, no error. **Mitigation:** pre-check `mvn compile` passes; compare pre/post data tables to detect "ran but did nothing."
2. **Parser bugs surface as misleading "source file problems" messages.**
3. **Memory footprint on large monorepos.** LST is in-memory. Plan `MAVEN_OPTS=-Xmx8G` or larger.
4. **Private Maven repos / corporate settings.xml.** Auth and mirrors add friction. Agent kit needs to document `settings.xml` handling.
5. **Silent no-op recipes** (issue #4200). Agent should always verify dry-run patch is non-empty for recipes it expects to apply.
6. **Recipes run atomically** — can't pause mid-stream. Each dry-run/review cycle is one atomic recipe list.

## Build files and config files — real strength

OpenRewrite handles `pom.xml`, `build.gradle(.kts)`, Dockerfiles, `web.xml`, `ejb-jar.xml`, YAML, JSON, TOML, HCL, Properties as first-class citizens with dedicated recipes. Upgrade recipes automatically update `maven-compiler-plugin` `<source>`/`<target>` from 1.8 to 17 as part of the same run. This is a real advantage over Spoon/JavaParser/Eclipse JDT, which would require hand-rolled XML manipulation.

## Alternatives briefly considered

| Tool | Verdict |
|---|---|
| Error Prone + Refaster (Google) | Fast, tight build integration, but Refaster is expression-level only. No project-wide refactors. |
| Spoon (INRIA) | Powerful, research-quality AST, but no recipe ecosystem — you build everything yourself. |
| JavaParser | Simple API, but weak type resolution (symbol solver is fragile). You write all semantics. |
| Eclipse JDT ASTRewrite | Powerful but Eclipse runtime dependency, heavyweight, no recipe ecosystem. |

**OpenRewrite is the de facto choice for pre-built maintained migration recipes at scale.** Nothing else has the recipe library or the industry mindshare. Used by AWS SDK migration, Spring Boot migration, Jakarta migration tooling.

## Recommended agent loop for Java work

1. Prerequisite check: `mvn -q compile` (or Gradle) passes
2. Agent generates YAML declarative recipe to `rewrite.yml` composing chosen recipes
3. Agent runs `mvn ... rewrite:dryRun ... -Drewrite.exportDatatables=true` as subprocess
4. Agent parses `target/site/rewrite/rewrite.patch` — primary signal
5. Agent optionally parses `target/rewrite/datatables/*.csv` for structured per-recipe data
6. Agent presents diff for review
7. User approves → `git apply` the patch or `rewrite:run` for in-place changes
8. On failure or silent no-op: re-check classpath, try narrower recipe set, or flag for LLM-driven semantic transform

## Key design implications for our kit

1. **Java mechanical conversion is ~solved.** We don't build Java pattern catalogs for mechanical transforms — we map our internal "migration profile" to OpenRewrite recipe names.
2. **Our Java profile is a recipe name list, not a pattern catalog.** The YAML file we ship for Java 8→17 is essentially `[UpgradeToJava17, JavaxMigrationToJakarta, <project-specific extras>]`.
3. **Python profile is completely different from Java profile.** No shared pattern catalog abstraction. Each profile declares which engine handles its mechanical phase. The "profile" is really a bundle of engine choices and their configurations.
4. **Build a thin JSON wrapper over OpenRewrite's patch + CSV output.** That's the contract between the agent kit and OpenRewrite. ~50 lines of Python. Stable regardless of how OpenRewrite evolves.
5. **Sealed classes, `ClassToRecord`, JPMS `module-info.java`** stay in the semantic/LLM-driven phase. Don't expect OpenRewrite to cover them.
6. **Legal review for commercial distribution** of the kit if we bundle MSAL recipes. For customer-engagement use (running on their code), no issue.

## Items still needing verification

- Whether general `ClassToRecord` recipe has landed in `rewrite-migrate-java` (issue #391)
- Whether JPMS `module-info.java` generator recipe exists
- Per-recipe Apache vs MSAL license on recipes we'd depend on
- Moderne CLI licensing terms for automated/agent use against private repos

## Key URLs

- Docs: https://docs.openrewrite.org/
- Java migration: https://docs.openrewrite.org/recipes/java/migrate
- UpgradeToJava17: https://docs.openrewrite.org/recipes/java/migrate/upgradetojava17
- Run without modifying build: https://docs.openrewrite.org/running-recipes/running-rewrite-on-a-maven-project-without-modifying-the-build
- dryRun mojo: https://openrewrite.github.io/rewrite-maven-plugin/dryRun-mojo.html
- Licensing: https://docs.openrewrite.org/licensing/openrewrite-licensing
- Data tables: https://docs.openrewrite.org/running-recipes/data-tables
- rewrite-migrate-java source: https://github.com/openrewrite/rewrite-migrate-java
- Recipe starter template: https://github.com/openrewrite/rewrite-recipe-starter
- rewrite-jbang (standalone): https://github.com/maxandersen/rewrite-jbang
