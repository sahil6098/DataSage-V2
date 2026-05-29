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
