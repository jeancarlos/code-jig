---
name: codegen
description: Use when the user asks to generate an API client or server stubs from an OpenAPI spec, scaffold a project or component, or apply the same mechanical change across many files (a codemod, a rename, an API migration).
---

# Code generation

Generators and codemods are deterministic: the same input gives the same output, at no token cost. Prefer them to writing repetitive code by hand.

## Rules

- The generation command lives in the repo: an npm script, an MSBuild target, a `scripts/` file or the generator's own config file. Anyone can rerun it.
- Never edit generated files by hand. Change the input or the generator's config and regenerate.
- Pin the generator version in the repo's dev dependencies or tool manifest.
- Review the generated diff like any other diff, then run the build and tests.

## OpenAPI clients

| Stack | Tool | Command |
|---|---|---|
| .NET | NSwag | `dotnet new tool-manifest` once, `dotnet tool install NSwag.ConsoleCore`, keep an `nswag.json`, then `DOTNET_CLI_TELEMETRY_OPTOUT=1 dotnet nswag run nswag.json` |
| .NET, TS, Python | Kiota | `KIOTA_CLI_TELEMETRY_OPTOUT=1 kiota generate -l CSharp -d openapi.yaml -o src/Client -n My.Client -c ApiClient` (`-l TypeScript`, `-l Python`) |
| TS, Python | openapi-generator | `npx @openapitools/openapi-generator-cli generate -i openapi.yaml -g typescript-fetch -o src/client` (`-g python`); needs Java, and the first run downloads the generator jar |

Kiota sends usage telemetry unless `KIOTA_CLI_TELEMETRY_OPTOUT=1` is set; set it in the script, not only in your shell.

Windows PowerShell has no `NAME=value command` form: write the variable first in the same command, for example `$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'; dotnet test`.

## Codemods with ast-grep

ast-grep matches syntax, not text, so it does not touch strings or comments that merely look like code.

```
ast-grep run --lang ts --pattern 'console.log($A)' --rewrite 'logger.debug($A)'            # preview
ast-grep run --lang ts --pattern 'console.log($A)' --rewrite 'logger.debug($A)' --update-all
```

For a change applied more than once, write a rule file and keep it in the repo (`sgconfig.yml` plus `rules/`), then `ast-grep scan --update-all`. Languages include C#, TypeScript, JavaScript and Python.

## Scaffolding

Use the stack's own templates: `dotnet new <template>` (with `DOTNET_CLI_TELEMETRY_OPTOUT=1`), `npm create <template>`, or a template the repo already has. Do not invent a project layout the repo does not follow.

## After generating

Then run the repository's own build and test commands (from its README, AGENTS.md or CI configuration) and `harness analyze --base main`, and report what changed, which generator or script made the change, and the build, test and analysis results.
