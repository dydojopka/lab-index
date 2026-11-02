"""Synthetic fixtures only; no access to the owner's real repositories."""

import base64
from email.message import Message
import hashlib
import io
import json
from urllib.error import HTTPError
from urllib.parse import urlencode

from lab_index.catalog import Work
from lab_index.github import API, LIST_QUERY, Repository
from lab_index.metadata import Metadata, NumberedTitle
from lab_index.readme import END, START

README = b'# Manual text\r\n\r\n' + START + b'\r\nold\r\n' + END + b'\r\nTail\n'
YAML = 'course: Курс\nsections: []\nassignment:\n  number: 1\n  title: Работа\n'.encode()


def repo(name='lab', *, private=False, branch='main'):
    return Repository(name, branch, f'https://github.com/dydojopka/{name}', private)


def repository_json(name='lab', *, private=False, owner='dydojopka', branch='main', id=1, **extra):
    return dict(id=id, name=name, owner={'login': owner}, default_branch=branch,
                html_url=f'https://github.com/{owner}/{name}', private=private, **extra)


def work(name='lab', *, course='Курс', sections=(), number=1, title='Работа', private=False):
    return Work(repo(name, private=private), Metadata(
        course, tuple(NumberedTitle(n, t) for n, t in sections), NumberedTitle(number, title),
    ))


def blob_sha(data):
    return hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()


def file_json(data=YAML, path='.lab.yml', **overrides):
    obj = dict(type='file', path=path, encoding='base64', size=len(data),
               sha=blob_sha(data), content=base64.encodebytes(data).decode())
    obj.update(overrides)
    return obj


def page_url(page):
    return f'{API}/user/repos?{urlencode(LIST_QUERY)}&page={page}'


def link(page, relation='next'):
    return f'<{page_url(page)}>; rel="{relation}"'


def headers(values=None):
    result = Message()
    for key, value in (values or {}).items():
        result[key] = str(value)
    return result


class Response(io.BytesIO):
    def __init__(self, obj=None, *, raw=None, status=200, **response_headers):
        super().__init__(json.dumps(obj).encode() if raw is None else raw)
        self.headers = headers(response_headers)
        self.status = status


def http_error(status, message='not for logs', **response_headers):
    return HTTPError('https://api.github.com/hidden-private-repo', status, 'remote error',
                     headers(response_headers), io.BytesIO(json.dumps({'message': message}).encode()))


def put_response(data=b'new'):
    return Response({'content': {'path': 'README.md'}, 'commit': {'sha': blob_sha(data)}})
