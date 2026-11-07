import html
from html.parser import HTMLParser
import unittest

from lab_index import LabIndexError
from lab_index.catalog import Work, build_catalog
from lab_index.github import Repository
from lab_index.readme import END, START, EMPTY, block_bounds, render_catalog, replace_block
from tests.helpers import README, work


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, text):
        self.text.append(text)


class ReadmeTests(unittest.TestCase):
    def render(self, works):
        return render_catalog(build_catalog(works))

    def test_assignment_numbers_keep_gaps_and_private_suffix(self):
        rendered = self.render([work(f'r{n}', number=n, private=n == 3) for n in [9, 4, 1, 7, 3, 8]])
        self.assertEqual([line.split('. ', 1)[0] for line in rendered.splitlines() if '<a href=' in line],
                         ['1', '3', '4', '7', '8', '9'])
        self.assertEqual(rendered.count('</a> (Private)<br>'), 1)

    def test_maximum_assignment_number_is_displayed(self):
        self.assertIn('2147483647. <a', self.render([work(number=2_147_483_647)]))

    def test_section_and_assignment_have_dotted_numbers_without_list_markers(self):
        rendered = self.render([work(number=4, sections=[(1, 'CreateJS')], title='Square editor')])
        self.assertIn('<p>\n<strong>1. CreateJS</strong><br>\n'
                      '&nbsp;&nbsp;&nbsp;1.4. <a ', rendered)
        for tag in ('<ul', '<ol', '<li'):
            self.assertNotIn(tag, rendered)

    def test_deep_nesting_and_parent_assignments_come_first(self):
        path = [(i, f'Section{i}') for i in range(1, 33)]
        rendered = self.render([work('root', title='Root'), work('deep', sections=path),
                                work('middle', sections=path[:2], title='Middle')])
        deepest = '.'.join(str(i) for i in range(1, 33))
        self.assertIn(f'{deepest}. Section32', rendered)
        self.assertIn(f'{deepest}.1. <a ', rendered)
        self.assertLess(rendered.index('Root</a>'), rendered.index('Section1</strong>'))
        self.assertLess(rendered.index('Middle</a>'), rendered.index('Section3</strong>'))

    def test_titles_are_literal_in_all_contexts(self):
        title = '<!-- LAB-INDEX:START --> [link](https://evil) <script> & "x" **a** # @user :smile:'
        rendered = self.render([work(course=title, sections=[(1, title)], title=title)])
        heading = rendered.splitlines()[0][3:]
        self.assertEqual(html.unescape(heading), title)
        for syntax in ('<', '[', '*', '`', '@', ':'):
            self.assertNotIn(syntax, heading)
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('<!-- LAB-INDEX:', rendered)
        parser = TextParser()
        parser.feed(rendered[rendered.index('<p>'):])
        self.assertIn(title, ''.join(parser.text))
        self.assertEqual(rendered.count('<a href='), 1)

    def test_non_github_urls_are_rejected_even_if_constructed_outside_client(self):
        item = work()
        for url in ('javascript:alert(1)', 'http://github.com/dydojopka/lab',
                    'https://github.com.evil/dydojopka/lab', 'https://evil@github.com/dydojopka/lab',
                    'https://github.com/dydojopka/lab?q="', 'https://github.com/other/lab'):
            invalid = Work(Repository('lab', 'main', url, False), item.metadata)
            with self.subTest(url=url), self.assertRaises(LabIndexError):
                self.render([invalid])

    def test_empty_catalogue_is_stable(self):
        self.assertEqual(self.render([]), EMPTY)
        result = replace_block(README, EMPTY)
        self.assertEqual(replace_block(result, EMPTY), result)

    def test_lf_crlf_utf8_and_mixed_external_bytes_preserved(self):
        for newline in (b'\n', b'\r\n'):
            for ending in (b'', b'\n', b'\r\n'):
                prefix = '\ufeff# Вручную\r\nMixed\n'.encode() + START + newline
                suffix = END + ending + ('Хвост\n\r\n'.encode() if ending else b'')
                source = prefix + b'old\n' + suffix
                result = replace_block(source, '## Курс\n\nТекст')
                self.assertTrue(result.startswith(prefix))
                self.assertTrue(result.endswith(suffix))
                self.assertEqual(result[len(prefix):-len(suffix)],
                                 newline + '## Курс'.encode() + newline * 2 + 'Текст'.encode() + newline * 2)

    def test_marker_errors(self):
        invalid = [b'', START, END, END + b'\n' + START + b'\n',
                   START + b'\n' + START + b'\n' + END,
                   START + b'\n' + END + b'\n' + END,
                   b'prefix ' + START + b'\n' + END,
                   START + b' suffix\n' + END,
                   START + b'\n' + END + b' suffix',
                   START + b'\r' + END,
                   README + b'\xff']
        for source in invalid:
            with self.subTest(source=source), self.assertRaises(LabIndexError):
                block_bounds(source)

    def test_readme_in_project_has_one_valid_pair(self):
        from pathlib import Path
        block_bounds(Path('README.md').read_bytes())
