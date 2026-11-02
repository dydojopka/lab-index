import base64
import io
import json
import os
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, unquote, urlsplit

from lab_index.__main__ import main
from tests.helpers import (
    README, YAML, Response, blob_sha, file_json, http_error, link, put_response, repository_json,
)


class SyntheticGitHub:
    """Stateful mock at the HTTP boundary, including conditional Contents writes."""
    def __init__(self):
        self.readme = README
        self.repos = [repository_json('public-lab'), repository_json('private-lab', id=2, private=True),
                      repository_json('hidden-unindexed', id=3, private=True)]
        self.metadata = {'public-lab': YAML, 'private-lab': YAML.replace(b'number: 1', b'number: 3')}
        self.requests = []
        self.writes = 0
        self.owner = 'dydojopka'
        self.page_failure = False
        self.metadata_failure = False
        self.conflict = False
        self.null_metadata = False

    def open(self, request, *, timeout):
        self.requests.append(request)
        path = unquote(urlsplit(request.full_url).path)
        query = parse_qs(urlsplit(request.full_url).query)
        if request.method == 'PUT':
            assert path == '/repos/dydojopka/index/contents/README.md'
            assert request.get_header('Authorization') == 'Bearer write-test-token'
            data = json.loads(request.data)
            if self.conflict or data['sha'] != blob_sha(self.readme):
                raise http_error(409)
            assert data['branch'] == 'primary'
            self.readme = base64.b64decode(data['content'])
            self.writes += 1
            return put_response(self.readme)
        assert request.method == 'GET'
        assert request.get_header('Authorization') == 'Bearer read-test-token'
        if path == '/user':
            return Response({'login': self.owner})
        if path == '/repos/dydojopka/index':
            return Response(repository_json('index', branch='primary'))
        if path == '/repos/dydojopka/index/contents/README.md':
            assert query == {'ref': ['primary']}
            return Response(file_json(self.readme, 'README.md'))
        if path == '/user/repos':
            if self.page_failure:
                if query['page'] == ['1']:
                    return Response(self.repos, Link=link(2))
                raise http_error(403, 'hidden-unindexed read-test-token')
            return Response(self.repos)
        if path.endswith('/contents/.lab.yml'):
            assert query == {'ref': ['main']}
            name = path.split('/')[3]
            if self.metadata_failure and name == 'hidden-unindexed':
                raise http_error(401, 'hidden-unindexed read-test-token')
            if self.null_metadata and name == 'hidden-unindexed':
                return Response(None)
            if name in self.metadata:
                return Response(file_json(self.metadata[name]))
            raise http_error(404)
        raise AssertionError('unexpected request')


