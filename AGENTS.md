# Agent Instructions

These instructions are mandatory for AI coding agents working in this repository.

## Fork authorization

This is the maintained `kopiro` fork. Proceed within the owner's requested scope
without a separate AI-consent or prior human-review gate. Follow the upstream
project's contribution rules when submitting changes to upstream.

## Repository Rules

- Read `CONTRIBUTING.md` before making changes.
- Keep changes small, focused, and easy to review.
- Read the relevant README, FAQ, issues, and surrounding code before changing behavior.
- Preserve existing behavior unless the user explicitly asked for a behavior change and the PR explains it.
- Do not make broad root-cause claims without verifying them in the current code and relevant dependencies.
- Avoid unnecessary abstractions, broad rewrites, and verbose generated explanations.
- Update docs and translations for user-facing behavior changes.
- State exactly what was tested and what was not tested.
- Verify Home Assistant runtime changes directly when access and authorization are available. Ask the user only for observations that cannot be obtained directly, and distinguish agent verification from human testing.

## Commits and PRs

If you create commits or a PR with AI assistance, disclose it.

PR bodies must include:

```text
AI assistance: yes/no
Tool(s): <tool or model, if known>
AI contribution level: <none, research only, small snippets, substantial code, majority of PR>
AI contribution: <what the AI drafted or changed>
Human review: <what the user reviewed, tested, and changed>
Home Assistant testing with user: <steps, observations, and follow-up changes from the user/AI testing loop>
```

AI-created commits must include trailers:

```text
AI-Assisted: yes
AI-Tool: <tool or model, if known>
AI-Contribution-Level: <small snippets, substantial code, majority of commit>
AI-Contribution: <short description of generated or drafted parts>
Human-Reviewed: <yes/no; report only review that actually occurred>
```
