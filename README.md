# DataSage V2

DataSage V2 is an AI-powered analytics copilot for connected databases and uploaded files. It lets users ask questions in plain English, inspect source schemas, generate charts, detect anomalies, forecast time series, and export session reports from a real-time chat interface.

## Features

| Category | Capability |
| --- | --- |
| Data sources | CSV, Excel, Parquet uploads, MongoDB Atlas, PostgreSQL, Supabase, self-hosted Postgres, and public Google Sheets |
| AI chat | Natural-language analysis over connected data through a LangGraph pipeline |
| Visualizations | Auto-generated bar, line, pie, scatter, area, and table views |
| Anomaly detection | Modified Z-score, IQR Tukey fence, and Grubbs-test analysis with severity and confidence scoring |
| Forecasting | AIC-selected ETS forecasting with walk-forward validation, confidence intervals, and linear-regression fallback |
| Data quality | Automated table-level quality scoring for uploaded datasets |
| Session memory | Persistent chat history with semantic vector recall and fallback search |
| Reports | Exportable PDF reports for chat sessions |
| LLM providers | Groq key pooling with Hugging Face DeepSeek fallback support |
| Saved sources | Encrypted saved connection library for reconnecting data sources |
| Auth | JWT access and refresh tokens with bcrypt password hashing |

## Architecture

```text
datasage-v2/
|-- backend/                 # FastAPI + Python API
|   |-- app/
|   |   |-- api/routers/     # auth, chat, connectors, sessions
|   |   |-- core/            # config, logging, security
|   |   |-- db/              # MongoDB async Motor client
|   |   |-- models/          # ODM models
|   |   |-- schemas/         # Pydantic request/response schemas
|   |   |-- services/        # Business logic and AI/data services
|   |   `-- utils/           # Helpers for tabular data, serialization, time, URI validation
|   |-- storage/uploads/     # Uploaded files, git-ignored
|   |-- tests/               # Pytest suite
|   `-- requirements.txt
|
|-- frontend/                # Next.js 16 + React 19 + TypeScript app
|   |-- public/
|   |-- src/
|   |   |-- app/             # App Router pages
|   |   |-- components/      # Chat, connector, sidebar, auth, brand, and visualization UI
|   |   `-- lib/             # API client helpers
|   |-- package.json
|   `-- next.config.ts
|
`-- docs/
    `-- system-design.md
```

## Backend Services

