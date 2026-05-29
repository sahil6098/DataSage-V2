from app.services.chat_service import ChatService


def _service() -> ChatService:
    return object.__new__(ChatService)


def test_typo_history_question_is_routed_to_session_history() -> None:
    service = _service()

    assert service._should_answer_from_session_memory("what we were descusiiong in this chat")


def test_regular_analysis_question_is_not_forced_into_memory_chat() -> None:
    service = _service()

    assert not service._should_answer_from_session_memory("show Nexora Technologies revenue trend")
    assert not service._should_answer_from_session_memory("answer with a revenue trend chart")


def test_follow_up_their_answer_resolves_previous_topic_answers() -> None:
    service = _service()
    messages = [
        {"role": "user", "content": "Show Nexora Technologies revenue trend."},
        {"role": "assistant", "content": "Nexora Technologies revenue increased from 2021 to 2023."},
        {"role": "user", "content": "What did we discuss about Nexora Technologies earlier?"},
        {"role": "assistant", "content": "You asked 1 earlier question about Nexora Technologies."},
    ]

    reply = service._history_lookup_reply(messages, "what was their answer")

    assert "Nexora Technologies revenue increased from 2021 to 2023" in reply
    assert "You asked 1 earlier question" not in reply


def test_saved_session_transcript_context_is_authoritative_memory() -> None:
    service = _service()
    messages = [
        {"role": "user", "content": "Show Nexora Technologies revenue trend."},
        {"role": "assistant", "content": "Nexora revenue rose steadily."},
    ]

    context = service._session_messages_memory_context(messages)

    assert "SAVED SESSION TRANSCRIPT" in context
    assert "Show Nexora Technologies revenue trend." in context
    assert "Nexora revenue rose steadily." in context
