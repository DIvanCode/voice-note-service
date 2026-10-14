import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from app import extractor


def upstream_response(result: object) -> MagicMock:
    response = MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.__iter__.return_value = iter(())
    response.read.return_value = json.dumps({
        "choices": [{"message": {"content": json.dumps(result)}}]
    }).encode()
    return response


class ExtractorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.valid = {field: None for field in extractor.FIELDS}

    def test_validate_result_accepts_exact_contract(self) -> None:
        self.assertEqual(extractor.validate_result(self.valid), self.valid)

    def test_validate_result_rejects_extra_field(self) -> None:
        result = {**self.valid, "extra": "must fail"}
        with self.assertRaises(ValueError):
            extractor.validate_result(result)

    def test_validate_result_rejects_wrong_type(self) -> None:
        result = {**self.valid, "budget": 100000}
        with self.assertRaises(ValueError):
            extractor.validate_result(result)

    def test_empty_input_is_rejected_without_model_call(self) -> None:
        with patch.object(extractor, "urlopen") as request:
            with self.assertRaises(extractor.InputValidationError):
                extractor.extract_text("  ")
            request.assert_not_called()

    def test_invalid_model_response_is_retried_once(self) -> None:
        response = upstream_response({**self.valid, "extra": "invalid"})
        with patch.object(extractor, "urlopen", side_effect=[
            response,
            URLError("temporary failure"),
        ]) as request:
            with self.assertRaises(extractor.ModelUnavailableError):
                extractor.extract_text("test transcript")
            self.assertEqual(request.call_count, 2)

    def test_valid_model_response_is_returned(self) -> None:
        with patch.object(
            extractor,
            "urlopen",
            return_value=upstream_response(self.valid),
        ):
            self.assertEqual(extractor.extract_text("test transcript"), self.valid)

    def test_requests_are_not_serialized_by_the_client(self) -> None:
        entered = threading.Barrier(2)

        def call(_: str) -> dict[str, str | None]:
            entered.wait(timeout=1)
            return self.valid, {}

        with patch.object(extractor, "_call_llama_once", side_effect=call):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(extractor.extract_text, ["first", "second"]))
        self.assertEqual(results, [self.valid, self.valid])


if __name__ == "__main__":
    unittest.main()
