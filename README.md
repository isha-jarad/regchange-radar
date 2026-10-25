# RegChange Radar

**Regulatory change detection and impact analysis for document versions.**

Upload two versions of a regulatory or policy PDF. RegChange Radar finds what was inserted, deleted, or replaced, flags each change with a priority and a plain-English explanation of *why*, saves everything in PostgreSQL, and lets reviewers track their review status change by change.

> **Note:** This is an independent portfolio project. Impact flags come from simple, deterministic keyword rules. They are **review aids, not legal advice or definitive regulatory decisions.**

## Features

- **Upload validation:** checks the file extension, the `%PDF-` header, and a configurable size limit; rejects empty, corrupt, password-protected, and scanned (no text) PDFs with clear, safe error messages
- **Text extraction and normalization** with PyMuPDF (Unicode normalization, hyphenation repair, whitespace cleanup, page-number removal)
- **Paragraph-level diff** with Python's `difflib`, plus a **word-level diff** that isolates exactly which words changed inside a replaced passage
- **Deterministic, configurable impact rules** (a JSON file) that assign `high`, `medium`, `low`, or `none` priority and explain which rule fired and which words matched
- **Auditable storage:** every comparison gets a stable UUID, SHA-256 fingerprints of both files, and the version of the ruleset that produced its flags
- **REST API** (FastAPI): create a comparison, list history with paging, fetch one by ID, and update the review status of each change
- **89 automated tests** (pytest)

## Tech stack

| Layer | Technology |
|---|---|
| API | Python, FastAPI, Uvicorn |
| Validation and schemas | Pydantic, pydantic-settings |
| Database | PostgreSQL, SQLAlchemy 2.x, psycopg 3 |
| PDF text extraction | PyMuPDF |
| Comparison | `difflib` (standard library) |
| Tests | pytest, FastAPI TestClient |

## Architecture

```
POST /comparisons
  -> read and validate each PDF   (size, type, header)
  -> extract paragraphs           (PyMuPDF, normalization)
  -> detect changes               (difflib: paragraph diff, then word diff)
  -> classify each change         (JSON keyword rules -> flags + priority)
  -> save in one transaction      (PostgreSQL)
  -> return the full result
```

The code is layered, and each folder has one job:

| Folder | Responsibility |
|---|---|
| `api/` | HTTP endpoints; maps errors to status codes |
| `services/` | Business logic as plain functions (extraction, diff, rules, persistence); no web or database knowledge in the diff and rule code, so it is easy to test |
| `models/` | SQLAlchemy tables |
| `schemas/` | Pydantic request and response shapes (the API contract) |
| `db/`, `core/` | Database engine and sessions; settings loaded from environment variables |

### Data model

```
comparisons  1 --< document_changes  1 --< impact_flags
(one run)          (one changed passage)    (one rule that fired)
```

- `comparisons`: version labels, filenames, SHA-256 of each file, summary counts, ruleset version, timestamp
- `document_changes`: change type, old and new text, paragraph and page locations, similarity, priority, review status and note
- `impact_flags`: rule id and name, priority, matched terms, explanation

## Quick start (Windows PowerShell)

**Prerequisites:** Python 3.14 (developed and tested on 3.14.7), PostgreSQL (tested on 18), Git.

**1. Clone the repository**

```powershell
git clone <repository-url>
cd regchange-radar\backend
```

**2. Create the database** (run in `psql` as the `postgres` user; choose a password with letters and digits only so it is safe inside a connection URL)

```sql
CREATE ROLE regchange_app WITH LOGIN PASSWORD 'choose-a-password';
CREATE DATABASE regchange_radar OWNER regchange_app;
```

**3. Create a virtual environment and install dependencies**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On macOS or Linux, activate with `source .venv/bin/activate`.

**4. Configure the environment**

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set your password in `DATABASE_URL`. Never commit `.env`.

```
DATABASE_URL=postgresql+psycopg://regchange_app:choose-a-password@localhost:5432/regchange_radar
MAX_UPLOAD_SIZE_MB=10
```

**5. Create the tables and start the server**

```powershell
python -m app.db.init_db
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000/docs** for the interactive API documentation.

## Try it with the sample documents

Two fictional sample PDFs are in `docs/samples/`. In the `/docs` page, open `POST /comparisons`, click **Try it out**, choose `policy_v1.pdf` as the old file and `policy_v2.pdf` as the new file, enter labels such as `v1` and `v2`, and click **Execute**.

Or from the repository root:

```powershell
curl.exe -X POST http://127.0.0.1:8000/comparisons `
  -F "old_file=@docs/samples/policy_v1.pdf" `
  -F "new_file=@docs/samples/policy_v2.pdf" `
  -F "old_version_label=v1" -F "new_version_label=v2"
