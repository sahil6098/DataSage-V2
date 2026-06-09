# 🧠 DataSage V2

> **AI-powered analytics copilot** — connect your databases and files, then ask questions in plain English. DataSage queries your data, detects anomalies, forecasts trends, and renders interactive charts — all in a real-time streaming chat interface.

---

## ✨ Features

| Category | Capability |
|---|---|
| **Data Sources** | CSV, Excel, Parquet file upload · MongoDB Atlas · PostgreSQL (Supabase & self-hosted) · Public Google Sheets |
| **AI Chat** | Natural-language queries over your data using a LangGraph pipeline |
| **Visualizations** | Auto-generated bar, line, pie, scatter, area & table charts via Recharts |
| **Anomaly Detection** | Three-method statistical analysis (Modified Z-Score, IQR Tukey fence, Grubbs test) with severity tiers & confidence scores |
| **Time-Series Forecasting** | AIC-selected Exponential Smoothing (ETS) with walk-forward cross-validation, 90% confidence intervals, and linear regression fallback |
| **Data Quality Reports** | Automated per-table quality scoring on file uploads (null rates, uniqueness, type consistency) |
| **PDF Reports** | Full session chat report exportable as a PDF |
| **Session Memory** | Persistent conversational memory with semantic vector search (sentence-transformers + MongoDB Atlas Vector Search) |
| **Multi-Provider LLM** | Groq (up to 10 pooled API key slots) + DeepSeek via HuggingFace — automatic failover and rate-limit management |
| **Saved Source Library** | Encrypted database credentials saved per user for one-click reconnect |
| **Auth** | JWT access + refresh token authentication with bcrypt password hashing |

---

## 🏗️ Architecture

```
datasage-v2/
├── backend/                 # FastAPI + Python
│   ├── app/
│   │   ├── api/
│   │   │   └── routers/     # auth · chat · connectors · sessions
│   │   ├── core/            # config · logging · security
│   │   ├── db/              # MongoDB async motor client
│   │   ├── models/          # ODM models
│   │   ├── schemas/         # Pydantic request/response schemas
│   │   ├── services/        # Business logic (see below)
│   │   └── utils/           # Helpers (tabular, serialization, time, URI validation)
│   ├── storage/uploads/     # Uploaded files (git-ignored)
│   ├── tests/               # pytest test suite
│   └── requirements.txt
│
└── frontend/                # Next.js 16 + React 19 + TypeScript
    └── src/
        ├── app/             # Next.js App Router pages (home · login · register · chat)
        ├── components/      # UI components (see below)
        └── lib/             # API client (axios)
```

### Backend Services

| Service | Responsibility |
|---|---|
| `chat_service.py` | LangGraph-based analysis pipeline — intent classification, query planning, execution, streaming, follow-up suggestions, query plan caching |
| `connector_service.py` | Data source connection management — MongoDB, PostgreSQL, CSV/Excel/Parquet, Google Sheets, schema introspection, encrypted credential storage |
| `llm_service.py` | Multi-provider LLM abstraction — round-robin Groq slots, DeepSeek fallback, rate-limit tracking, token budget management, JSON repair |
| `memory_service.py` | Session memory — Atlas Vector Search → local cosine fallback → keyword fallback, embedding via `all-MiniLM-L6-v2` |
| `anomaly_service.py` | Statistical outlier detection — Modified Z-Score (MAD), IQR fence, Grubbs test with majority-vote confidence |
| `forecast_service.py` | Time-series forecasting — AIC-selected ETS, walk-forward CV, expanding confidence intervals, linear regression fallback |
| `report_service.py` | PDF report generation via ReportLab |
| `quality_service.py` | Dataset quality scoring on file upload |
| `session_service.py` | Chat session CRUD and data source state management |
| `auth_service.py` | User registration, login, token refresh, logout (revokes tokens + disconnects DB sessions) |
| `token_budget_service.py` | In-memory RPM/TPM/RPD budget tracking per LLM provider slot |

### Frontend Components

