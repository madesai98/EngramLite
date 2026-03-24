#!/usr/bin/env python3
import argparse
import hashlib
import sqlite3
import unicodedata
from pathlib import Path

# Offload to local workspace memory (SQLite file)
DB_PATH = Path(__file__).resolve().parent / "engram_memory.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = ON")

    c.execute(
        '''CREATE TABLE IF NOT EXISTS facts (
               fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
               text_payload TEXT UNIQUE NOT NULL,
               created_at TEXT DEFAULT CURRENT_TIMESTAMP,
               updated_at TEXT DEFAULT CURRENT_TIMESTAMP
           )'''
    )

    c.execute(
        '''CREATE TABLE IF NOT EXISTS fact_ngrams (
               hash_id TEXT NOT NULL,
               fact_id INTEGER NOT NULL,
               ngram_size INTEGER NOT NULL,
               PRIMARY KEY (hash_id, fact_id),
               FOREIGN KEY (fact_id) REFERENCES facts(fact_id) ON DELETE CASCADE
           )'''
    )

    c.execute("CREATE INDEX IF NOT EXISTS idx_fact_ngrams_hash ON fact_ngrams(hash_id)")

    # One-time migration from legacy schema: memory(hash_id, text_payload)
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memory'")
    has_legacy_memory_table = c.fetchone() is not None
    if has_legacy_memory_table:
        c.execute("SELECT COUNT(*) FROM memory")
        legacy_rows = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM facts")
        fact_rows = c.fetchone()[0]

        if legacy_rows > 0 and fact_rows == 0:
            c.execute(
                '''INSERT OR IGNORE INTO facts (text_payload)
                   SELECT DISTINCT text_payload FROM memory'''
            )
            c.execute(
                '''INSERT OR IGNORE INTO fact_ngrams (hash_id, fact_id, ngram_size)
                   SELECT m.hash_id, f.fact_id, 0
                   FROM memory m
                   JOIN facts f ON f.text_payload = m.text_payload'''
            )

    conn.commit()
    return conn


def canonicalize(text: str) -> str:
    """Implement Tokenizer Compression: NFKC normalization and lowercasing."""
    text = unicodedata.normalize("NFKC", text)
    return text.lower().strip()


def get_ngrams(text: str, n_list=None):
    """Extract N-grams (including unigrams by default)."""
    if n_list is None:
        n_list = [1, 2, 3]

    tokens = text.split()
    ngrams = []
    for n in n_list:
        if n <= 0 or len(tokens) < n:
            continue
        for i in range(len(tokens) - n + 1):
            ngrams.append(" ".join(tokens[i : i + n]))
    return ngrams


def compute_hash(ngram: str) -> str:
    """O(1) deterministic hashing using blake2b."""
    return hashlib.blake2b(ngram.encode("utf-8"), digest_size=16).hexdigest()


def retrieve_memory_ranked(query: str):
    """Return ranked facts as (fact_id, text_payload, overlap_score)."""
    conn = init_db()
    c = conn.cursor()

    norm_query = canonicalize(query)
    ngrams = list(dict.fromkeys(get_ngrams(norm_query)))
    if not ngrams:
        conn.close()
        return []

    query_hashes = [compute_hash(ngram) for ngram in ngrams]
    placeholders = ",".join(["?"] * len(query_hashes))

    c.execute(
        f'''SELECT f.fact_id, f.text_payload, COUNT(*) AS overlap_score
            FROM fact_ngrams fn
            JOIN facts f ON f.fact_id = fn.fact_id
            WHERE fn.hash_id IN ({placeholders})
            GROUP BY f.fact_id, f.text_payload
            ORDER BY overlap_score DESC, f.updated_at DESC''',
        query_hashes,
    )
    rows = c.fetchall()
    conn.close()
    return rows


def store_memory(text: str):
    """Store one fact and index its N-grams."""
    conn = init_db()
    c = conn.cursor()

    norm_text = canonicalize(text)
    ngrams = list(dict.fromkeys(get_ngrams(norm_text)))

    c.execute("INSERT OR IGNORE INTO facts (text_payload) VALUES (?)", (text,))
    c.execute("UPDATE facts SET updated_at = CURRENT_TIMESTAMP WHERE text_payload = ?", (text,))
    c.execute("SELECT fact_id FROM facts WHERE text_payload = ?", (text,))
    row = c.fetchone()

    if not row:
        print("Error: Unable to persist fact.")
        conn.close()
        return

    fact_id = row[0]
    indexed_count = 0

    for ngram in ngrams:
        hash_id = compute_hash(ngram)
        c.execute(
            "INSERT OR IGNORE INTO fact_ngrams(hash_id, fact_id, ngram_size) VALUES (?, ?, ?)",
            (hash_id, fact_id, len(ngram.split())),
        )
        if c.rowcount > 0:
            indexed_count += 1

    conn.commit()
    conn.close()
    print(f"Success: Indexed {indexed_count} N-gram links for fact_id={fact_id}.")


def retrieve_memory(query: str):
    """Retrieve facts by hashed N-gram overlap and rank by overlap count."""
    rows = retrieve_memory_ranked(query)

    if rows:
        print("--- Retrieved Engram Memory ---")
        for _, payload, score in rows:
            print(f"- ({score}) {payload}")
    else:
        print("No local dependencies found in memory.")


