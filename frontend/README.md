# Agent Chat Frontend

React + TypeScript (Vite) chat UI for the LangGraph agent backend in `backend/`.

## Features

- Token-level streaming responses (SSE) rendered as they arrive
- Thread sidebar backed by the backend's SQLite thread store
  (`GET/POST /chat`, `GET /threads`, `DELETE /threads/{id}`)
- Create new conversations, switch threads, delete threads
- Tool-call activity shown as chips inline with the response
- Vite dev proxy forwards `/api/*` to the FastAPI backend on `:8000`

## Run

Requires the backend running on `http://127.0.0.1:8000` (see `backend/README.md`).

```sh
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

## Production build

```sh
npm run build      # type-check (tsc) + bundle to dist/
npm run preview    # serve the production build locally
```

Serve the `dist/` folder from any static host, and point the API calls at the
backend (set `BASE` in `src/api.ts` if not proxied).