class CLITests(unittest.TestCase):
    def setUp(self):
        self.api = SyntheticGitHub()
        self.env = {'LABS_READ_TOKEN': 'read-test-token', 'INDEX_WRITE_TOKEN': 'write-test-token',
                    'GITHUB_REPOSITORY': 'dydojopka/index'}
        self.enterContext(patch.dict(os.environ, self.env, clear=True))
        self.enterContext(patch('lab_index.github.build_opener', return_value=Mock(open=self.api.open)))
        self.stdout = self.enterContext(patch('sys.stdout', new_callable=io.StringIO))
        self.stderr = self.enterContext(patch('sys.stderr', new_callable=io.StringIO))

    def test_check_reads_everything_without_write_token_or_local_file_writes(self):
        del os.environ['INDEX_WRITE_TOKEN']
        original = self.api.readme
        with patch('builtins.open', side_effect=AssertionError('no filesystem writes')):
            self.assertEqual(main(['--check']), 0)
        self.assertEqual(self.api.readme, original)
        self.assertEqual(self.api.writes, 0)
        self.assertTrue(all(r.method == 'GET' for r in self.api.requests))
        self.assertIn('требуется изменение', self.stdout.getvalue())
        self.assertIn('проверено: 3; включено: 2', self.stdout.getvalue())
        self.assertNotIn('hidden-unindexed', self.stdout.getvalue())

    def test_publish_no_change_then_changed_set_then_removal(self):
        self.assertEqual(main(['--publish']), 0)
        self.assertEqual(self.api.writes, 1)
        self.assertIn(b'</a> (Private)', self.api.readme)
        self.assertTrue(self.api.readme.startswith(b'# Manual text\r\n\r\n'))
        self.assertTrue(self.api.readme.endswith(b'\r\nTail\n'))
        self.assertEqual(main(['--publish']), 0)
        self.assertEqual(self.api.writes, 1)
        self.assertIn('без изменений', self.stdout.getvalue())
        self.api.repos = [repository_json('renamed-lab', id=1)]
        self.api.metadata = {'renamed-lab': YAML.replace(b'sections: []', b'sections: [{number: 2, title: Moved}]')}
        self.assertEqual(main(['--publish']), 0)
        self.assertEqual(self.api.writes, 2)
        self.assertNotIn(b'/public-lab', self.api.readme)
        self.assertNotIn(b'(Private)', self.api.readme)
        self.assertIn(b'/renamed-lab', self.api.readme)
        self.assertIn(b'2. Moved', self.api.readme)
        self.api.metadata.clear()
        self.assertEqual(main(['--publish']), 0)
        self.assertEqual(self.api.writes, 3)
        self.assertNotIn(b'## ', self.api.readme)
        self.assertEqual(main(['--publish']), 0)
        self.assertEqual(self.api.writes, 3)

    def test_last_page_error_prevents_partial_publication(self):
        self.api.page_failure = True
        self.assertEqual(main(['--publish']), 1)
        self.assertEqual(self.api.writes, 0)
        self.assertEqual(self.api.readme, README)
        self.assertNotIn('hidden-unindexed', self.stderr.getvalue())

    def test_source_api_error_prevents_publication_without_disclosing_nonparticipant(self):
        self.api.metadata_failure = True
        self.assertEqual(main(['--publish']), 1)
        self.assertEqual(self.api.writes, 0)
        self.assertNotIn('hidden-unindexed', self.stderr.getvalue())
        self.assertNotIn('read-test-token', self.stderr.getvalue())

    def test_null_contents_response_is_not_treated_as_missing_file(self):
        self.api.null_metadata = True
        self.assertEqual(main(['--publish']), 1)
        self.assertEqual(self.api.writes, 0)
        self.assertEqual(self.api.readme, README)

    def test_visibility_change_is_included_in_byte_comparison(self):
        self.assertEqual(main(['--publish']), 0)
        self.api.repos[1]['private'] = False
        self.assertEqual(main(['--publish']), 0)
        self.assertEqual(self.api.writes, 2)
        self.assertNotIn(b'(Private)', self.api.readme)

    def test_invalid_metadata_or_conflicts_fail_without_put(self):
        for data in (YAML.replace(b'number: 1', b'number: true'), YAML):
            self.api.metadata['private-lab'] = data
            self.assertEqual(main(['--publish']), 1)
            self.assertEqual(self.api.writes, 0)
        self.assertIn('private-lab: .lab.yml: assignment.number', self.stderr.getvalue())
        self.assertEqual(self.api.readme, README)

    def test_marker_failure_happens_before_repository_enumeration(self):
        self.api.readme = b'no markers'
        self.assertEqual(main(['--publish']), 1)
        self.assertFalse(any('/user/repos?' in r.full_url for r in self.api.requests))
        self.assertEqual(self.api.writes, 0)

    def test_missing_inputs_and_wrong_target_fail_before_network(self):
        for name in self.env:
            with patch.dict(os.environ, self.env, clear=True):
                del os.environ[name]
                self.assertEqual(main(['--publish']), 1)
        with patch.dict(os.environ, {'GITHUB_REPOSITORY': 'other/index'}):
            self.assertEqual(main(['--check']), 1)
        self.assertEqual(self.api.requests, [])

    def test_wrong_token_owner_fails_before_reading_index(self):
        self.api.owner = 'someone-else'
        self.assertEqual(main(['--publish']), 1)
        self.assertEqual(len(self.api.requests), 1)
        self.assertIn('должен принадлежать dydojopka', self.stderr.getvalue())

    def test_stale_sha_is_not_replaced_with_fresh_sha(self):
        self.api.conflict = True
        self.assertEqual(main(['--publish']), 1)
        self.assertEqual(self.api.writes, 0)
        puts = [r for r in self.api.requests if r.method == 'PUT']
        self.assertEqual(len(puts), 1)
        self.assertEqual(json.loads(puts[0].data)['sha'], blob_sha(README))
        self.assertEqual(self.api.readme, README)

    def test_unexpected_exception_does_not_leak_traceback_or_secret(self):
        with patch('lab_index.__main__.parse_metadata', side_effect=RuntimeError('read-test-token')):
            self.assertEqual(main(['--publish']), 1)
        self.assertNotIn('read-test-token', self.stderr.getvalue())
        self.assertNotIn('Traceback', self.stderr.getvalue())
        self.assertEqual(self.api.writes, 0)

    def test_cli_requires_exactly_one_mode(self):
        for argv in ([], ['--check', '--publish'], ['--other']):
            with self.subTest(argv=argv), self.assertRaises(SystemExit) as error:
                main(argv)
            self.assertEqual(error.exception.code, 2)
        self.assertEqual(self.api.requests, [])
