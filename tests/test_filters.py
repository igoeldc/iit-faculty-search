import unittest
from unittest.mock import patch

from backend import main
from backend.main import _filter_results, _matches_faculty_type
from backend.search import structured_search
from build_indices import make_searchable


RECORDS = [
    {"name": "Full", "departments": ["Computer Science"], "titles": ["Professor of Computer Science"]},
    {"name": "Associate", "departments": ["Computer Science"], "titles": ["Associate Professor of Computer Science"]},
    {"name": "Assistant", "departments": ["Mathematics"], "titles": ["Assistant Professor of Mathematics"]},
]


class FilterTests(unittest.TestCase):
    def test_department_is_an_exact_membership_filter(self):
        results = _filter_results(RECORDS, "Computer Science", None)
        self.assertEqual([record["name"] for record in results], ["Full", "Associate"])

    def test_full_professor_excludes_ranked_professors(self):
        self.assertTrue(_matches_faculty_type(RECORDS[0], "Full Professor"))
        self.assertFalse(_matches_faculty_type(RECORDS[1], "Full Professor"))
        self.assertFalse(_matches_faculty_type(RECORDS[2], "Full Professor"))

    def test_type_filter_combines_with_department(self):
        results = _filter_results(RECORDS, "Computer Science", "Associate Professor")
        self.assertEqual([record["name"] for record in results], ["Associate"])

    def test_keyword_route_applies_both_filters_after_ranking(self):
        original_faculty = main._faculty
        main._faculty = RECORDS
        try:
            with patch("backend.main.keyword_search", return_value=RECORDS):
                response = main.search(
                    q="algorithms",
                    dept="Computer Science",
                    faculty_type="Associate Professor",
                    mode="keyword",
                    offset=0,
                    limit=50,
                )
        finally:
            main._faculty = original_faculty
        self.assertEqual([record["name"] for record in response["results"]], ["Associate"])
        self.assertEqual(response["total"], 1)

    def test_search_response_uses_offset(self):
        response = main._search_response(RECORDS, "keyword", offset=1, limit=1)
        self.assertEqual([record["name"] for record in response["results"]], ["Associate"])
        self.assertEqual(response["total"], 3)

    def test_hybrid_can_omit_bm25_structured_fallback(self):
        self.assertEqual(
            structured_search("algorithms", None, None, 10, None, None, RECORDS, False),
            [],
        )

    def test_keyword_search_omits_zero_score_documents(self):
        class Retriever:
            def retrieve(self, *_args, **_kwargs):
                class Matrix:
                    shape = (1, 2)
                    def __getitem__(self, key): return [0, 1][key[1]]
                return Matrix(), MatrixScores()

        class MatrixScores:
            def __getitem__(self, key): return [1.0, 0.0][key[1]]

        from backend.search import keyword_search
        with patch('bm25s.tokenize', return_value=[]):
            results = keyword_search('topic', 2, Retriever(), RECORDS[:2])
        self.assertEqual([record['name'] for record in results], ['Full'])

    def test_retrieval_text_includes_available_profile_detail(self):
        text = make_searchable(
            {
                "name": "Ada Lovelace",
                "education": ["Mathematics, University of London"],
                "professional_affiliations": ["ACM"],
            }
        )
        self.assertIn("Mathematics, University of London", text)
        self.assertIn("ACM", text)
