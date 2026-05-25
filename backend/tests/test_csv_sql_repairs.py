from pathlib import Path

from app.services.chat_service import ChatService
from app.services.connector_service import ConnectorService
from app.utils.tabular import load_tabular_source


def _chat_service() -> ChatService:
    return object.__new__(ChatService)


def _connector_service() -> ConnectorService:
    return object.__new__(ConnectorService)


def _csv_source(table_name: str = "datasage_master") -> dict:
    return {
        "type": "csv",
        "file_path": "",
        "file_name": "datasage_master.csv",
        "selected_tables": [table_name],
        "schema_cache": {
            "tables": [
                {
                    "name": table_name,
                    "fields": [
                        {"name": "record_type"},
                        {"name": "due_date"},
                        {"name": "expense_status"},
                        {"name": "expense_category"},
                        {"name": "invoice_status"},
                        {"name": "outstanding"},
                        {"name": "amount"},
                        {"name": "net_salary"},
                        {"name": "bonus"},
                    ],
                }
            ]
        },
    }


def test_uploaded_csv_table_name_uses_original_file_name(tmp_path: Path) -> None:
    stored = tmp_path / "6a13093e64fab6a6480ad2a8_6a140a1b602d264f940e5324_datasage_master.csv"
    stored.write_text("amount\n10\n", encoding="utf-8")

    tables = load_tabular_source(stored, "datasage_master.csv")

    assert list(tables) == ["datasage_master"]


def test_numeric_legacy_table_name_is_quoted_for_duckdb(tmp_path: Path) -> None:
    stored = tmp_path / "6a13093e64fab6a6480ad2a8_6a140a1b602d264f940e5324_datasage_master.csv"
    stored.write_text("amount\n10\n", encoding="utf-8")
    data_source = _csv_source("6a13093e64fab6a6480ad2a8_6a140a1b602d264f940e5324_datasage_master")
    data_source["file_path"] = str(stored)
    service = _connector_service()

    query = service._prepare_file_sql_query(
        data_source,
        "SELECT SUM(amount) AS total_amount FROM 6a13093e64fab6a6480ad2a8_6a140a1b602d264f940e5324_datasage_master",
    )

    assert 'FROM "6a13093e64fab6a6480ad2a8_6a140a1b602d264f940e5324_datasage_master"' in query


def test_sql_validation_allows_result_aliases_and_current_date() -> None:
    service = _chat_service()
    data_source = _csv_source("6a13093e64fab6a6480ad2a8_6a140a1b602d264f940e5324_datasage_master")
    plan = {
        "query": (
            "SELECT SUM(outstanding) AS total_outstanding_amount "
            "FROM 6a13093e64fab6a6480ad2a8_6a140a1b602d264f940e5324_datasage_master "
            "WHERE due_date < CURRENT_DATE"
        )
    }

    repaired = service._repair_sql_plan_for_schema(plan, "total overdue outstanding", data_source)
    warnings = service._validate_query_plan_against_schema(repaired, data_source)

    assert warnings == []


def test_sql_field_aliases_are_repaired_from_question_context() -> None:
    service = _chat_service()
    data_source = _csv_source()
    plan = {"query": "SELECT * FROM datasage_master WHERE status = 'Pending' ORDER BY amount DESC"}

    repaired = service._repair_sql_plan_for_schema(plan, "List all expenses with status Pending", data_source)
    warnings = service._validate_query_plan_against_schema(repaired, data_source)

    assert "expense_status = 'Pending'" in repaired["query"]
    assert warnings == []


def test_common_metric_aliases_are_repaired_when_used_as_columns() -> None:
    service = _chat_service()
    data_source = _csv_source()
    plan = {"query": "SELECT SUM(invoice_amount) AS total_amount FROM datasage_master"}

    repaired = service._repair_sql_plan_for_schema(plan, "total invoice amount", data_source)
    warnings = service._validate_query_plan_against_schema(repaired, data_source)

    assert "SUM(amount)" in repaired["query"]
    assert "AS total_amount" in repaired["query"]
    assert warnings == []
