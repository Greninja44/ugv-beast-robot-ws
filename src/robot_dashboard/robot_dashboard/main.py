"""Entry point: `ros2 run robot_dashboard dashboard` or `python -m robot_dashboard.main`."""
from __future__ import annotations

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .api import routes
from .core.config import load_settings
from .core.lifespan import make_lifespan

# index.html must never be cached: it references content-hashed asset filenames
# that change on every build, so a stale cached index.html points at JS/CSS
# files that no longer exist after a redeploy.
_NO_CACHE_HEADERS = {'Cache-Control': 'no-store'}


def create_app() -> FastAPI:
    settings = load_settings()
    app = FastAPI(title='robot_dashboard', version='0.1.0', lifespan=make_lifespan(settings))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=['*'],
        allow_headers=['*'],
    )
    routes.mount(app)  # /api/* and /ws — registered first, so they always win the match

    if settings.frontend_dir.is_dir():
        frontend_dir = settings.frontend_dir.resolve()
        index_file = frontend_dir / 'index.html'

        @app.get('/{full_path:path}')
        async def spa(full_path: str) -> FileResponse:
            """Serve the built SPA's static files directly, and fall back to
            index.html for CLIENT-SIDE ROUTES (e.g. /sensors, /teleop) so a hard
            refresh or direct link doesn't 404 — plain StaticFiles(html=True)
            only handles '/', not React Router paths.

            Requests for an actual asset (has a file extension, e.g.
            /assets/index-<hash>.js) that isn't found must 404 for real, NOT
            fall back to index.html — otherwise a browser holding a stale
            cached index.html (referencing a since-replaced hashed filename)
            gets HTML back where it expected JS, and the whole SPA fails to
            parse and mount (blank page after any redeploy)."""
            candidate = (frontend_dir / full_path).resolve()
            if frontend_dir in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
            last_segment = full_path.rsplit('/', 1)[-1]
            if '.' in last_segment:
                raise HTTPException(404, 'not found')
            return FileResponse(index_file, headers=_NO_CACHE_HEADERS)

    return app


def main() -> None:
    settings = load_settings()
    uvicorn.run(create_app(), host=settings.host, port=settings.port, log_level='info')


if __name__ == '__main__':
    main()