| Component | Description |
|---|---|
| `ChatMessage.tsx` | Rich message renderer — markdown, interactive charts (bar/line/pie/scatter/area/table), anomaly cards, forecast overlays, follow-up chips |
| `DataSourcePreview.tsx` | Schema browser with table selection, per-field descriptions, data preview, quality report panel |
| `ConnectorModal.tsx` | Multi-mode connector UI — file upload, database connection (MongoDB/PostgreSQL), Google Sheets import, saved source library |
| `Sidebar.tsx` | Session list with create/delete, data source badges |
| `AnimatedBackground.tsx` | Animated canvas background |
| `AuthGuard.tsx` | JWT-aware route protection |
| `BrandLogo.tsx` | SVG brand logo |

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.11+**
- **Node.js 18+** and npm
- A **MongoDB Atlas** cluster (free tier works) — required for user auth and session storage
- At least one **Groq API key** (free at [console.groq.com](https://console.groq.com))

---

### 1 · Backend Setup

```bash
# From the project root
cd backend

# Create and activate a virtual environment
python -m venv ../venv
# Windows
..\venv\Scripts\activate
# macOS / Linux
source ../venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**Configure environment variables** — copy and edit the `.env` file:

```bash
# The .env file already exists at backend/.env
# Edit the values marked below
```

Key variables to set:

```env
# MongoDB
MONGODB_URI=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/
MONGODB_DATABASE=datasage

# JWT secrets (change these!)
JWT_SECRET_KEY=your-secret-key-here
JWT_REFRESH_SECRET_KEY=your-refresh-secret-here

# Encryption key for stored DB credentials (change this!)
ENCRYPTION_KEY=your-32-char-encryption-key-here

# Groq API keys (add up to 10 slots for pooling)
GROQ_API_KEY_1=gsk_...
GROQ_MODEL_1=llama-3.3-70b-versatile

# Optional: DeepSeek via HuggingFace as fallback
HUGGINGFACE_API_KEY=hf_...

# Optional: OpenRouter key for PDF report generation
OPENROUTER_REPORT_API_KEY=sk-or-...
```

**Run the API server:**

```bash
# From backend/
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API will be available at `http://127.0.0.1:8000`. Interactive docs at `http://127.0.0.1:8000/docs`.

---

### 2 · Frontend Setup

```bash
# From the project root
cd frontend

# Install dependencies
npm install

# Run the dev server
npm run dev
```

The app will be available at `http://localhost:3000`.

> **Note:** The frontend expects the backend at `http://127.0.0.1:8000`. Adjust the API base URL in `frontend/src/lib/` if your backend runs elsewhere.

---

## ⚙️ Configuration Reference

### LLM Provider Pooling

DataSage supports up to **10 Groq API key slots** to work around free-tier rate limits. The service automatically rotates between slots based on current usage and cools down rate-limited slots:

```env
GROQ_API_KEY_1=gsk_...
GROQ_MODEL_1=llama-3.3-70b-versatile

GROQ_API_KEY_2=gsk_...
GROQ_MODEL_2=llama-3.3-70b-versatile

# ... up to GROQ_API_KEY_10
```

Rate-limit budgets (conservative defaults for free tier):

```env
GROQ_REQUESTS_PER_MINUTE=28
GROQ_TOKENS_PER_MINUTE=10000
GROQ_REQUESTS_PER_DAY=950
GROQ_TOKENS_PER_DAY=95000
```

### Session Memory & Vector Search

Chat memory uses `sentence-transformers/all-MiniLM-L6-v2` embeddings stored in MongoDB. For best recall, create an Atlas Vector Search index on the `chat_vectors` collection:

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
      "numDimensions": 384,
      "similarity": "cosine"
    },
    { "type": "filter", "path": "user_id" },
    { "type": "filter", "path": "session_id" },
    { "type": "filter", "path": "embedding_model" }
  ]
}
```

Index name must match `MEMORY_VECTOR_INDEX_NAME` (default: `chat_vectors_index`).

> If the Atlas index is not configured, the system gracefully falls back to local cosine search and then keyword matching.

### File Upload

```env
UPLOAD_DIR=backend/storage/uploads   # relative to project root
MAX_UPLOAD_SIZE_MB=25
```

Uploaded files are stored locally and are git-ignored.

---

## 🔌 API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/register` | Create a new account |
| `POST` | `/auth/login` | Login and receive JWT tokens |
| `POST` | `/auth/refresh` | Refresh access token |
| `POST` | `/auth/logout` | Revoke refresh token + disconnect all DB sessions |
| `GET` | `/auth/me` | Get current user profile |
| `GET` | `/sessions` | List all chat sessions |
| `POST` | `/sessions` | Create a new session |
| `DELETE` | `/sessions/{id}` | Delete a session |
| `POST` | `/chat/{session_id}/stream` | **SSE** — stream chat response |
| `GET` | `/chat/{session_id}/report` | Download session PDF report |
| `POST` | `/connectors/{session_id}/connect` | Connect a database (MongoDB/PostgreSQL) |
| `POST` | `/connectors/{session_id}/upload` | Upload a file (CSV/Excel/Parquet) |
| `POST` | `/connectors/{session_id}/google-sheet` | Import a public Google Sheet |
| `POST` | `/connectors/{session_id}/connect/saved/{id}` | Connect from saved library |
| `POST` | `/connectors/{session_id}/connect/last` | Reconnect last data source |
| `GET` | `/connectors/{session_id}/schema` | Get schema of connected source |
| `GET` | `/connectors/{session_id}/preview/{table}` | Preview table rows |
| `PATCH` | `/connectors/{session_id}/schema-context` | Update table/field descriptions |
| `DELETE` | `/connectors/{session_id}/disconnect` | Disconnect current source |
| `GET` | `/connectors/{session_id}/quality` | Get dataset quality report |
| `GET` | `/connectors/library` | List saved data sources |
| `GET` | `/health` | Health check |

