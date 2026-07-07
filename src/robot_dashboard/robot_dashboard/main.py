"""Entry point: `ros2 run robot_dashboard dashboard` or `python -m robot_dashboard.main`."""
from __future__ import annotations

import os
from pathlib import Path

# Must run before rclpy is imported anywhere below (routes -> ros/bridge pulls it
# in transitively) — RMW_IMPLEMENTATION is read when the DDS layer is loaded, not
# lazily per-call. Whoever launches this process (a bare `ros2 run`, a manual
# restart, docker exec without sourcing .bashrc, ...) may not have exported the
# shared CycloneDDS/domain-42 config that every other robot_ws node uses; without
# this, the dashboard silently lands on ROS2's plain defaults (rmw_fastrtps_cpp,
# domain 0) and ends up in a completely separate, undiscoverable DDS graph from
# everything else on the Pi — including anything IT launches via launch_manager
# (base bringup, SLAM, Nav2, explore), since those inherit this process's own
# environment. setdefault, not overwrite: an explicit export from the caller still
# wins, this is only a floor.
os.environ.setdefault('RMW_IMPLEMENTATION', 'rmw_cyclonedds_cpp')
os.environ.setdefault('ROS_DOMAIN_ID', '42')
os.environ.setdefault('ROS_LOCALHOST_ONLY', '0')

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
            # normpath (lexical), NOT resolve() (follows symlinks): under colcon
            # --symlink-install the dist/assets/*.js files are symlinks back into
            # src/, so resolve() would move the real path outside frontend_dir and
            # the containment guard below would reject every legit asset (blank
            # page). normpath still collapses any '..' traversal — the actual
            # security concern here — without following the asset symlinks out.
            candidate = Path(os.path.normpath(frontend_dir / full_path))
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
