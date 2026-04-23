# Quickstart

The fastest way to run the product is the bundled Docker Compose stack. If you are working from source, use the repo verification script first and then start backend and frontend in separate terminals.

## Fast path: Docker Compose

```bash
git clone https://github.com/brownjuly2003-code/ab-test-research-designer.git
cd ab-test-research-designer
docker compose up --build
```

Open the local app at `http://127.0.0.1:8008`.

Useful checks:

- App: `http://127.0.0.1:8008`
- Health: `http://127.0.0.1:8008/health`
- Readiness: `http://127.0.0.1:8008/readyz`
- FastAPI docs: `http://127.0.0.1:8008/docs`

## Source checkout path

Prerequisites:

- Python 3.11+
- Node.js LTS

Install dependencies once:

```bash
python -m pip install -r app/backend/requirements.txt
npm --prefix app/frontend ci
```

Run the repo's cross-platform verification wrapper without rebuilding frontend assets:

```bash
python scripts/verify_all.py --skip-build
```

Start the backend:

```bash
python -m uvicorn app.backend.app.main:app --host 127.0.0.1 --port 8008
```

Start the frontend dev server:

```bash
npm --prefix app/frontend run dev
```

Open:

- Frontend dev UI: `http://127.0.0.1:5173`
- Backend API: `http://127.0.0.1:8008`

## First things to try

1. Open the sample wizard payload from `docs/demo/sample-project.json`.
2. Run sizing for the default checkout conversion example.
3. Switch the analysis mode to Bayesian or increase `n_looks` to surface the extra guidance blocks.
