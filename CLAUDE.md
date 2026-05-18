# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

跨设备 Skill 管理软件 — a desktop tool (Windows) for managing AI coding assistant skills across local Windows and remote Linux machines. Supports Codex, Claude Code, and CC-Switch at both global and project levels.

## Key Documents

- `REQUIREMENTS.md` — full requirements specification
- `simple-description.md` — original brief

## Tech Stack (Planned)

- **Language:** Python 3.10+ or Go 1.21+
- **GUI:** PySide6 / WPF / Electron
- **SSH:** Paramiko (Python) / crypto/ssh (Go)
- **Storage:** SQLite for connection configs, project configs, and sync history

## Skill Directory Layout

```
Windows                          Linux
%USERPROFILE%/.codex/skills      ~/.codex/skills
%USERPROFILE%/.claude/skills     ~/.claude/skills
%USERPROFILE%/.cc-switch/skills  ~/.cc-switch/skills

Project-level:
<project>/.claude/skills
<project>/.codex/skills
```

## Core Features to Implement

1. **Read skills** — scan local/remote skill directories for Codex, Claude Code, CC-Switch
2. **Deduplicate & compare** — identify skill differences across devices and levels (global/project)
3. **Sync skills** — push/pull between local and remote, across global/project levels, with tool selection
4. **SSH connection management** — store and reuse remote Linux connection configs
5. **Project management** — register project directories for project-level skill isolation

## Sync Directions

- Local ↔ Remote (cross-device)
- Global ↔ Project (cross-level)
- Project ↔ Project (same or different device)

## Architecture Notes

The application has three conceptual layers:
- **Device layer** — local Windows vs remote Linux, accessed via SSH
- **Level layer** — global skills (shared) vs project skills (scoped to one project)
- **Tool layer** — Codex / Claude Code / CC-Switch, each with its own skills directory

Skill identity is name-based; same name across devices/levels/tools = same skill. Hash-based comparison detects content divergence.

---

## Behavioral Guidelines

These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
