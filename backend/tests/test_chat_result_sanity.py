from app.services.chat_service import ChatService


def _service() -> ChatService:
    return object.__new__(ChatService)


def test_budget_metric_columns_are_considered_related() -> None:
    service = _service()

    warnings = service._sanity_check_results(
        "give me budgeted opex and budgeted revenue of vantage",
        {"query_type": "mongodb", "collection": "Budgets"},
        [{"company": "Vantage", "budgeted_opex": 1200, "budgeted_revenue": 4500}],
    )

    assert "Result columns don't appear related to the question." not in warnings
    assert not service._has_blocking_sanity_warning(warnings)


def test_unrelated_result_columns_are_blocking() -> None:
    service = _service()

    warnings = service._sanity_check_results(
        "give me budgeted opex and budgeted revenue of vantage",
        {"query_type": "mongodb", "collection": "Customers"},
        [{"segment": "Enterprise", "count": 12}],
    )

    assert "Result columns don't appear related to the question." in warnings
    assert service._has_blocking_sanity_warning(warnings)


def test_generic_alias_can_be_supported_by_query_plan_fields() -> None:
    service = _service()

    warnings = service._sanity_check_results(
        "give me budgeted revenue of vantage",
        {
            "query_type": "mongodb",
            "collection": "Budgets",
            "pipeline": [{"$group": {"_id": None, "total": {"$sum": "$budgeted_revenue"}}}],
        },
        [{"total": 4500}],
    )

    assert "Result columns don't appear related to the question." not in warnings


def test_answer_prompt_includes_non_blocking_sanity_warnings() -> None:
    service = _service()

    prompt = service._answer_user_prompt(
        question="compare revenue by company",
        query_plan={"query_type": "mongodb", "collection": "Budgets"},
        rows=[{"company": "Vantage", "revenue": 4500}],
        sanity_warnings=["Query returned only 1 row but the question implies multiple results."],
    )

    assert "Result quality warnings:" in prompt
    assert "do not overclaim" in prompt
