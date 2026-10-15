# 0018: Subagent roles on cheaper tiers, and model picks per catalog

Status: accepted (2026-10-15)

## Decision

`install` writes two Codex agent roles from `core/agents/`, each with the model and reasoning effort of one tier:

- `$CODEX_HOME/agents/explorer.toml` on the `bulk` tier. It replaces Codex's built-in `explorer`. It answers one lookup with `path:start-end` line ranges and short quotes, and never edits.
- `$CODEX_HOME/agents/reviewer.toml` on the `review` tier. It looks only for what is wrong in a plan, diff, finding or claim, and never edits.

`grilling`, `redacao` and the `web-consensus` researchers use `explorer`; the `web-consensus` challenger uses `reviewer`. `bug-hunt` keeps its per-category subagents on the default role, because judging a bug is not a lookup. `[agents] default_subagent_model` stays unset, so code-writing subagents keep the session's model. Doctor checks both role files, and warns when a role's tier is the same as `default`, because the role then saves nothing.

The example overlays pick models from each catalog's own descriptions:

| Tier | `personal` (public catalog) | `enterprise` (work catalog) |
|---|---|---|
| `default` | `gpt-6.1-sol` | `gpt-6-sol` |
| `deep` | `gpt-6-astra` | `gpt-6-sol` |
| `bulk` | `gpt-6-luna` | `gpt-6-luna` |
| `review` | `gpt-6-astra` | `gpt-5.6-sol` |

## Context

On the bench, one session spent 4.08M input tokens, and 1.78M of them (44%) went to two subagents running the parent's frontier model at `high`. A dedicated exploration subagent that returns paths and line ranges cut the main agent's tokens by 60% on SWE-QA and added 5.5 points on SWE-bench Pro (arXiv 2606.14066), with smaller or negative effects on other benchmarks.

The user also asked that every skill run on the best model for its job. A skill cannot choose its model: `SkillMetadata` has no model field (`codex-rs/skills/src/model.rs`, rust-v0.162.1), so a skill runs on the session's model. A skill can reach a different model only through a subagent role.

## Data

- Codex discovers role files in `<config folder>/agents/*.toml` for every config layer (`agent-roles/src/loader.rs`). A role file holds `name`, `description`, `developer_instructions` (required for a discovered file) and config keys.
- A user role wins over a built-in one with the same name (`core/src/agent/role.rs`, `resolve_role_config`). The built-in `explorer` points at `core/assets/agent/builtins/explorer.toml`, which is empty, so it inherits the parent's model.
- From a role file Codex applies only `developer_instructions`, `model`, `model_reasoning_effort`, `model_reasoning_summary`, `model_verbosity`, `personality`, `service_tier`, a few feature switches and skill disables (`AgentRoleOverrides`, same file). It does not apply sandbox settings, so the explorer's read-only behaviour comes from its instructions, inside the session's sandbox.
- Codex 0.162 runs multi-agent v2. Its `spawn_agent` takes `agent_type` and applies the role even to a full-history fork (`core/src/agent/child_config.rs`, `core/src/tools/handlers/multi_agents_v2/spawn.rs`), but only offers `agent_type` when at least one user role exists (`expose_agent_type: !agent_roles.is_empty()`, `core/src/tools/spec_plan.rs`). Without these files the model could not pick a role at all.
- A full-history fork re-sends the parent's conversation to the child, so the explorer's description asks for a self-contained question instead.
- v2 tells the model not to spawn subagents unless the user, an `AGENTS.md` or a skill asks for them (the `multi_agent_mode` prompt section), which is why the skills name the role.
- When a role sets a model, the spawn tool's role list says "This role's model is set to `<model>` and cannot be changed" (same file, `format_role`).
- The catalog describes `gpt-6.1-sol` as "Latest workhorse model for coding and everyday work", `gpt-6-astra` as "Frontier intelligence for the most demanding work", `gpt-6-luna` as "Fast and affordable model for easier tasks", `gpt-6-sol` as "Previous generation workhorse model" and `gpt-5.6-sol` as "Older generation workhorse model" (`models_cache.json` on the bench, 2026-10-15). The picks follow these descriptions; no quality benchmark between the models was run.
- `multi_agent_reasoning_effort` in the catalog (`xhigh` for two models) applies only when the effort is `ultra` (`protocol/src/openai_models/reasoning_effort.rs`), so it does not raise subagent cost at the tiers' efforts.

## Cost

About 40 lines in `install.py` and `doctor.py`, two role files, four one-line skill edits. The two role descriptions add to the spawn tool's guidance in every request, mostly from the prompt cache.

## Rejected

- `[agents] default_subagent_model` on the bulk model: it moves code-writing workers to the cheap model too.
- A model field in skill frontmatter: Codex does not read one.
- A role per skill: most skills are judgement on the session's model; a lookup role and a review role cover what can be delegated.
