import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.database import Base
from backend.models import AuditEvent
from backend.workflow import (
    WorkflowError,
    case_to_dict,
    create_case,
    get_case,
    list_cases,
    render_report,
    review_case,
    save_draft,
    validate_image_name,
)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        self.case = create_case(
            self.session, " Brain ", [{"format": "dcm", "bytes": 12}]
        )
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_case_starts_without_a_report_and_is_persisted(self):
        self.assertEqual(self.case.body_region, "brain")
        self.assertIsNone(self.case.report_status)
        self.assertEqual(get_case(self.session, self.case.id).id, self.case.id)

    def test_case_listing_is_paginated_and_newest_first(self):
        second = create_case(self.session, "knee", [{"format": "nii.gz", "bytes": 10}])
        self.session.commit()
        self.assertEqual(
            [case.id for case in list_cases(self.session, limit=1)],
            [second.id],
        )

    def test_draft_requires_findings_and_impression(self):
        with self.assertRaisesRegex(WorkflowError, "Findings and impression are required"):
            save_draft(self.session, self.case.id, "", " ", " ")

    def test_draft_is_manual_and_requires_review(self):
        case = save_draft(
            self.session, self.case.id, "", "No finding entered.", "Review required."
        )
        self.assertEqual(case.report_status, "pending_review")
        self.assertEqual(case.indication, "Not provided")
        self.assertIn("Not assessed", render_report(case))

    def test_return_requires_note_and_redraft_is_audited(self):
        save_draft(self.session, self.case.id, "", "Finding.", "Impression.")
        with self.assertRaisesRegex(WorkflowError, "Add a note"):
            review_case(self.session, self.case.id, "return", "Reviewer")
        case = review_case(
            self.session, self.case.id, "return", "Reviewer", "Please revise."
        )
        self.assertEqual(case.report_status, "returned")
        save_draft(self.session, self.case.id, "", "Updated finding.", "Updated impression.")
        self.session.commit()
        event_types = list(
            self.session.scalars(
                select(AuditEvent.event_type)
                .where(AuditEvent.case_id == self.case.id)
                .order_by(AuditEvent.id)
            )
        )
        self.assertEqual(
            event_types,
            ["draft_saved", "report_returned", "draft_saved"],
        )
        self.assertEqual(get_case(self.session, self.case.id).report_status, "pending_review")

    def test_signed_report_cannot_be_edited_or_reviewed_twice(self):
        save_draft(self.session, self.case.id, "", "Finding.", "Impression.")
        review_case(self.session, self.case.id, "sign", "Reviewer")
        self.session.commit()
        with self.assertRaisesRegex(WorkflowError, "cannot be edited"):
            save_draft(self.session, self.case.id, "", "Changed.", "Changed.")
        with self.assertRaisesRegex(WorkflowError, "Only a pending report"):
            review_case(self.session, self.case.id, "sign", "Reviewer")

    def test_case_response_has_no_uploaded_file_names(self):
        response = case_to_dict(self.case)
        self.assertEqual(response["images"], [{"format": "dcm", "bytes": 12}])
        self.assertNotIn("filename", response["images"][0])

    def test_image_file_suffix_validation(self):
        self.assertEqual(validate_image_name(r"C:\upload\scan.NII.GZ"), "nii.gz")
        with self.assertRaisesRegex(WorkflowError, "Use a DICOM"):
            validate_image_name("report.pdf")


if __name__ == "__main__":
    unittest.main()
