# DataSage V2

Monorepo containing:
- `backend/`: FastAPI backend
- `frontend/`: Next.js frontend

## Quick start

### Backend

1. Create `backend/.env` from `backend/.env.example`
2. Create and activate a virtual environment
3. Install deps: `pip install -r backend/requirements.txt`
4. Run API: `uvicorn main:app --reload` (from `backend/`)

### Frontend

1. Install deps: `npm install` (from `frontend/`)
2. Run dev server: `npm run dev`

## Notes

- Secrets are intentionally not committed. Use the `.env.example` templates.
- Uploaded files are stored under `backend/storage/uploads/` and are ignored by Git.
