import json

from app.services.report_service import REPORT_CSS, ReportService


def _service() -> ReportService:
    return object.__new__(ReportService)


def test_report_css_avoids_xhtml2pdf_unsupported_page_margin_boxes() -> None:
    assert "@bottom-right" not in REPORT_CSS


def test_saved_sessions_without_report_gate_do_not_require_four_user_messages() -> None:
    service = _service()

    assert not service._requires_minimum_messages({})


def test_new_sessions_with_report_gate_require_four_user_messages() -> None:
    service = _service()

    assert service._requires_minimum_messages({"report_min_messages_required": True})


def test_chat_report_renders_with_xhtml2pdf() -> None:
    service = _service()
    session = {
        "title": "Quarterly Sales Analysis",
        "messages": [
            {"role": "user", "content": "Show revenue by region."},
            {"role": "assistant", "content": "Revenue is strongest in the West."},
            {"role": "user", "content": "Compare the top two regions."},
            {
                "role": "assistant",
                "content": "The West leads the East.",
                "viz_data": json.dumps(
                    {
                        "summary": "Revenue by region",
                        "chart_type": "bar",
                        "rows": [
                            {"region": "West", "revenue": 125000},
                            {"region": "East", "revenue": 98000},
                        ],
                    }
                ),
            },
            {"role": "user", "content": "What should I do next?"},
            {"role": "assistant", "content": "Validate the trend against source data."},
            {"role": "user", "content": "Include caveats."},
            {"role": "assistant", "content": "The report depends on the saved transcript."},
        ],
    }
    narrative = {
        "session_overview": "A session reviewing revenue by region.",
        "executive_summary": "The session explored regional revenue performance and next steps.",
        "key_findings": ["The West region leads revenue.", "The East region is second."],
        "recommendations": ["Validate the results against the source database."],
        "limitations": ["The report uses saved chat messages only."],
    }

    pdf_bytes = service._build_pdf(session=session, narrative=narrative)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000
