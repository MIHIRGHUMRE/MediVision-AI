from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import AuditEvent, CaseRecord


ALLOWED_REGIONS = {"brain", "spine", "knee", "other"}
ALLOWED_IMAGE_SUFFIXES = (".dcm", ".nii", ".nii.gz", ".png", ".jpg", ".jpeg")


class WorkflowError(ValueError):
    pass


def validate_region(body_region: str) -> str:
    normalized = body_region.strip().lower()
    if normalized not in ALLOWED_REGIONS:
        raise WorkflowError("Choose brain, spine, knee, or other as the MRI body region.")
    return normalized


def validate_image_name(filename: str | None) -> str:
    safe_name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    if not safe_name.endswith(ALLOWED_IMAGE_SUFFIXES):
        raise WorkflowError("Use a DICOM, NIfTI, PNG, or JPEG MRI file.")
    if safe_name.endswith(".nii.gz"):
        return "nii.gz"
    return safe_name.rsplit(".", 1)[-1]


def render_report(case: CaseRecord) -> str | None:
    if case.report_status is None:
        return None
    return (
        f"INDICATION\n{case.indication}\n\n"
        f"FINDINGS\n{case.findings}\n\n"
        f"IMPRESSION\n{case.impression}\n\n"
        "URGENCY\nNot assessed — radiologist review required"
    )


def case_to_dict(case: CaseRecord) -> dict[str, Any]:
    return {
        "id": case.id,
        "body_region": case.body_region,
        "created_at": _utc_isoformat(case.created_at),
        "images": case.images,
        "report": (
            {
                "indication": case.indication,
                "findings": case.findings,
                "impression": case.impression,
                "urgency": "Not assessed — radiologist review required",
                "status": case.report_status,
                "reviewer": case.reviewer,
                "review_note": case.review_note,
                "reviewed_at": (
                    _utc_isoformat(case.reviewed_at) if case.reviewed_at else None
                ),
            }
            if case.report_status
            else None
        ),
        "report_text": render_report(case),
        "version": case.version,
    }


def _utc_isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def create_case(
    session: Session, body_region: str, images: list[dict[str, str | int]]
) -> CaseRecord:
    case = CaseRecord(
        id=str(uuid4()),
        body_region=validate_region(body_region),
        created_at=datetime.now(timezone.utc),
        images=images,
    )
    session.add(case)
    session.flush()
    return case


def get_case(session: Session, case_id: str, *, for_update: bool = False) -> CaseRecord:
    statement = select(CaseRecord).where(CaseRecord.id == case_id)
    if for_update:
        statement = statement.with_for_update()
    case = session.scalar(statement)
    if case is None:
        raise WorkflowError("Case not found.")
    return case


def list_cases(
    session: Session, *, limit: int = 50, offset: int = 0
) -> list[CaseRecord]:
    statement = (
        select(CaseRecord)
        .order_by(CaseRecord.created_at.desc(), CaseRecord.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement))


def save_draft(
    session: Session,
    case_id: str,
    indication: str,
    findings: str,
    impression: str,
    *,
    actor: str = "user",
) -> CaseRecord:
    case = get_case(session, case_id, for_update=True)
    if case.report_status == "signed":
        raise WorkflowError("A signed report cannot be edited.")
    if not findings.strip() or not impression.strip():
        raise WorkflowError("Findings and impression are required.")
    case.indication = indication.strip() or "Not provided"
    case.findings = findings.strip()
    case.impression = impression.strip()
    case.report_status = "pending_review"
    case.reviewer = None
    case.review_note = None
    case.reviewed_at = None
    case.version += 1
    session.add(
        AuditEvent(
            case_id=case.id,
            event_type="draft_saved",
            actor=actor,
            details={"version": case.version},
        )
    )
    session.flush()
    return case


def review_case(
    session: Session,
    case_id: str,
    action: Literal["sign", "return"],
    reviewer: str,
    review_note: str = "",
) -> CaseRecord:
    case = get_case(session, case_id, for_update=True)
    if case.report_status != "pending_review":
        raise WorkflowError("Only a pending report can be reviewed.")
    if not reviewer.strip():
        raise WorkflowError("Reviewer name is required.")
    if action == "return" and not review_note.strip():
        raise WorkflowError("Add a note when returning a report.")
    if action not in {"sign", "return"}:
        raise WorkflowError("Action must be sign or return.")
    case.report_status = "signed" if action == "sign" else "returned"
    case.reviewer = reviewer.strip()
    case.review_note = review_note.strip() or None
    case.reviewed_at = datetime.now(timezone.utc)
    case.version += 1
    session.add(
        AuditEvent(
            case_id=case.id,
            event_type=f"report_{action}ed" if action == "return" else "report_signed",
            actor=case.reviewer,
            details={"version": case.version, "review_note": case.review_note},
        )
    )
    session.flush()
    return case
