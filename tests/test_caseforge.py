import json
import subprocess
import sys
import unittest
from contextlib import contextmanager
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from caseforge.core import (
    DRAFT_SCHEMA,
    DraftError,
    generate,
    load_json,
    read_json,
    requirements_from,
)
from caseforge.providers import TITLES_SCHEMA, FixtureProvider, LlamaProvider

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
REQUIREMENTS = load_json(EXAMPLES / "requirements.json")
FIXTURE = load_json(EXAMPLES / "recorded-drafts.json")
SOURCE = requirements_from(REQUIREMENTS)[0]


@contextmanager
def local_completion(status, response):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, payload))
            payload = json.dumps(response).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            if status in {301, 302, 303, 307, 308}:
                self.send_header("Location", self.path)
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
        )
        worker.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", requests
        finally:
            server.shutdown()
            worker.join()


class CaseForgeTests(unittest.TestCase):
    def test_fixture_cases_trace_to_batch_requirements(self):
        result = generate(requirements_from(REQUIREMENTS), FixtureProvider(FIXTURE))
        self.assertEqual(
            result["counts"], {"positive": 2, "negative": 2, "boundary": 2}
        )
        self.assertEqual(result["cases"][2]["id"], "REQ-QTY-BOUNDARY")
        self.assertEqual(result["cases"][2]["requirement_id"], "REQ-QTY")
        self.assertTrue(all(case["status"] == "draft" for case in result["cases"]))

    def test_duplicate_input_ids_are_rejected(self):
        with self.assertRaisesRegex(DraftError, "Duplicate requirement"):
            requirements_from([REQUIREMENTS[0]] * 2)

    def test_duplicate_json_fields_are_rejected(self):
        with self.assertRaisesRegex(DraftError, "Repeated JSON key"):
            read_json('{"positive":1,"positive":2}')

    def test_recorded_result_is_bound_to_exact_statement(self):
        edited = requirements_from(
            [{**REQUIREMENTS[0], "statement": "New requirement"}]
        )
        with self.assertRaisesRegex(DraftError, "Fixture statement mismatch"):
            generate(edited, FixtureProvider(FIXTURE))

    def test_generated_records_must_cover_all_categories(self):
        broken = deepcopy(FIXTURE)
        del broken[SOURCE.id]["draft"]["boundary"]
        with self.assertRaisesRegex(DraftError, "all three"):
            generate([SOURCE], FixtureProvider(broken))

    def test_duplicate_titles_are_rejected(self):
        broken = deepcopy(FIXTURE)
        draft = broken[SOURCE.id]["draft"]
        draft["positive"]["title"] = draft["negative"]["title"].upper()
        with self.assertRaisesRegex(DraftError, "duplicate case titles"):
            generate([SOURCE], FixtureProvider(broken))

    def test_local_llm_transport_requests_schema_and_parses_result(self):
        output = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": json.dumps(FIXTURE[SOURCE.id]["draft"])},
                }
            ]
        }
        with local_completion(200, output) as (origin, requests):
            result = generate([SOURCE], LlamaProvider(origin, "test"))
        self.assertEqual(requests[0][0], "/v1/chat/completions")
        self.assertEqual(requests[0][1]["response_format"]["schema"], DRAFT_SCHEMA)
        self.assertIn(SOURCE.statement, requests[0][1]["messages"][1]["content"])
        self.assertEqual(len(result["cases"]), 3)

    def test_local_llm_rejects_redirect(self):
        with (
            local_completion(307, {}) as (origin, requests),
            self.assertRaisesRegex(DraftError, "local model request failed"),
        ):
            LlamaProvider(origin, "test").draft(SOURCE)
        self.assertEqual(len(requests), 1)

    def test_grounded_titles_keep_deterministic_actions_and_outcomes(self):
        requirement = requirements_from(
            load_json(EXAMPLES / "grounded-requirements.json")
        )[0]
        output = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(
                            {
                                "positive": "Accept quantity three",
                                "negative": "Reject quantity six",
                                "boundary": "Accept the maximum quantity",
                            }
                        )
                    },
                }
            ]
        }
        with local_completion(200, output) as (origin, requests):
            result = generate([requirement], LlamaProvider(origin, "test"))
        self.assertEqual(requests[0][1]["response_format"]["schema"], TITLES_SCHEMA)
        self.assertEqual(
            [row["action"] for row in result["cases"]],
            ["Submit quantity = 3", "Submit quantity = 6", "Submit quantity = 5"],
        )
        self.assertIn("unchanged", result["cases"][1]["expected"])
        self.assertEqual(result["cases"][0]["expected"], result["cases"][2]["expected"])

    def test_bool_and_flat_integer_ranges_are_invalid(self):
        source = load_json(EXAMPLES / "grounded-requirements.json")[0]
        for minimum in (True, 5):
            invalid = deepcopy(source)
            invalid["integer_constraint"]["minimum"] = minimum
            with self.subTest(minimum=minimum), self.assertRaises(DraftError):
                requirements_from([invalid])

    def test_remote_origins_are_refused(self):
        for origin in (
            "http://example.test:8080",
            "http://127.0.0.1:8080/admin",
            "http://localhost",
        ):
            with self.subTest(origin=origin), self.assertRaises(DraftError):
                LlamaProvider(origin, "test")

    def test_truncated_completion_is_reported(self):
        with (
            local_completion(200, {"choices": [{"finish_reason": "length"}]}) as (
                origin,
                _,
            ),
            self.assertRaisesRegex(DraftError, "truncated"),
        ):
            LlamaProvider(origin, "test").draft(SOURCE)

    def test_cli_produces_json_on_standard_output(self):
        cmd = [
            sys.executable,
            "-m",
            "caseforge",
            "examples/requirements.json",
            "--provider",
            "fixture",
            "--fixture",
            "examples/recorded-drafts.json",
        ]
        result = subprocess.run(
            cmd, cwd=EXAMPLES.parent, check=True, capture_output=True
        )
        self.assertEqual(len(json.loads(result.stdout)["cases"]), 6)


if __name__ == "__main__":
    unittest.main()
