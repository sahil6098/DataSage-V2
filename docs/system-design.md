# DataSage System Design

## Why LangGraph

This project needs multi-step, low-cost orchestration more than open-ended agent loops. LangGraph fits well because we can keep the flow deterministic:

1. Build compact schema context from the selected tables and field notes.
2. Ask the chosen LLM for one safe read-only query plan.
3. Execute the query against the connected source.
4. Ask the LLM for a concise answer and chart recommendation only after data exists.

That keeps token usage predictable and avoids wasting free-tier capacity on preview, validation, storage, or chart rendering.

## High-Level Architecture

### Frontend

- Next.js app in `frontend/`
- Auth screens already attached to the repo
- Chat workspace with:
  - session list
  - secure connector modal
  - source preview modal
  - chart rendering and chart-type dropdown
  - per-message token budget display

### Backend

- FastAPI API in `backend/app`
- MongoDB as the application database for:
  - users
  - refresh tokens
  - sessions
  - encrypted saved source library
- External analytical sources:
  - MongoDB Atlas
  - Supabase PostgreSQL
  - uploaded CSV/Excel/parquet files

## Core Flows

### 1. Auth

- User registers or logs in.
- Backend issues access and refresh JWTs.
- Refresh tokens are stored server-side with revocation support.

### 2. Session Lifecycle

- Frontend creates a hidden draft session before the first prompt or connector action.
- Session becomes visible in the sidebar after the first successful chat turn.
- Each session stores its own connected source and schema guidance.

### 3. Source Connection

#### MongoDB Atlas

- Accept only `mongodb://` or `mongodb+srv://`
- Require Atlas hosts containing `mongodb.net`
- Reject private or localhost targets
- Require username, password, and database name

#### Supabase PostgreSQL

- Accept only `postgresql://` or `postgres://`
- Require hosts containing `supabase`
- Reject private or localhost targets
- Enforce SSL in normalized connection strings

#### Files

- Accept CSV, Excel, and parquet
- Save file to `backend/storage/uploads`
- Query uploaded data via DuckDB in-memory sessions

### 4. Preview and Schema Guidance

- Backend introspects collections, tables, or file sheets
- Frontend previews rows and schema
- User can save:
  - selected tables
  - database description
  - table descriptions
  - field descriptions

Those notes are stored per session and injected into the compact analysis context.

### 5. Chat Analysis

LangGraph state:

1. `plan_query`
2. `execute_query`
3. `summarize_result`

Query style by source:

- MongoDB Atlas: aggregation pipeline JSON
- Supabase PostgreSQL: read-only SQL
- Files: read-only DuckDB SQL

The chat response returns:

- assistant text
- optional `viz_data`
- generated query preview
- recommended chart type

## Cost Control Strategy

### What does not use the LLM

- auth
- source validation
- encryption
- preview rows
- schema extraction
- chart rendering
- table/field note persistence

### What uses the LLM

- one query-planning call
- one answer-synthesis call

### Token Controls

- frontend token budget display
- backend approximate token limit per message
- in-memory per-provider request-per-minute and token-per-minute guards
- provider fallback across Groq key slots, then HuggingFace DeepSeek when the preferred provider is unavailable

## Visualization Design

- Frontend renders charts locally with Chart.js and Recharts
- Dropdown includes multiple chart types, including a custom 3D bar mode
- Hover tooltips show exact values
- Table fallback remains available for non-chartable results

## Security Notes

- Raw connection secrets are encrypted server-side
- Browser no longer stores raw database URLs for quick reconnect
- only approved hosts are accepted for live connectors
- localhost and private-network URIs are blocked
- SQL is restricted to read-only queries
- MongoDB write stages such as `$out` and `$merge` are blocked
- request logs are timestamped in IST for easier debugging

## Recommended Next Improvements

1. Add background schema snapshots for very large databases.
2. Add redis-backed token budgeting for multi-instance deployments.
3. Add unit tests for URI validation, schema merging, and SQL safety guards.
4. Add a saved-source delete endpoint and audit trail UI.
5. Add a frontend "This looks wrong" flag button with optional re-analysis.

## Query Validation and Error Recovery

### What does not use extra LLM calls

- Schema validation: column and table existence checks before execution
- Result sanity checks: detects all-zero results, single-row for plural questions, unrelated columns
- Graceful error recovery: catches DB execution errors and returns actionable messages
- Query plan caching: reuses successful plans for repeated questions

### What uses at most 1 extra LLM call (conditional)

- Retry with error feedback: if schema validation detects issues, the query is re-planned once with the specific validation errors injected into the prompt

### LLM self-check (zero extra calls)

- The query planner prompt now includes a `confidence` field (high/medium/low)
- Low-confidence plans trigger warnings in the user-facing response
- The prompt instructs the LLM to verify field names against the provided schema before writing the query

