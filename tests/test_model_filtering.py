import unittest

# Import the function to be tested
from app.utils import filter_free_models


class TestModelFiltering(unittest.TestCase):
    def test_filter_free_models_basic(self):
        """
        Test that filter_free_models correctly filters models with ':free' suffix.
        """
        all_models = [
            "google/gemini-2.0-flash-001",
            "google/gemini-2.0-flash-001:free",
            "openai/gpt-3.5-turbo",
            "mistralai/mistral-7b-instruct:free",
            "anthropic/claude-3-haiku",
            "meta-llama/llama-3.1-8b-instruct:free",
            "non-free-model",
        ]
        expected_models = sorted(
            [
                "google/gemini-2.0-flash-001:free",
                "mistralai/mistral-7b-instruct:free",
                "meta-llama/llama-3.1-8b-instruct:free",
            ]
        )

        filtered_models = filter_free_models(all_models)
        self.assertEqual(sorted(filtered_models), expected_models)

    def test_filter_free_models_no_free_models(self):
        """
        Test filter_free_models when no models with ':free' suffix are present.
        """
        all_models = [
            "google/gemini-2.0-flash-001",
            "openai/gpt-3.5-turbo",
            "anthropic/claude-3-haiku",
        ]
        expected_models = []

        filtered_models = filter_free_models(all_models)
        self.assertEqual(sorted(filtered_models), expected_models)

    def test_filter_free_models_all_free_models(self):
        """
        Test filter_free_models when all models have ':free' suffix.
        """
        all_models = [
            "google/gemini-2.0-flash-001:free",
            "mistralai/mistral-7b-instruct:free",
        ]
        expected_models = sorted(
            [
                "google/gemini-2.0-flash-001:free",
                "mistralai/mistral-7b-instruct:free",
            ]
        )

        filtered_models = filter_free_models(all_models)
        self.assertEqual(sorted(filtered_models), expected_models)

    def test_filter_free_models_empty_list(self):
        """
        Test filter_free_models with an empty input list.
        """
        all_models = []
        expected_models = []

        filtered_models = filter_free_models(all_models)
        self.assertEqual(sorted(filtered_models), expected_models)


if __name__ == "__main__":
    unittest.main()
