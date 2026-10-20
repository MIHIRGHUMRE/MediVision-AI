from __future__ import annotations

import hmac
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from backend.config import Settings, settings
from backend.database import Base, create_database_engine
from backend.workflow import (
    ALLOWED_REGIONS,
    WorkflowError,
    case_to_dict,
    create_case,
    get_case,
    list_cases,
    review_case as apply_review,
    save_draft as apply_draft,
    validate_image_name,
)


ROOT = Path(__file__).resolve().parent.parent


class DraftRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    indication: str = Field(default="", max_length=1000)
    findings: str = Field(min_length=1, max_length=10_000)
    impression: str = Field(min_length=1, max_length=5_000)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    action: Literal["sign", "return"]
    reviewer: str = Field(min_length=1, max_length=200)
    review_note: str = Field(default="", max_length=5_000)


def create_app(app_settings: Settings = settings) -> FastAPI:
    app_settings.validate()
    db_engine = create_database_engine(app_settings.database_url)
    session_factory = sessionmaker(
        bind=db_engine, autoflush=False, expire_on_commit=False
    )

    def request_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if app_settings.app_env in {"development", "test"}:
            Base.metadata.create_all(bind=db_engine)
        yield
        db_engine.dispose()

    application = FastAPI(
        title="MediVision AI Research Prototype",
        description=(
            "MRI-only research workflow scaffold. It does not analyze images or "
            "generate clinical findings."
        ),
        version="0.2.0",
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.db_engine = db_engine
    application.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")

    def custom_openapi() -> dict[str, Any]:
        if application.openapi_schema:
            return application.openapi_schema
        schema = get_openapi(
            title=application.title,
            version=application.version,
            description=application.description,
            routes=application.routes,
        )
        schema.setdefault("components", {}).setdefault("securitySchemes", {})[
            "BearerAuth"
        ] = {"type": "http", "scheme": "bearer"}
        for path, operations in schema["paths"].items():
            if path.startswith("/api/") and path not in {"/api/health", "/api/ready"}:
                for operation in operations.values():
                    operation["security"] = [{"BearerAuth": []}]
        application.openapi_schema = schema
        return schema

    application.openapi = custom_openapi

    @application.middleware("http")
    async def protect_api(request: Request, call_next):
        if request.url.path.startswith("/api/") and request.url.path not in {
            "/api/health",
            "/api/ready",
        }:
            supplied_key = request.headers.get("authorization", "")
            expected_key = f"Bearer {app_settings.api_key}"
            if not hmac.compare_digest(supplied_key, expected_key):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "A valid API access key is required."},
                    headers={"WWW-Authenticate": "Bearer"},
                )
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    request_bytes = int(content_length)
                except ValueError:
                    return JSONResponse(
                        status_code=400,
                        content={"detail": "Content-Length must be a valid integer."},
                    )
                if request_bytes > app_settings.max_upload_bytes + 1024 * 1024:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Request exceeds the configured upload limit."},
                    )

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
        )
        return response

    @application.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(ROOT / "frontend" / "index.html")

    @application.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": app_settings.app_env}

    @application.get("/api/ready")
    def readiness(session: Session = Depends(request_session)) -> dict[str, str]:
        try:
            session.execute(text("SELECT 1"))
        except Exception as error:
            raise HTTPException(status_code=503, detail="Database is unavailable.") from error
        return {"status": "ready"}

    @application.get("/api/cases")
    def cases(
        session: Session = Depends(request_session),
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[dict]:
        return [case_to_dict(case) for case in list_cases(session, limit=limit, offset=offset)]

    @application.post("/api/cases")
    def new_case(
        body_region: Annotated[str, Form()],
        files: Annotated[list[UploadFile], File()],
        session: Session = Depends(request_session),
    ) -> dict:
        if body_region.strip().lower() not in ALLOWED_REGIONS:
            raise HTTPException(status_code=422, detail="Choose a supported MRI body region.")
        if not files:
            raise HTTPException(status_code=422, detail="Upload at least one MRI image file.")
        if len(files) > app_settings.upload_file_limit:
            raise HTTPException(
                status_code=413,
                detail=f"Upload no more than {app_settings.upload_file_limit} files per case.",
            )

        image_metadata: list[dict[str, str | int]] = []
        total_bytes = 0
        try:
            for upload in files:
                try:
                    image_format = validate_image_name(upload.filename)
                except WorkflowError as error:
                    raise HTTPException(status_code=422, detail=str(error)) from error

                file_bytes = 0
                while chunk := upload.file.read(1024 * 1024):
                    file_bytes += len(chunk)
                    total_bytes += len(chunk)
                    if total_bytes > app_settings.max_upload_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail="Upload exceeds the configured total size limit.",
                        )
                if file_bytes == 0:
                    raise HTTPException(
                        status_code=422, detail="Uploaded image files cannot be empty."
                    )
                image_metadata.append({"format": image_format, "bytes": file_bytes})
        finally:
            for upload in files:
                upload.file.close()

        case = create_case(session, body_region, image_metadata)
        return case_to_dict(case)

    @application.get("/api/cases/{case_id}")
    def case_detail(
        case_id: str, session: Session = Depends(request_session)
    ) -> dict:
        try:
            return case_to_dict(get_case(session, case_id))
        except WorkflowError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @application.post("/api/cases/{case_id}/draft")
    def draft(
        case_id: str,
        request: DraftRequest,
        session: Session = Depends(request_session),
    ) -> dict:
        try:
            case = apply_draft(
                session,
                case_id,
                request.indication,
                request.findings,
                request.impression,
            )
            return case_to_dict(case)
        except WorkflowError as error:
            status_code = 404 if str(error) == "Case not found." else 409
            raise HTTPException(status_code=status_code, detail=str(error)) from error

    @application.post("/api/cases/{case_id}/review")
    def review(
        case_id: str,
        request: ReviewRequest,
        session: Session = Depends(request_session),
    ) -> dict:
        try:
            case = apply_review(
                session,
                case_id,
                request.action,
                request.reviewer,
                request.review_note,
            )
            return case_to_dict(case)
        except WorkflowError as error:
            status_code = 404 if str(error) == "Case not found." else 409
            raise HTTPException(status_code=status_code, detail=str(error)) from error

    return application


app = create_app()
