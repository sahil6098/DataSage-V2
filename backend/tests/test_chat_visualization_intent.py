from unittest import TestCase

from app.services.chat_service import ChatService


class ChatVisualizationIntentTests(TestCase):
    def setUp(self) -> None:
        self.service = object.__new__(ChatService)

    def test_visualized_follow_up_requests_chart(self) -> None:
        self.assertTrue(
            self.service._user_requested_visualization(
                "give me it in an structured visualized format so i can understand it"
            )
        )

    def test_visually_follow_up_requests_chart(self) -> None:
        self.assertTrue(self.service._user_requested_visualization("give me it visually"))

    def test_visualized_follow_up_builds_viz_payload(self) -> None:
        viz_data = self.service._build_viz_data(
            question="give me it in an structured visualized format so i can understand it",
            query_plan={"query": "SELECT department, total_expenses FROM expenses", "chart_type": "bar"},
            rows=[
                {"department": "Engineering", "total_expenses": "$59,200"},
                {"department": "Marketing", "total_expenses": "$51,500"},
            ],
            answer="Engineering has the highest expenses.",
        )

        self.assertIsNotNone(viz_data)

    def test_follow_ups_do_not_repeat_clicked_question(self) -> None:
        suggestions = self.service._generate_follow_ups(
            "Show total amount grouped by category",
            [
                {"category": "A", "amount": 10},
                {"category": "B", "amount": 20},
                {"category": "C", "amount": 30},
            ],
            {"query": "SELECT category, SUM(amount) AS amount FROM t GROUP BY category"},
        )

        self.assertNotIn("Show total amount grouped by category", suggestions)
