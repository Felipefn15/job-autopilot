import unittest
from linkedin_collector import API, NoRedirect, canonical_post, queries

class CollectorTests(unittest.TestCase):
    def test_origin_validation(self):
        for url in ("http://example.com", "https://user:pass@example.com", "https://example.com/path", "https://example.com?token=abc"):
            with self.assertRaises(ValueError):
                API(url, "x" * 32)
        self.assertEqual(API("https://example.com/", "x" * 32).url, "https://example.com")
        self.assertIsNone(NoRedirect().redirect_request(None, None, None, None, "https://evil.example"))

    def test_post_identity(self):
        self.assertEqual(canonical_post("https://www.linkedin.com/posts/person_activity-123456789-extra?utm=a"), "https://www.linkedin.com/feed/update/urn:li:activity:123456789/")
        self.assertIsNone(canonical_post("https://linkedin.com.evil.example/posts/test"))
        self.assertIsNone(canonical_post("https://www.linkedin.com/in/person"))

    def test_queries_use_preferences(self):
        result = queries({"keywords":"React, Node.js, Python, SQL", "country":"Brasil", "remoteOnly":True})
        self.assertEqual(len(result),2)
        self.assertIn('"React" OR "Node.js"',result[0])
        self.assertIn('"Brasil"',result[0])
        self.assertIn("remote OR remoto", result[0])
        self.assertIn("Latin America", queries({"keywords":"React", "country":"LATAM"})[0])
        self.assertNotIn('"global"', queries({"keywords":"React", "country":"global"})[0])
        with self.assertRaises(ValueError): queries({"keywords":""})

if __name__ == "__main__":
    unittest.main()
