# DataSage Backend

FastAPI backend for the attached `frontend` app. It provides:

- JWT auth with register, login, refresh, and `me`
- Per-user sessions stored in MongoDB
- Secure data-source connections for MongoDB Atlas and Supabase PostgreSQL
- CSV, Excel, and parquet uploads for chat analysis
- Schema preview plus database/table/field descriptions saved per session
- LangGraph-based query planning and answer synthesis with Groq key-pool fallback or HuggingFace DeepSeek
- Open-source SentenceTransformer embeddings for semantic session memory
- IST-aware request and application logging

## Quick Startdb 

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill in:

- `MONGODB_URI`
- `MONGODB_DATABASE`
- `JWT_SECRET_KEY`
- `JWT_REFRESH_SECRET_KEY`
- `ENCRYPTION_KEY`
- `GROQ_API_KEY_1` through `GROQ_API_KEY_10` and/or `HUGGINGFACE_API_KEY`

4. Run the API:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

5. In `frontend`, point `NEXT_PUBLIC_API_URL` at `http://127.0.0.1:8000`.

## Notes

- Connection URIs are validated before connect and stored encrypted on the server.
- Raw database URLs are no longer saved in browser storage.
- User prompts are limited with an approximate token budget before LLM calls are made.
- Semantic memory uses `MEMORY_EMBEDDING_MODEL` (default: `sentence-transformers/all-MiniLM-L6-v2`) and `MEMORY_EMBEDDING_DIMENSIONS` (default: `384`). The model downloads from Hugging Face on first use unless it is already cached locally.
- Frontend production build was validated successfully with `npm run build`.
