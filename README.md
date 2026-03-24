# EngramLite

EngramLite is a small local memory tool for coding agents.

It stores short facts in a SQLite database and retrieves the most relevant ones by matching hashed n-grams (1-3 word chunks). In practice, that gives you fast, repeatable memory lookups without sending private notes to a hosted service.

## What this is used for

Use it when your agent keeps forgetting stable project context, for example:

- local API URLs and ports
- project conventions that do not belong in every prompt
- recurring commands and environment details
- user preferences you want the agent to recall quickly

The tool is intentionally narrow: `store`, `retrieve`, `update`, and `stats`.

## Where this came from (and why)

This repo is a lightweight, local adaptation inspired by the Engram approach shared by DeepSeek:

https://github.com/deepseek-ai/Engram/tree/main

The goal here is practical: keep the core idea, remove setup friction, and make it easy to drop into an existing agent workflow as a single Python script.

Why this version exists:

- no server process required
- no external vector database
- deterministic behavior (same input, same hash/index)
- easy to audit and modify in one file

## How it works

`engram.py` creates a local SQLite file (`engram_memory.db`) with two tables:

- `facts`: unique text payloads
- `fact_ngrams`: hashed n-gram index pointing to facts

On retrieval, query n-grams are hashed, matching facts are scored by overlap count, and higher-overlap facts are returned first.

## Setup

### 1) Requirements

- Python 3.9+
- local write access to this folder

No pip dependencies are required.

### 2) Run directly

From this directory:

```powershell
python .\engram.py --help
python .\engram.py store "The API base URL is http://localhost:3001"
python .\engram.py retrieve "What is the API base URL?"
python .\engram.py update "The API base URL is http://127.0.0.1:3001"
python .\engram.py stats
```

### 3) Optional: make an `engram` command (Windows)

If you want agents/tools to call `engram` directly, add a wrapper to your `PATH`.

Create `engram.cmd` in a folder already on your `PATH`:

```bat
@echo off
python M:\Code\EngramLite\engram.py %*
```

Then verify:

```powershell
engram --help
```

## Using this with existing agent setups

If your agent already supports custom instructions/skills, you usually only need two things:

1. The `engram` command must be callable in the shell.
2. Agent instructions must tell it when to use memory.

This repo already includes a starter skill prompt in `SKILL.md`.

Typical integration pattern:

- at task start, agent runs `engram retrieve "<current task context>"`
- when stable facts appear, agent runs `engram store "<fact>"`
- when facts change, agent runs `engram update "<new fact>"`

Example instruction snippet you can reuse in your agent config:

```text
Use engram for persistent local memory:
- Retrieve relevant memory before starting substantial tasks.
- Store stable facts that are likely to matter later.
- Update facts when values change instead of duplicating entries.
- Use `engram --help` if command format is unclear.
```

## Data location and privacy notes

- Data is stored in `engram_memory.db` in this repo.
- `.gitignore` excludes that DB by default.
- This does not encrypt data at rest; do not store secrets you would not keep in plain local files.

## Command reference

- `engram store "<text>"` — add a fact and index its n-grams
- `engram retrieve "<query>"` — return ranked matching facts
- `engram update "<text>"` — interactively replace matching old facts
- `engram stats` — show fact/index counts

## Notes

EngramLite is intentionally small. If you need semantic retrieval, multi-user sync, encryption, or remote serving, use a larger memory stack. If you need fast local recall with minimal moving parts, this is the point of this repo.

This is mainly just a proof-of-concept extracting the applicable portions DeepSeek's research into a standalone module anyone can try out today rather than waiting for the big model providers to implement the research directly into the hidden layers. While this tool can be used on its own, it will be a lot more powerful when used in conjunction with other tools, this repo only focuses on the data storage and retrieval aspect of a persistent memory system.
