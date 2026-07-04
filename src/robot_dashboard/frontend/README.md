# robot_dashboard frontend

React + TypeScript + Vite single-page app for the UGV Beast dashboard. See the
[top-level README](../../../README.md) for the full project overview, architecture, and setup guide.

## Develop

```bash
npm install
npm run dev
```

By default this expects the backend at `http://localhost:8080` (see `dashboard.yaml`'s
`cors_origins` and the frontend's API base URL config).

## Build

```bash
npm run build
```

Outputs to `dist/`, served by the FastAPI backend in production.
