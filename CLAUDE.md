# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

跨设备 Skill 管理软件 — a cross-platform desktop tool (Windows / macOS / Linux) for managing AI coding assistant skills across local and remote machines. Supports Codex, Claude Code, and CC-Switch at both global and project levels.

## Key Documents

- `REQUIREMENTS.md` — full requirements specification
- `IMPLEMENTATION.md` — architecture & implementation plan
- `simple-description.md` — original brief

## Tech Stack

- **Language:** Python 3.10+
- **GUI:** PySide6 6.5+
- **SSH:** Paramiko
- **Crypto:** cryptography (AES-256-GCM)
- **Credential storage:** keyring (Windows Credential Manager / macOS Keychain / Linux Secret Service)
- **Storage:** SQLite (stdlib `sqlite3`)

## Project Structure

```
src/
├── main.py              # Entry point
├── config.py            # Constants, tool names, path templates
├── models/              # Data layer — Connection, Project, SyncHistory + CRUD over sqlite3
├── services/            # Business logic — Scanner, Hasher, Sync, SSH, Crypto, ProjectService
├── ui/                  # PySide6 widgets — MainWindow, Sidebar, Panels, BottomBar, Dialogs
└── utils/               # Path utilities, logging

tests/                   # pytest suite (56 tests, 8 modules)
```

## Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows
pip install -r requirements.txt

# Run
python -m src.main

# Test
python -m pytest tests/ -v

# Package (all platforms)
pip install pyinstaller
pyinstaller skill-manager.spec
```

## Cross-Platform Notes

- All paths use `pathlib.Path` / `Path.home()` — no OS-specific hardcoding
- Keyring auto-selects the native credential store per platform
- PyInstaller produces platform-native executables (`.exe` / `.app` / ELF binary)
- Linux requires: `sudo apt install libxcb-cursor0` (Qt runtime dep)
- The same source tree runs on all three platforms without modification

## Skill Directory Layout

```
{Path.home()}/.codex/skills      # Codex global skills
{Path.home()}/.claude/skills     # Claude Code global skills
{Path.home()}/.cc-switch/skills  # CC-Switch global skills

Project-level:
<project>/.claude/skills
<project>/.codex/skills
```

## Core Features

1. **Read skills** — scan local/remote skill directories (F1, F2)
2. **Deduplicate & compare** — SHA-256 hash, classify as synced/local-only/remote-only/conflict (F3)
3. **Sync skills** — push/pull with atomic write (temp+rename), backup/rollback, conflict handling (F4)
4. **SSH connection management** — lazy connect, idle timeout, key/password auth with encrypted storage (F5)
5. **Project management** — register project dirs, project-level skill isolation (F6)

## Sync Directions

- Local ↔ Remote (cross-device)
- Global ↔ Project (cross-level)
- Project ↔ Project (same or different device)

## Architecture

Three-layer architecture:
- **UI layer** — PySide6 widgets, QThread workers for I/O, signals/slots for data flow
- **Services layer** — pure Python business logic, no Qt dependency
- **Models layer** — dataclasses + thin CRUD over sqlite3, no business logic

Skill identity is `(name, tool)` — same name with different tools are different skills. Hash-based comparison detects content divergence. Skills are ephemeral (not persisted to DB), discovered fresh on each scan.

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