def parse_selection(selection_text: str, max_index: int):
    """Parse comma-separated numbers and ranges like 1,3-5 into 1-based indexes."""
    selection_text = selection_text.strip()
    if not selection_text:
        raise ValueError("Selection cannot be empty.")

    result = set()
    parts = [part.strip() for part in selection_text.split(",") if part.strip()]
    if not parts:
        raise ValueError("Selection cannot be empty.")

    for part in parts:
        if "-" in part:
            boundaries = [value.strip() for value in part.split("-", 1)]
            if len(boundaries) != 2 or not boundaries[0].isdigit() or not boundaries[1].isdigit():
                raise ValueError(f"Invalid range: {part}")
            start = int(boundaries[0])
            end = int(boundaries[1])
            if start > end:
                raise ValueError(f"Invalid range: {part}")
            for index in range(start, end + 1):
                if index < 1 or index > max_index:
                    raise ValueError(f"Selection out of range: {index}")
                result.add(index)
        else:
            if not part.isdigit():
                raise ValueError(f"Invalid selection token: {part}")
            index = int(part)
            if index < 1 or index > max_index:
                raise ValueError(f"Selection out of range: {index}")
            result.add(index)

    return sorted(result)


def delete_facts(fact_ids):
    """Delete fact rows by IDs; fact_ngrams are removed via cascade."""
    if not fact_ids:
        return 0

    conn = init_db()
    c = conn.cursor()
    placeholders = ",".join(["?"] * len(fact_ids))
    c.execute(f"DELETE FROM facts WHERE fact_id IN ({placeholders})", tuple(fact_ids))
    deleted_count = c.rowcount
    conn.commit()
    conn.close()
    return deleted_count


def update_memory(new_text: str):
    """Interactive update: select matching facts to replace, or insert as new."""
    rows = retrieve_memory_ranked(new_text)

    if not rows:
        print("No applicable existing facts found. Inserting as new fact.")
        store_memory(new_text)
        return

    print("--- Applicable Facts (ranked) ---")
    for idx, (fact_id, payload, score) in enumerate(rows, start=1):
        print(f"{idx}. ({score}) [id={fact_id}] {payload}")

    selection_indexes = None
    while selection_indexes is None:
        selection_text = input(
            "Select fact numbers to replace (e.g., 1 or 1,3 or 2-4), "
            "type 'new' to insert instead, or 'cancel': "
        ).strip()
        normalized = selection_text.lower()

        if normalized in {"new", "n"}:
            print("Inserting as a new fact.")
            store_memory(new_text)
            return
        if normalized in {"cancel", "c", "q", "quit"}:
            print("Update cancelled.")
            return

        try:
            selection_indexes = parse_selection(selection_text, len(rows))
        except ValueError as error:
            print(f"Invalid selection: {error}")

    selected_rows = [rows[index - 1] for index in selection_indexes]
    selected_fact_ids = [fact_id for fact_id, _, _ in selected_rows]

    print("--- Facts to be replaced ---")
    for _, payload, score in selected_rows:
        print(f"- ({score}) {payload}")
    print("--- Replacement fact ---")
    print(f"- {new_text}")

    confirmation = input("Proceed with replacement and delete selected originals? [y/N]: ").strip().lower()
    if confirmation not in {"y", "yes"}:
        print("Update cancelled.")
        return

    deleted_count = delete_facts(selected_fact_ids)
    store_memory(new_text)
    print(f"Success: Replaced {deleted_count} fact(s) with one updated fact.")


def stats_memory():
    """Print database stats useful for validating indexing behavior."""
    conn = init_db()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM facts")
    fact_count = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM fact_ngrams")
    index_count = c.fetchone()[0]

    c.execute("SELECT COUNT(DISTINCT hash_id) FROM fact_ngrams")
    unique_hashes = c.fetchone()[0]

    conn.close()

    print("--- Engram Memory Stats ---")
    print(f"Facts: {fact_count}")
    print(f"Index links: {index_count}")
    print(f"Unique hashes: {unique_hashes}")


def main():
    parser = argparse.ArgumentParser(description="Engram O(1) Memory Lookup for Agents")
    subparsers = parser.add_subparsers(dest="command", required=True)

    store_parser = subparsers.add_parser("store", help="Store a static fact into memory.")
    store_parser.add_argument("text", type=str, help="The payload to remember.")

    retrieve_parser = subparsers.add_parser("retrieve", help="Retrieve facts based on local context.")
    retrieve_parser.add_argument("query", type=str, help="The local context/query.")

    update_parser = subparsers.add_parser(
        "update",
        help="Retrieve applicable facts and interactively replace selected ones with a new fact.",
    )
    update_parser.add_argument("text", type=str, help="The replacement/new fact text.")

    subparsers.add_parser("stats", help="Show memory database stats.")

    args = parser.parse_args()

    if args.command == "store":
        store_memory(args.text)
    elif args.command == "retrieve":
        retrieve_memory(args.query)
    elif args.command == "update":
        update_memory(args.text)
    elif args.command == "stats":
        stats_memory()


if __name__ == "__main__":
    main()
