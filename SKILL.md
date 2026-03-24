# Engram Memory Tool
You have access to a deterministic O(1) memory retrieval CLI called `engram`.
Use this to store static facts, API documentation, or user preferences, and retrieve them instantly to save context space.

Usage:
- Store a fact: `engram store "The database URL is postgres://localhost:5432"`
- Recall a fact: `engram retrieve "What is the database URL?"`
- Update a fact: `engram update "The database URL is postgres://127.0.0.1:5432"`

If you are unsure of the commands, run `engram --help`.