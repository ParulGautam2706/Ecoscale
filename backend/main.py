import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

import app.models  # noqa: F401  (register tables)
from app.api.v1 import auth, catalog, dashboard, insights, ml, optimization, telemetry
from app.core.config import settings
from app.core.ratelimit import limiter
from app.database.session import Base, engine
from app.monitoring import prometheus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("greencloud")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)  # dev convenience; Alembic is the real migration path
    yield


app = FastAPI(title=settings.app_name, version="2.0.0", lifespan=lifespan,
              description="Explainable, carbon-aware cloud optimization. Values are labelled measured / estimated / simulated / predicted.")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])
for r in (auth, catalog, dashboard, telemetry, ml, optimization, insights):
    app.include_router(r.router, prefix="/api/v1")


@app.exception_handler(ValueError)
async def value_error(_: Request, exc: ValueError):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(LookupError)
async def lookup_error(_: Request, exc: LookupError):
    return JSONResponse({"detail": str(exc)}, status_code=404)


@app.exception_handler(FileNotFoundError)
async def model_missing(_: Request, exc: FileNotFoundError):
    return JSONResponse({"detail": str(exc)}, status_code=409)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


@app.get("/api/v1/health", tags=["system"])
def health():
    return {"status": "ok", "data_mode": settings.data_mode, "version": app.version}


@app.get("/metrics", tags=["system"], include_in_schema=False)
def metrics():
    return Response(prometheus.render(), media_type="text/plain; version=0.0.4")
