import re
import unittest
import json
import urllib.error
import urllib.request
from threading import Thread
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from server import Handler, make_lesson, qc_instruction, qc_research, research


class LessonWorkflowTests(unittest.TestCase):
    SOURCES = [
        {"kind": "Primary source", "title": "HTTP Semantics", "url": "https://example.test/rfc"},
        {"kind": "Reference", "title": "Status codes", "url": "https://example.test/status"},
        {"kind": "YouTube", "title": "Videos", "url": "https://youtube.com/results"},
        {"kind": "Book search", "title": "Books", "url": "https://books.google.com"},
    ]

    def setUp(self):
        self.sources = self.SOURCES

    def test_http_lesson_has_categories_examples_assessment_and_45_minute_schedule(self):
        title = "HTTP Requests and Responses"
        objective = "Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories."
        result = make_lesson(title, objective, {"sources": self.sources, "research_notes": []})
        for required in ("GET", "POST", "2xx", "4xx", "5xx", "404", "503", "45-minute lesson plan", "Knowledge check"):
            self.assertIn(required, result)
        self.assertIn("**[Primary source: HTTP Semantics](https://example.test/rfc)**", result)
        for factual_detail in ("safe, idempotent", "not inherently idempotent", "200 is OK", "201 is Created"):
            self.assertIn(factual_detail, result)
        schedule = re.search(r"\*\*45-minute lesson plan:\*\* (.+)", result).group(1)
        minutes = [int(value) for value in re.findall(r"(\d+) min", schedule)]
        self.assertEqual(sum(minutes), 45)
        report = qc_instruction(result, title, objective)
        self.assertIn(report["status"], ("Passed automated checks", "Review recommended"))
        report = qc_research(result, self.sources, ["GET is a safe and idempotent method."])
        self.assertTrue(
            any("does not establish" in issue["issue"] for issue in report["issues"])
        )

    def test_second_topic_has_practice_and_separate_qc_layers(self):
        title = "Photosynthesis: From Light to Chemical Energy"
        objective = "Describe how plants use light, water, and carbon dioxide to produce sugars and oxygen."
        sources = [
            {"kind": "Textbook", "title": "OpenStax Biology 2e Section 8.2: Light-Dependent Reactions", "url": "https://openstax.org/books/biology-2e/pages/8-2-the-light-dependent-reactions-of-photosynthesis"},
            {"kind": "Reference", "title": "Calvin cycle overview", "url": "https://en.wikipedia.org/wiki/Calvin_cycle"},
            *self.sources[2:],
        ]
        images = [
            {
                "title": "Photosynthesis in a leaf",
                "url": "https://upload.wikimedia.org/example.jpg",
                "page_url": "https://commons.wikimedia.org/wiki/File:Example.jpg",
                "alt": "A labeled diagram of photosynthesis.",
                "license": "CC BY-SA 4.0",
                "artist": "Example artist",
            }
        ]
        result = make_lesson(
            title,
            objective,
            {"sources": sources, "research_notes": [], "images": images},
        )
        self.assertIn("Practice (10 min)", result)
        self.assertIn("References and supplementary learning", result)
        self.assertIn("## Photo resources", result)
        self.assertIn("![A labeled diagram of photosynthesis.](https://upload.wikimedia.org/example.jpg)", result)
        self.assertIn("CC BY-SA 4.0", result)
        for factual_detail in ("Calvin cycle", "G3P", "Water is split", "oxygen", "ATP and NADPH", "OpenStax Biology 2e"):
            self.assertIn(factual_detail, result)
        self.assertEqual(qc_research(result, self.sources)["layer"], "Research and factual accuracy")
        self.assertEqual(qc_instruction(result, title, objective)["layer"], "Instructional quality")

    def test_empty_objective_is_rejected(self):
        with self.assertRaises(ValueError):
            make_lesson("A title", "", {"sources": [], "research_notes": []})

    def test_reference_links_are_bolded_without_changing_lesson_links(self):
        from server import bold_reference_links

        content = (
            "Read [this link](https://example.test/read).\n\n"
            "## References\n- [Official guide](https://example.test/guide)\n"
            "## Recap\n- [Activity](https://example.test/activity)"
        )
        result = bold_reference_links(content)
        self.assertIn("- **[Official guide](https://example.test/guide)**", result)
        self.assertIn("- [Activity](https://example.test/activity)", result)
        self.assertIn("Read [this link](https://example.test/read).", result)

    def test_research_qc_reports_missing_authoritative_sources(self):
        report = qc_research("A lesson", [{"kind": "YouTube", "title": "Search", "url": "https://example.test"}])
        self.assertEqual(report["status"], "Review recommended")
        self.assertTrue(report["issues"])

    def test_research_returns_licensed_photos_and_surfaces_search_failures(self):
        image_page = {
            "index": 1,
            "title": "File:Java class diagram.jpg",
            "imageinfo": [
                {
                    "mime": "image/jpeg",
                    "thumburl": "https://upload.wikimedia.org/java.jpg",
                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:Java_class_diagram.jpg",
                    "extmetadata": {
                        "ImageDescription": {"value": "<p>A Java class diagram.</p>"},
                        "LicenseShortName": {"value": "CC BY 4.0"},
                        "Artist": {"value": "<a href='https://example.test'>Example author</a>"},
                    },
                }
            ],
        }

        def fake_read_json(url, headers=None):
            if "commons.wikimedia.org" in url:
                return {"query": {"pages": {"1": image_page}}}
            if "wikipedia.org" in url:
                return {"query": {"search": []}}
            if "googleapis.com" in url:
                return {"items": []}
            self.fail(f"Unexpected research URL: {url}")

        with patch("server._read_json", side_effect=fake_read_json), patch.dict(
            "os.environ", {"YOUTUBE_API_KEY": ""}
        ):
            result = research("OOP in Java", "Explain classes and objects to beginners")

        self.assertEqual(len(result["images"]), 1)
        self.assertEqual(result["images"][0]["alt"], "A Java class diagram.")
        self.assertEqual(result["images"][0]["artist"], "Example author")
        self.assertFalse(any("No licensed image results" in error for error in result["research_errors"]))


class LessonApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_homepage_serves_app(self):
        with urllib.request.urlopen(self.base_url + "/") as response:
            self.assertEqual(response.status, 200)
            page = response.read()
            self.assertIn(b"Lesson Studio", page)
            self.assertIn(b"dashboard-illustration.svg", page)
            self.assertIn(b"reviewSourceList", page)
            self.assertIn(b"lessonPhotoList", page)
            self.assertIn(b"Website and research links", page)

        with urllib.request.urlopen(self.base_url + "/dashboard-illustration.svg") as response:
            self.assertEqual(response.headers.get_content_type(), "image/svg+xml")
            self.assertIn(b"<svg", response.read())

    def test_api_rejects_empty_inputs_and_returns_both_qc_reports(self):
        request = urllib.request.Request(
            self.base_url + "/api/generate",
            data=json.dumps({"title": "", "objective": "test"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        self.assertEqual(error.exception.code, 400)

        payload = {
            "title": "HTTP Requests and Responses",
            "objective": "Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories.",
            "research": {"sources": LessonWorkflowTests.SOURCES, "research_notes": []},
        }
        request = urllib.request.Request(
            self.base_url + "/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            result = json.load(response)
        self.assertEqual(result["qc_research"]["layer"], "Research and factual accuracy")
        self.assertEqual(result["qc_instruction"]["layer"], "Instructional quality")
        self.assertIn("503", result["content"])

    def test_qc_endpoint_rechecks_edited_draft(self):
        payload = {
            "title": "HTTP Requests and Responses",
            "objective": "Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories.",
            "content": "An edited draft with no timed plan or practice.",
            "sources": [],
        }
        request = urllib.request.Request(
            self.base_url + "/api/qc",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            reports = json.load(response)
        self.assertTrue(reports["qc_research"]["issues"])
        self.assertTrue(reports["qc_instruction"]["issues"])


if __name__ == "__main__":
    unittest.main()