---

## 🧪 Running Tests

```bash
cd backend
pytest tests/ -v
```

Test files cover: chat session history, visualization intent classification, result sanity checks, CSV SQL query repairs, MongoDB connector, Google Sheets connector, and report generation.

---

## 🛠️ Tech Stack

### Backend
| Technology | Version | Purpose |
|---|---|---|
| FastAPI | 0.116 | Web framework |
| Uvicorn | 0.35 | ASGI server |
| Motor | 3.7 | Async MongoDB driver |
| LangGraph | 0.6 | AI pipeline orchestration |
| LangChain Groq | 0.3 | Groq LLM integration |
| LangChain HuggingFace | 0.1+ | DeepSeek/HF LLM integration |
| Sentence Transformers | 3.0+ | Memory embeddings (`all-MiniLM-L6-v2`) |
| DuckDB | 1.3 | In-process SQL engine for file queries |
| SQLAlchemy + psycopg | 2.0 | PostgreSQL connectivity |
| PyMongo | 4.15 | MongoDB aggregation pipeline execution |
| Pandas | 2.3 | Tabular file parsing |
| statsmodels | 0.14+ | ETS time-series forecasting |
| scipy | 1.11+ | Grubbs test, linear regression fallback |
| ReportLab | 4.2 | PDF generation |
| Pydantic | v2 | Data validation and settings |
| python-jose | 3.5 | JWT tokens |
| passlib[bcrypt] | 1.7 | Password hashing |

### Frontend
| Technology | Version | Purpose |
|---|---|---|
| Next.js | 16.2 | React framework (App Router) |
| React | 19 | UI library |
| TypeScript | 5 | Type safety |
| Recharts | 3.8 | Data visualization |
| Chart.js | 4.5 | Secondary chart support |
| Axios | 1.15 | HTTP client |
| Lucide React | 1.8 | Icon set |
| Rive | 4.28 | Animated graphics |

---

## 📁 Project Notes

- **Secrets are not committed.** Always set `JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY`, and `ENCRYPTION_KEY` to strong, unique values in production.
- **Uploaded files** are stored at `backend/storage/uploads/` and are git-ignored. Back up this directory if persistence is needed.
- **Groq free tier** allows ~1,000 requests/day per key. Use the key pool feature to maximize throughput without paying.
- **MongoDB Atlas free tier** (M0) is sufficient to run DataSage, including vector search (requires M10+ or Atlas Search, or use local cosine fallback).
- The frontend dev server proxies API calls; for production, configure a reverse proxy (nginx, Caddy, etc.) in front of both services.

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.
