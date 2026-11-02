import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import yaml

from lab_index.metadata import MAX_BYTES, MetadataError, parse_metadata
from tests.helpers import YAML


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.obj = yaml.safe_load(YAML)

    def parse(self, obj):
        return parse_metadata(yaml.safe_dump(obj, allow_unicode=False).encode())

    def test_valid_empty_sections_and_example(self):
        self.assertEqual(parse_metadata(YAML).sections, ())
        example = Path('examples/.lab.yml').read_bytes()
        result = parse_metadata(example)
        self.assertEqual([s.number for s in result.sections], [2, 1])
        self.assertEqual(result.assignment.number, 3)

    def test_required_unknown_and_wrong_shapes(self):
        variants = [None, [], 'text', 3]
        for field in self.obj:
            obj = copy.deepcopy(self.obj)
            del obj[field]
            variants.append(obj)
        for key in ('url', 'private', 'enabled', 'version'):
            variants.append(dict(self.obj, **{key: True}))
        for value in ({}, None, 'none', [1]):
            variants.append(dict(self.obj, sections=value))
        for value in ([], None, 1, {'number': 1}, {'number': 1, 'title': 'A', 'extra': 1}):
            variants.append(dict(self.obj, assignment=value))
        for value in variants:
            with self.subTest(value=value), self.assertRaises(MetadataError):
                self.parse(value)

    def test_number_types_and_bounds_in_assignments_and_sections(self):
        for number in (True, False, 1.0, '3', None, 0, -1, 2_147_483_648):
            for location in ('assignment', 'sections'):
                obj = copy.deepcopy(self.obj)
                item = {'number': number, 'title': 'A'}
                obj[location] = [item] if location == 'sections' else item
                with self.subTest(number=number, location=location), self.assertRaisesRegex(MetadataError, 'number'):
                    self.parse(obj)
        self.obj['assignment']['number'] = 2_147_483_647
        self.assertEqual(self.parse(self.obj).assignment.number, 2_147_483_647)

    def test_titles_types_whitespace_controls_and_length(self):
        bad = ['', ' A', 'A ', 'A\nB', '\tA', 'A\tB', 'A\rB', 'A\0B', 'A\x7fB',
               'A\x85B', 'A\u2028B', 'A\u2029B', 'A\u202eB', 'a' * 501, 4, True,
               None, yaml.safe_load('2024-01-01')]
        for value in bad:
            for location in ('course', 'assignment', 'sections'):
                obj = copy.deepcopy(self.obj)
                if location == 'course':
                    obj[location] = value
                elif location == 'assignment':
                    obj[location]['title'] = value
                else:
                    obj[location] = [{'number': 1, 'title': value}]
                with self.subTest(value=value, location=location), self.assertRaises(MetadataError):
                    self.parse(obj)

    def test_literal_unicode_and_markup_not_silently_normalized(self):
        for title in ('Ёлка е\u0308', 'a' * 500, '"<>& [x](https://x) # *a* `b`', '<!-- LAB-INDEX:END -->'):
            self.obj['course'] = title
            self.obj['assignment']['title'] = title
            self.assertEqual(self.parse(self.obj).course, title)

    def test_duplicate_keys_documents_tags_anchors_aliases_and_merge(self):
        cases = [
            YAML + b'course: Again\n',
            YAML.replace(b'number: 1', b'number: 1\n  number: 2'),
            YAML + b'---\n{}',
            YAML.replace(b'course:', b'course: !custom'),
            YAML.replace(b'course:', b'course: !!str'),
            YAML.replace(b'course:', b'course: &c'),
            b'course: *missing\nsections: []\nassignment: {}',
            YAML + b'<<: {}\n', YAML + b'"<<": {}\n',
            YAML + b'? [complex, key]\n: value\n',
            b'course: !!python/object/apply:os.system [echo unsafe]',
        ]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(MetadataError):
                parse_metadata(value)

    def test_depth_checked_before_construction(self):
        data = b'[' * 1000 + b'0' + b']' * 1000
        with patch('lab_index.metadata.yaml.load') as load:
            with self.assertRaisesRegex(MetadataError, 'глубина'):
                parse_metadata(data)
            load.assert_not_called()

    def test_file_size_utf8_and_path_limits(self):
        for data in (b'#' * (MAX_BYTES + 1), b'\xff', b'', b'course: ['):
            with self.subTest(data=data[:10]), self.assertRaises(MetadataError):
                parse_metadata(data)
        self.assertEqual(parse_metadata(YAML + b'#' * (MAX_BYTES - len(YAML))).course, 'Курс')
        self.obj['sections'] = [{'number': 1, 'title': 'X'} for _ in range(32)]
        self.assertEqual(len(self.parse(self.obj).sections), 32)
        self.obj['sections'].append({'number': 1, 'title': 'X'})
        with self.assertRaisesRegex(MetadataError, 'sections'):
            self.parse(self.obj)

    def test_errors_do_not_include_source_or_unknown_keys(self):
        for data in (YAML + b'secret-value: x\n', b'course: [secret-value',
                     YAML.replace(b'number: 1', b'number: secret-value')):
            with self.assertRaises(MetadataError) as error:
                parse_metadata(data)
            self.assertNotIn('secret-value', str(error.exception))
