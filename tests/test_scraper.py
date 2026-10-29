import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup
from scraper.scraper import school_filter, scrape_directory, scrape_profile


class SchoolFilterTests(unittest.TestCase):
    def test_keeps_unrecognized_profile_sections(self):
        html = '''<article class="detail-page">
          <h1>Jane Smith</h1>
          <h2>Awards and Honors</h2><ul><li>Distinguished Research Award</li></ul>
          <h2>Research Interests</h2><p>Machine learning</p>
        </article>'''
        with patch('scraper.scraper.get_soup', return_value=BeautifulSoup(html, 'html.parser')):
            profile = scrape_profile('https://example.edu/jane')
        self.assertEqual(profile['additional_sections'], {'Awards and Honors': ['Distinguished Research Award']})
        self.assertEqual(profile['research_interests'], ['Machine learning'])

    def test_school_selected_instead_of_department(self):
        html = '''
            <select name="organization"><option value="1000054495">School of Computing</option></select>
            <select name="school"><option value="54491">School of Computing</option></select>
        '''
        self.assertEqual(school_filter(BeautifulSoup(html, 'html.parser'), 'School of Computing'), {'school': '54491'})

    def test_duplicate_filter_controls_resolve_once(self):
        control = '<select name="school"><option value="42">School of Computing</option></select>'
        self.assertEqual(school_filter(BeautifulSoup(control * 2, 'html.parser'), 'School of Computing'), {'school': '42'})

    def test_distinct_filters_remain_ambiguous(self):
        html = '<select name="school"><option value="42">School of Computing</option><option value="43">School of Computing</option></select>'
        with self.assertRaisesRegex(ValueError, '42.*43'):
            school_filter(BeautifulSoup(html, 'html.parser'), 'School of Computing')

    def test_filtered_pagination_and_deduplication(self):
        pages = [BeautifulSoup(html, 'html.parser') for html in [
            '<select name="school"><option value="42">School of Computing</option></select>',
            '<a href="/directory/people/alice">Alice</a><a rel="next">Next</a>',
            '<a href="/directory/people/alice">Alice</a><a href="/directory/people/bob">Bob</a>',
        ]]
        with patch('scraper.scraper.get_soup', side_effect=pages) as fetch, patch('scraper.scraper.time.sleep'):
            urls = scrape_directory(school='School of Computing')
        self.assertEqual(len(urls), 2)
        self.assertEqual(fetch.call_args_list[1].kwargs['params'], {'profile_type': 21, 'school': '42'})
        self.assertEqual(fetch.call_args_list[2].kwargs['params'], {'profile_type': 21, 'school': '42', 'page': 1})

    def test_missing_school_fails(self):
        with self.assertRaises(ValueError):
            school_filter(BeautifulSoup('', 'html.parser'), 'School of Computing')

    def test_failed_page_fails(self):
        with patch('scraper.scraper.get_soup', return_value=None):
            with self.assertRaises(RuntimeError):
                scrape_directory()
