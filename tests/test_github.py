import base64
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

from lab_index import LabIndexError
from lab_index.github import (
    API, API_VERSION, MAX_README, MAX_RESPONSE, APIError, File, GitHub, NoRedirect, target_name,
)
from tests.helpers import (
    README, YAML, Response, file_json, headers, http_error, link, page_url,
    put_response, repo, repository_json,
)


class GitHubTests(unittest.TestCase):
    def setUp(self):
        self.client = GitHub('read-test-token')
        self.open = self.enterContext(patch.object(self.client._opener, 'open'))
        self.sleep = self.enterContext(patch('lab_index.github.time.sleep'))

    def test_owner_identity_before_scan(self):
        for value in ({'login': 'DyDoJoPkA'}, {'login': 'other'}, {}, [], {'login': None}):
            self.open.return_value = Response(value)
            if isinstance(value, dict) and value.get('login') == 'DyDoJoPkA':
                self.client.verify_owner()
            else:
                with self.assertRaises(LabIndexError):
                    self.client.verify_owner()

    def test_target_owner_and_repo_name_validation(self):
        self.assertEqual(target_name('Dydojopka/index'), 'index')
        for name in ('other/index', 'dydojopka', 'dydojopka/a/b', 'dydojopka/..',
                     'dydojopka/a?x', 'dydojopka/a\n'):
            with self.subTest(name=name), self.assertRaises(LabIndexError):
                target_name(name)

    def test_token_header_validation(self):
        for value in ('', 'a\nb', 'a\rb', 'a b', 'токен'):
            with self.subTest(value=value), self.assertRaises(LabIndexError):
                GitHub(value)

    def test_headers_timeout_fixed_host_and_no_redirects(self):
        self.open.return_value = Response({'login': 'dydojopka'})
        self.client.verify_owner()
        request = self.open.call_args.args[0]
        self.assertEqual(request.full_url, API + '/user')
        self.assertEqual(request.get_header('Authorization'), 'Bearer read-test-token')
        self.assertEqual(request.get_header('Accept'), 'application/vnd.github+json')
        self.assertEqual(request.get_header('X-github-api-version'), API_VERSION)
        self.assertTrue(request.get_header('User-agent'))
        self.assertEqual(self.open.call_args.kwargs['timeout'], 20)
        self.assertIsNone(NoRedirect().redirect_request(Request(API), None, 302, '', headers(), 'https://evil'))
        self.open.reset_mock()
        for path in ('https://evil/user', 'https://api.github.com.evil/user',
                     'https://x@api.github.com/user', 'https://api.github.com:443/user',
                     'https://api.github.com/user\n'):
            with self.subTest(path=path), self.assertRaises(APIError):
                self.client._request('GET', path)
        self.open.assert_not_called()

    def test_repository_default_branch_and_validation(self):
        self.open.return_value = Response(repository_json('index', branch='release/учёба'))
        self.assertEqual(self.client.repository('index').branch, 'release/учёба')
        for overrides in ({'private': 'false'}, {'default_branch': None}, {'owner': {'login': 'other'}},
                          {'html_url': 'https://evil'}, {'name': 'renamed'}, {'name': '../x'}):
            obj = repository_json('index')
            obj.update(overrides)
            self.open.return_value = Response(obj)
            with self.subTest(overrides=overrides), self.assertRaises(APIError):
                self.client.repository('index')

    def test_paginate_101_repositories_private_archived_and_forks(self):
        first = [repository_json(f'r{i}', id=i + 1, private=i % 2 == 0, archived=True, fork=True)
                 for i in range(100)]
        self.open.side_effect = [Response(first, Link=link(2) + ', ' + link(2, 'last')),
                                 Response([repository_json('old', id=101, private=True)])]
        repos = list(self.client.repositories())
        self.assertEqual(len(repos), 101)
        self.assertTrue(repos[-1].private)
        self.assertEqual(self.open.call_args_list[0].args[0].full_url, page_url(1))
        self.assertEqual(self.open.call_args_list[1].args[0].full_url, page_url(2))
        query = parse_qs(urlsplit(page_url(1)).query)
        self.assertEqual(query['visibility'], ['all'])
        self.assertEqual(query['affiliation'], ['owner'])
        self.assertNotIn('type', query)

    def test_foreign_collaborator_repos_filtered_and_not_requested(self):
        self.open.return_value = Response([repository_json('foreign-private', owner='someone', private=True),
                                          repository_json('mine', id=2)])
        self.assertEqual([r.name for r in self.client.repositories()], ['mine'])

    def test_broken_last_page_and_duplicates_fail(self):
        cases = [
            [Response([repository_json()], Link=link(2)), http_error(401)],
            [Response([repository_json()], Link=link(2) + ', ' + link(3, 'last')),
             Response([repository_json('b', id=2)])],
            [Response([repository_json()], Link=link(2)), Response([repository_json()])],
            [Response([repository_json()], Link=link(2)), Response([repository_json('b')])],
            [Response([repository_json()], Link=link(3))],
            [Response([], Link=link(2))],
            [Response({})], [Response([{'owner': {}}])],
        ]
        for responses in cases:
            self.open.side_effect = responses
            with self.subTest(responses=responses), self.assertRaises(APIError):
                list(self.client.repositories())

    def test_untrusted_and_malformed_pagination_links(self):
        for value in ('garbage', '<https://evil/user/repos>; rel="next"',
                      link(2).replace('/user/repos', '/users/dydojopka/repos'),
                      link(2).replace('visibility=all', 'visibility=public'),
                      link(2).replace('page=2', 'page=1'),
                      link(2) + ', ' + link(3),
                      link(2).replace('page=2', 'page=2&page=3')):
            self.open.reset_mock()
            self.open.side_effect = [Response([repository_json()], Link=value)]
            with self.subTest(value=value), self.assertRaises(APIError):
                list(self.client.repositories())
            self.assertEqual(self.open.call_count, 1)

    def test_absent_metadata_and_empty_repository(self):
        for response in (http_error(404), http_error(409, 'Git Repository is empty.'),
                         http_error(409, 'This repository is empty.')):
            self.open.side_effect = [response]
            self.assertIsNone(self.client.file(repo(), '.lab.yml'))
        self.open.side_effect = [http_error(409, 'another conflict')]
        with self.assertRaises(APIError):
            self.client.file(repo(), '.lab.yml')
        self.open.side_effect = [http_error(404)]
        with self.assertRaises(APIError):
            self.client.file(repo(), 'README.md')

    def test_file_uses_explicit_encoded_default_branch_not_download_url(self):
        obj = file_json(download_url='https://evil/never-request-this')
        self.open.return_value = Response(obj)
        file = self.client.file(repo('name.with-dots', branch='release/учёба+#'), '.lab.yml')
        self.assertEqual(file.content, YAML)
        url = self.open.call_args.args[0].full_url
        self.assertIn('/name.with-dots/contents/.lab.yml?', url)
        self.assertIn('ref=release%2F', url)
        self.assertEqual(parse_qs(urlsplit(url).query), {'ref': ['release/учёба+#']})
        self.assertEqual(self.open.call_count, 1)

    def test_empty_file_and_exact_size_limit(self):
        for data in (b'', b'a' * 65536):
            self.open.return_value = Response(file_json(data))
            self.assertEqual(self.client.file(repo(), '.lab.yml').content, data)

    def test_file_type_encoding_size_sha_base64_and_shape_validation(self):
        values = [None, [], {}, file_json(type='dir'), file_json(type='symlink'),
                  file_json(type='submodule'), file_json(submodule_git_url='https://evil'),
                  file_json(target='somewhere'), file_json(encoding='none'), file_json(content='%%%'),
                  file_json(content='é'), file_json(sha='not-sha'), file_json(size=True),
                  file_json(size=-1), file_json(size=65537), file_json(size=0),
                  file_json(path='other'), file_json(content=None)]
        for value in values:
            self.open.return_value = Response(value)
            with self.subTest(value=value), self.assertRaises(APIError):
                self.client.file(repo(), '.lab.yml')

    def test_json_and_response_limits(self):
        for raw in (b'not json', b'\xff', b'[' * 2000 + b']' * 2000, b' ' * (MAX_RESPONSE + 1)):
            self.open.return_value = Response(raw=raw)
            with self.subTest(raw=raw[:10]), self.assertRaises(APIError):
                self.client.verify_owner()

    def test_known_truncated_http_response_is_not_accepted_as_complete_page(self):
        for length in ('3', 'not a length', '-1', '9' * 5000):
            self.open.return_value = Response([], **{'Content-Length': length})
            with self.subTest(length=length), self.assertRaisesRegex(APIError, 'неполный'):
                list(self.client.repositories())

    def test_base64_payload_size_checked_before_decoding(self):
        self.open.return_value = Response(file_json(size=1))
        with patch('lab_index.github.base64.b64decode') as decode:
            with self.assertRaisesRegex(APIError, 'размер Base64'):
                self.client.file(repo(), '.lab.yml')
            decode.assert_not_called()

    def test_read_retries_temporaries_but_not_auth_or_redirects(self):
        for status in (429, 500, 502, 503, 504):
            self.open.reset_mock()
            self.open.side_effect = [http_error(status), Response({'login': 'dydojopka'})]
            self.client.verify_owner()
            self.assertEqual(self.open.call_count, 2)
        for status in (301, 302, 401, 403, 404, 422, 501):
            self.open.reset_mock()
            self.open.side_effect = [http_error(status)]
            with self.subTest(status=status), self.assertRaises(APIError):
                self.client.verify_owner()
            self.assertEqual(self.open.call_count, 1)

    def test_network_retry_limit_and_recovery(self):
        for error in (TimeoutError('read-test-token'), URLError('read-test-token')):
            self.open.reset_mock()
            self.open.side_effect = [error, error, error]
            with self.assertRaises(APIError) as caught:
                self.client.verify_owner()
            self.assertNotIn('read-test-token', str(caught.exception))
            self.assertEqual(self.open.call_count, 3)
        self.open.side_effect = [TimeoutError(), Response({'login': 'dydojopka'})]
        self.client.verify_owner()

    def test_rate_limit_403_retry_after_and_bounded_total_budget(self):
        self.open.side_effect = [http_error(403, **{'Retry-After': '3'}), Response({'login': 'dydojopka'})]
        self.client.verify_owner()
        self.sleep.assert_called_with(3)
        self.open.reset_mock()
        self.open.side_effect = [http_error(403, **{'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': '9999999999'})]
        with self.assertRaisesRegex(APIError, 'бюджет'):
            self.client.verify_owner()
        self.assertEqual(self.open.call_count, 1)
        self.open.side_effect = [http_error(429, **{'Retry-After': '6'}),
                                 http_error(429, **{'Retry-After': '6'})]
        with self.assertRaises(APIError):
            self.client.verify_owner()

    def test_retry_after_http_date_and_bad_values(self):
        self.open.side_effect = [http_error(429, **{'Retry-After': 'Thu, 01 Jan 1970 00:00:05 GMT'}),
                                 Response({'login': 'dydojopka'})]
        with patch('lab_index.github.time.time', return_value=0):
            self.client.verify_owner()
        self.sleep.assert_called_with(5)
        for value in ('NaN', 'infinity', 'bad', '100000'):
            self.open.side_effect = [http_error(429, **{'Retry-After': value})]
            with self.subTest(value=value), self.assertRaises(APIError):
                self.client.verify_owner()
        self.open.side_effect = [http_error(403, **{'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': 'NaN'})]
        with self.assertRaisesRegex(APIError, 'заголовки лимита'):
            self.client.verify_owner()

    def test_put_contains_only_readme_original_sha_branch_and_fixed_message(self):
        original = File(README, 'a' * 40)
        self.open.return_value = put_response()
        self.client.publish(repo('index', branch='default/branch'), original, b'new')
        request = self.open.call_args.args[0]
        self.assertEqual(request.method, 'PUT')
        self.assertEqual(request.full_url, API + '/repos/dydojopka/index/contents/README.md')
        self.assertEqual(json.loads(request.data), {
            'content': base64.b64encode(b'new').decode(), 'sha': 'a' * 40,
            'branch': 'default/branch', 'message': 'Обновлён каталог учебных работ',
        })

    def test_no_put_when_identical_and_oversize_fails_before_write(self):
        original = File(README, 'a' * 40)
        self.client.publish(repo(), original, README)
        self.open.assert_not_called()
        with self.assertRaises(LabIndexError):
            self.client.publish(repo(), original, b'a' * (MAX_README + 1))
        self.open.assert_not_called()

    def test_conflict_or_forbidden_write_is_not_retried(self):
        for status in (401, 403, 409, 422):
            self.open.reset_mock()
            self.open.side_effect = [http_error(status)]
            with self.subTest(status=status), self.assertRaises(LabIndexError):
                self.client.publish(repo(), File(README, 'a' * 40), b'new')
            self.assertEqual(self.open.call_count, 1)

    def test_uncertain_put_confirmed_by_readback_without_retry(self):
        for result in (TimeoutError(), http_error(502), Response(raw=b'bad json'), Response({})):
            self.open.reset_mock()
            self.open.side_effect = [result, Response(file_json(b'new', 'README.md'))]
            self.client.publish(repo(), File(README, 'a' * 40), b'new')
            self.assertEqual([c.args[0].method for c in self.open.call_args_list], ['PUT', 'GET'])

    def test_uncertain_put_unconfirmed_fails_without_retry(self):
        for readback in (Response(file_json(README, 'README.md')), http_error(403)):
            self.open.reset_mock()
            self.open.side_effect = [URLError('write-test-token'), readback]
            with self.assertRaisesRegex(LabIndexError, 'не подтверждена'):
                self.client.publish(repo(), File(README, 'a' * 40), b'new')
            self.assertEqual([c.args[0].method for c in self.open.call_args_list], ['PUT', 'GET'])

    def test_status_bodies_are_never_exposed(self):
        self.open.side_effect = [http_error(403, 'Authorization: Bearer read-test-token hidden-private-repo')]
        with self.assertRaises(APIError) as caught:
            self.client.file(repo('hidden-private-repo', private=True), '.lab.yml')
        self.assertEqual(str(caught.exception), 'API: HTTP 403')
