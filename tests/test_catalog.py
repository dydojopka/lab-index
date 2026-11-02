import itertools
import unittest

from lab_index import LabIndexError
from lab_index.catalog import build_catalog
from lab_index.readme import render_catalog
from tests.helpers import work


class CatalogTests(unittest.TestCase):
    def test_sections_merge_and_assignments_sort_numerically(self):
        works = [work('a', sections=[(2, 'Outer'), (1, 'Inner')], number=3),
                 work('b', sections=[(2, 'Outer'), (1, 'Inner')], number=1)]
        tree = build_catalog(works)
        self.assertEqual(len(tree), 1)
        self.assertEqual(list(tree[0].sections), [2])
        self.assertEqual(len(tree[0].sections[2].sections[1].assignments), 2)

    def test_number_to_title_and_title_to_number_conflicts(self):
        for sections in ([(1, 'Other')], [(2, 'Intro')]):
            with self.subTest(sections=sections), self.assertRaisesRegex(LabIndexError, 'sections'):
                build_catalog([work('a', sections=[(1, 'Intro')]), work('b', sections=sections)])

    def test_section_identity_is_scoped_to_parent_and_course(self):
        tree = build_catalog([
            work('a', sections=[(1, 'A'), (1, 'Intro')]),
            work('b', sections=[(2, 'B'), (2, 'Intro')]),
            work('c', course='Other', sections=[(1, 'Intro')]),
        ])
        self.assertEqual(len(tree), 2)

    def test_assignment_numbers_are_unique_only_within_node(self):
        with self.assertRaisesRegex(LabIndexError, 'assignment.number'):
            build_catalog([work('a'), work('b')])
        tree = build_catalog([work('a'), work('b', sections=[(1, 'A')]),
                              work('c', sections=[(2, 'B')])])
        self.assertEqual(len(tree[0].assignments), 1)
        self.assertEqual(len(tree[0].sections), 2)

    def test_deterministic_courses_and_api_order(self):
        names = ['ёж', 'Еж', 'еж', 'Ёж', 'Z', 'a', 'A', 'е\u0308ж']
        works = [work(f'r{i}', course=name) for i, name in enumerate(names)]
        expected = ['A', 'a', 'Z', 'Ёж', 'Еж', 'е\u0308ж', 'еж', 'ёж']
        self.assertEqual([n.title for n in build_catalog(works)], expected)
        works = [work('a', sections=[(3, 'C')]), work('b', sections=[(1, 'A')]),
                 work('c', number=3), work('d', number=1)]
        results = {render_catalog(build_catalog(order)) for order in itertools.permutations(works)}
        self.assertEqual(len(results), 1)

    def test_rebuild_handles_add_rename_move_remove_and_pruning(self):
        original = render_catalog(build_catalog([work('before', sections=[(1, 'Old')])]))
        changed = render_catalog(build_catalog([work('after', course='New', sections=[(2, 'Moved')], title='New title')]))
        self.assertIn('/before', original)
        self.assertNotIn('/before', changed)
        self.assertNotIn('Old', changed)
        self.assertIn('/after', changed)
        self.assertIn('Moved', changed)
        self.assertEqual(build_catalog([]), [])