```

### What the sample produces

6 unchanged paragraphs, 4 replaced, 1 deleted, 1 inserted:

| # | Change | Priority | Rules that fired |
|---|---|---|---|
| 0 | Scope sentence broadened ("and contract research organisations") | none | none |
| 1 | "may" became "shall"; "30 days" became "15 days" | high | Obligation language, Permissive language, Numeric value |
| 2 | "should" became "must"; "three years" became "five years" | high | Obligation language, Permissive language |
| 3 | "means" became "is defined as" | low | Definitions and cross-references |
| 4 | The penalty sentence was deleted | high | Penalties and enforcement, Scope and applicability |
| 5 | A new "Transition period" section with "90 days" was added | high | Deadlines and timing, Numeric value |

Change 0 widens who is covered, but no rule fires. It shows why the flags are review aids and not decisions.

## API

| Method and path | Purpose | Success | Errors |
|---|---|---|---|
| `POST /comparisons` | Upload two PDFs and two version labels (multipart form) | `201` full result | `400` empty, unreadable, encrypted, or text-less PDF; `413` too large; `415` not a PDF; `422` invalid input |
| `GET /comparisons?limit=20&offset=0` | History, newest first, paged | `200` | `422` bad paging values |
| `GET /comparisons/{comparison_id}` | One comparison with all changes and flags | `200` | `404`, `422` |
| `PATCH /comparisons/{comparison_id}/changes/{change_id}/review` | Set `pending`, `reviewed`, or `needs_follow_up`, with an optional note | `200` | `404`, `422` |
| `GET /health`, `GET /health/db` | Liveness and database connectivity | `200` | `503` if the database is unreachable |

Error responses use the shape `{"detail": "..."}` and never include file paths or stack traces. The note on a review is only changed when `review_note` is included in the request.

## How the impact rules work

Rules live in `backend/app/rules/default_rules.json`. Each rule has an `id`, `name`, `priority`, `description`, and a list of `terms` (whole-word, case-insensitive; the longest phrase wins) and/or regex `patterns`. The file is validated at startup, so a broken rule stops the app from starting instead of failing later.

```json
{
  "id": "OBLIGATION_LANGUAGE",
  "name": "Obligation or prohibition language",
  "priority": "high",
  "description": "Mandatory or prohibitive wording was added or removed...",
  "terms": ["shall not", "shall", "must not", "must", "required"]
}
```

Rules run only on the words that actually changed, so an unchanged "shall" in an edited sentence does not trigger a flag. A change's priority is the highest priority among its flags, or `none` if no rule fired. The ruleset version is stored with every comparison, so older results stay explainable after the rules change.

## Testing

```powershell
cd backend
python -m pytest
```

The tests cover insertions, deletions, replacements, identical and empty input, reordering, the impact rules and their validation, upload validation, extraction failures (corrupt, scanned, encrypted), and every API endpoint including its error codes. API tests run against a throwaway in-memory SQLite database and force the database URL to a dummy value before the app loads, so they cannot touch a real database.

## Design decisions

- **Deterministic rules instead of an LLM:** results are reproducible, explainable, and auditable, and cost nothing to run.
- **No temporary files:** PDFs are processed in memory from bytes, so there is nothing to clean up and no server paths to leak. Only fingerprints (SHA-256) are stored, not the files.
- **Services raise domain exceptions; the API layer maps them to HTTP codes,** which keeps the business logic independent of the web framework.
- **One transaction per comparison:** the comparison, its changes, and its flags are saved together or not at all.
- **Strings plus `CHECK` constraints instead of PostgreSQL enums,** which are easier to evolve.
- **Tables are created with `create_all`** through an explicit script (`python -m app.db.init_db`) rather than at server start. This is simple for an MVP, but it does not alter existing tables; Alembic migrations would be the next step.

## Limitations

- Text-based PDFs only. Scanned documents (OCR) are out of scope and are rejected with a clear message.
- Paragraphs come from PyMuPDF's text blocks, a layout heuristic. Tables, multi-column pages, and paragraphs that cross a page break may not split cleanly.
- `difflib` has no concept of moved text, so a moved paragraph appears as a deletion plus an insertion.
- Keyword rules are lexical: they do not understand negation, synonyms, or context. For example, "May" (the month) matches the word "may", numbers written as words ("five") are not detected, and section renumbering can trigger the numeric rule.
- Comparison runs inside the request. Very large documents would need a background worker; documents over 8,000 paragraphs are rejected.
- No authentication or user accounts. Every upload creates a new comparison, even for an identical pair of files.

## Future work

- Alembic migrations
- A React review interface (upload, filter by priority, review changes)
- Printable or downloadable comparison report
- Move detection and finer-grained diffing inside multi-paragraph blocks
- An audit log of review events (who changed what, and when)
- Background processing for large documents
- Authentication and per-user history

## Notes

PyMuPDF is licensed under AGPL-3.0 (or a commercial license). Review its license before any commercial use. This repository does not yet include a license file.