| Service | Responsibility |
| --- | --- |
| `chat_service.py` | LangGraph analysis flow, intent classification, query planning, execution, streaming, follow-up suggestions, and query-plan caching |
| `connector_service.py` | MongoDB, PostgreSQL, CSV, Excel, Parquet, Google Sheets, schema introspection, and encrypted credential storage |
| `llm_service.py` | Multi-provider LLM abstraction, Groq slot rotation, DeepSeek fallback, rate-limit handling, token budgeting, and JSON repair |
| `memory_service.py` | Session memory with Atlas Vector Search, local cosine fallback, keyword fallback, and `all-MiniLM-L6-v2` embeddings |
| `anomaly_service.py` | Statistical outlier detection with modified Z-score, IQR fences, and Grubbs test |
| `forecast_service.py` | Time-series forecasting with ETS selection, walk-forward validation, confidence intervals, and fallback regression |
| `report_service.py` | PDF report generation with ReportLab |
| `quality_service.py` | Dataset quality scoring for uploaded files |
| `session_service.py` | Chat session CRUD and data-source state management |
| `auth_service.py` | Registration, login, refresh, logout, token revocation, and DB session cleanup |
| `token_budget_service.py` | In-memory RPM, TPM, RPD, and TPD budget tracking per provider slot |

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- MongoDB Atlas or a local MongoDB instance for auth, sessions, saved sources, and memory
- At least one Groq API key from [console.groq.com](https://console.groq.com)

### Backend Setup

```bash
cd backend

python -m venv ../venv

# Windows
../venv/Scripts/activate

# macOS / Linux
source ../venv/bin/activate

pip install -r requirements.txt
```

Create or update `backend/.env`:

```env
APP_NAME=DataSage API
ENVIRONMENT=development
DEBUG=true
API_HOST=127.0.0.1
API_PORT=8000

MONGODB_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/
MONGODB_DATABASE=datasage

JWT_SECRET_KEY=replace-with-a-strong-secret
JWT_REFRESH_SECRET_KEY=replace-with-a-strong-refresh-secret
ENCRYPTION_KEY=replace-with-a-strong-encryption-key

GROQ_API_KEY_1=gsk_...
GROQ_MODEL_1=llama-3.3-70b-versatile

# Optional DeepSeek fallback through Hugging Face
HUGGINGFACE_API_KEY=hf_...
HUGGINGFACE_API_BASE=https://router.huggingface.co/v1
HUGGINGFACE_DEEPSEEK_MODEL=deepseek-ai/DeepSeek-V4-Flash

# Optional report-generation provider
OPENROUTER_REPORT_API_KEY=sk-or-...
OPENROUTER_REPORT_MODEL=openai/gpt-oss-20b:free
```

Run the API:

```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API runs at `http://127.0.0.1:8000`, with interactive docs at `http://127.0.0.1:8000/docs`.

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:3000`.

The frontend is configured for a backend at `http://127.0.0.1:8000`. Update the API client under `frontend/src/lib/` if your API is hosted elsewhere.

## Configuration Notes

### Groq Key Pooling

DataSage can rotate across up to 10 Groq API key slots:

```env
GROQ_API_KEY_1=gsk_...
GROQ_MODEL_1=llama-3.3-70b-versatile

GROQ_API_KEY_2=gsk_...
GROQ_MODEL_2=llama-3.3-70b-versatile

# Continue through GROQ_API_KEY_10 / GROQ_MODEL_10 as needed.
```

Default budget controls:

```env
GROQ_REQUESTS_PER_MINUTE=28
GROQ_TOKENS_PER_MINUTE=6000
GROQ_REQUESTS_PER_DAY=950
GROQ_TOKENS_PER_DAY=0

DEEPSEEK_REQUESTS_PER_MINUTE=5
DEEPSEEK_TOKENS_PER_MINUTE=8000
DEEPSEEK_REQUESTS_PER_DAY=0
DEEPSEEK_TOKENS_PER_DAY=0
```

### Session Memory and Vector Search

Chat memory uses `sentence-transformers/all-MiniLM-L6-v2` embeddings with 384 dimensions. For best recall, create a MongoDB Atlas Vector Search index on the `chat_vectors` collection:

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

The index name must match `MEMORY_VECTOR_INDEX_NAME`, which defaults to `chat_vectors_index`.

If Atlas Vector Search is unavailable, the memory service falls back to local cosine search and then keyword matching.

### File Uploads

```env
UPLOAD_DIR=backend/storage/uploads
MAX_UPLOAD_SIZE_MB=25
PREVIEW_ROW_LIMIT=200
MAX_CHAT_RESULT_ROWS=200
```

Uploaded files are stored locally and are ignored by git.

## API Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/auth/register` | Create an account |
| `POST` | `/auth/login` | Log in and receive JWT tokens |
| `POST` | `/auth/refresh` | Refresh an access token |
| `POST` | `/auth/logout` | Revoke refresh token and disconnect DB sessions |
| `GET` | `/auth/me` | Get the current user profile |
| `GET` | `/sessions` | List chat sessions |
| `POST` | `/sessions` | Create a session |
| `GET` | `/sessions/{id}` | Get a session by ID |
| `DELETE` | `/sessions/{id}` | Delete a session |
| `POST` | `/chat/{session_id}/stream` | Stream an AI chat response with SSE |
| `GET` | `/chat/{session_id}/report` | Download a session PDF report |
| `POST` | `/connectors/{session_id}/connect` | Connect a MongoDB or PostgreSQL database |
| `POST` | `/connectors/{session_id}/upload` | Upload a CSV, Excel, or Parquet file |
| `POST` | `/connectors/{session_id}/google-sheet` | Import a public Google Sheet |
| `POST` | `/connectors/{session_id}/connect/saved/{id}` | Connect from the saved-source library |
| `POST` | `/connectors/{session_id}/connect/last` | Reconnect the last data source |
| `GET` | `/connectors/{session_id}/schema` | Get the connected source schema |
| `GET` | `/connectors/{session_id}/preview/{table}` | Preview table rows |
| `PATCH` | `/connectors/{session_id}/schema-context` | Update table and field descriptions |
| `DELETE` | `/connectors/{session_id}/disconnect` | Disconnect the current source |
| `GET` | `/connectors/{session_id}/quality` | Get a dataset quality report |
| `GET` | `/connectors/library` | List saved data sources |
| `GET` | `/health` | Health check |

## Tests

```bash
cd backend
pytest tests/ -v
```

The backend tests cover chat session history, visualization intent classification, result sanity checks, CSV SQL repairs, MongoDB connection behavior, Google Sheets import behavior, and PDF report generation.

## Tech Stack

### Backend

| Technology | Version | Purpose |
| --- | --- | --- |
| FastAPI | 0.116.1 | Web framework |
| Uvicorn | 0.35.0 | ASGI server |
| Motor | 3.7.1 | Async MongoDB driver |
| PyMongo | 4.15.0 | MongoDB queries and aggregation |
| Pydantic Settings | 2.11.0 | Environment configuration |
| LangGraph | 0.6.6 | AI workflow orchestration |
| LangChain Groq | 0.3.8 | Groq LLM integration |
| LangChain Hugging Face | 0.1.2+ | Hugging Face / DeepSeek integration |
| Sentence Transformers | 3.0+ | Semantic memory embeddings |
| DuckDB | 0.10.3 | In-process SQL over uploaded files |
| SQLAlchemy | 2.0.43 | PostgreSQL connectivity |
| psycopg | 3.2.10 | PostgreSQL driver |
| Pandas | 2.3.2 | Tabular data loading and processing |
| statsmodels | 0.14+ | ETS forecasting |
| SciPy | 1.11+ | Statistical tests and regression fallback |
| ReportLab | 4.2.5 | PDF generation |
| python-jose | 3.5.0 | JWT handling |
| passlib[bcrypt] | 1.7.4 | Password hashing |

### Frontend

| Technology | Version | Purpose |
| --- | --- | --- |
| Next.js | 16.2.4 | React framework with App Router |
| React | 19.2.4 | UI library |
| TypeScript | 5.x | Type safety |
| Recharts | 3.8.1 | Primary chart rendering |
| Chart.js | 4.5.1 | Secondary chart support |
| Axios | 1.15.0 | API client |
| Lucide React | 1.8.0 | Icon library |
| Rive React Canvas | 4.28.1 | Animated graphics |

## Project Notes

- Do not commit secrets. Use strong unique values for `JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY`, and `ENCRYPTION_KEY`.
- Uploaded files live under `backend/storage/uploads/` and should be backed up separately if persistence matters.
- MongoDB Atlas free-tier storage is enough for core app data. Atlas Vector Search may require additional Atlas Search support; the app includes fallback recall paths.
- For production, run the backend and frontend behind a reverse proxy or deployment platform, set `ENVIRONMENT=production`, disable debug mode, and configure allowed CORS origins.

## License

MIT. See [LICENSE](LICENSE) for details.
