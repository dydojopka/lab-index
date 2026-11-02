"""Small, bounded REST client. Never follow redirects or log remote bodies."""

import base64
import binascii
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
import http.client
import json
import math
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import LabIndexError
from .metadata import MAX_BYTES

OWNER = 'dydojopka'
API = 'https://api.github.com'
API_VERSION = '2026-03-10'
TIMEOUT = 20
MAX_RESPONSE = 8 * 1024 * 1024
MAX_README = 1024 * 1024  # Contents API's inline Base64 limit.
RETRY_BUDGET = 10
_MISSING = object()  # JSON null is an invalid response, not an absent file.
REPO_NAME = re.compile(r'[A-Za-z0-9_.-]{1,100}\Z')
SHA = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z')
LIST_QUERY = {
    'affiliation': 'owner', 'visibility': 'all', 'per_page': '100',
    'sort': 'created', 'direction': 'asc',
}


class APIError(LabIndexError):
    def __init__(self, message: str, *, status=None, ambiguous=False):
        super().__init__(message)
        self.status = status
        self.ambiguous = ambiguous


@dataclass(frozen=True)
class Repository:
    name: str
    branch: str
    url: str
    private: bool


@dataclass(frozen=True)
class File:
    content: bytes
    sha: str


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _valid_name(name) -> bool:
    return isinstance(name, str) and REPO_NAME.fullmatch(name) is not None and name not in {'.', '..'}


def target_name(full_name: str) -> str:
    parts = full_name.split('/')
    if len(parts) != 2 or parts[0].casefold() != OWNER or not _valid_name(parts[1]):
        raise LabIndexError(f'GITHUB_REPOSITORY: ожидается {OWNER}/имя-репозитория')
    return parts[1]


def validate_repository_url(url, name: str) -> None:
    if not isinstance(url, str) or not url.isascii() or not _valid_name(name):
        raise APIError('API: некорректный URL репозитория')
    # Full matching also rejects credentials, ports, query strings and fragments.
    expected = f'https://github.com/{OWNER}/{name}'
    if url.casefold() != expected.casefold():
        raise APIError('API: некорректный URL репозитория')


def _api_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        valid = (parsed.scheme == 'https' and parsed.netloc == 'api.github.com'
                 and not parsed.fragment and parsed.path.startswith('/'))
    except ValueError:
        valid = False
    if not valid or any(ord(c) <= 32 or ord(c) >= 127 for c in url):
        raise APIError('API: недопустимый адрес запроса')


def _repository(obj) -> Repository:
    if not isinstance(obj, dict) or not isinstance(obj.get('owner'), dict):
        raise APIError('API: некорректный объект репозитория')
    owner = obj['owner'].get('login')
    if not isinstance(owner, str) or owner.casefold() != OWNER:
        raise APIError('API: неожиданный владелец репозитория')
    name, branch, private = obj.get('name'), obj.get('default_branch'), obj.get('private')
    if (not _valid_name(name) or not isinstance(branch, str) or not branch
            or len(branch) > 1024 or any(ord(c) < 32 or ord(c) == 127 for c in branch)
            or type(private) is not bool):
        raise APIError('API: некорректные поля репозитория')
    validate_repository_url(obj.get('html_url'), name)
    return Repository(name, branch, obj['html_url'], private)


def _page_number(url: str) -> int:
    _api_url(url)
    parsed = urlsplit(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if (parsed.path != '/user/repos' or set(query) != set(LIST_QUERY) | {'page'}
            or any(query.get(k) != [v] for k, v in LIST_QUERY.items())):
        raise APIError('API: недопустимая ссылка пагинации')
    page = query['page']
    if len(page) != 1 or not re.fullmatch(r'[1-9][0-9]{0,8}', page[0]):
        raise APIError('API: некорректный номер страницы')
    return int(page[0])


def _links(header: str) -> dict[str, tuple[str, int]]:
    links = {}
    if not header:
        return links
    for part in header.split(','):
        match = re.fullmatch(r'\s*<([^<>]+)>\s*;\s*rel="([a-z ]+)"\s*', part)
        if match is None:
            raise APIError('API: повреждён заголовок пагинации')
        url, relations = match.groups()
        page = _page_number(url)
        for relation in relations.split():
            if relation in links:
                raise APIError('API: повторяющаяся ссылка пагинации')
            links[relation] = (url, page)
    return links


def _retry_delay(headers, attempt: int, spent: float) -> float:
    delay = float(2 ** attempt)
    retry_after = headers.get('Retry-After')
    if retry_after is not None:
        try:
            wait = float(retry_after)
        except ValueError:
            try:
                wait = parsedate_to_datetime(retry_after).timestamp() - time.time()
            except (ValueError, TypeError, OverflowError):
                raise APIError('API: некорректный Retry-After') from None
        if not math.isfinite(wait):
            raise APIError('API: некорректный Retry-After')
        delay = max(delay, wait)
    if headers.get('X-RateLimit-Remaining') == '0':
        try:
            reset = float(headers.get('X-RateLimit-Reset', '0'))
        except ValueError:
            raise APIError('API: некорректные заголовки лимита') from None
        if not math.isfinite(reset):
            raise APIError('API: некорректные заголовки лимита')
        delay = max(delay, reset - time.time())
    if not math.isfinite(delay) or spent + delay > RETRY_BUDGET:
        raise APIError('API: лимит запросов или превышен бюджет ожидания; повторите сверку позже')
    return delay


class GitHub:
    def __init__(self, token: str):
        if not token or not re.fullmatch(r'[\x21-\x7e]+', token):
            raise LabIndexError('некорректный формат токена')
        self._token = token
        self._opener = build_opener(NoRedirect())

    def _request(self, method: str, path: str, *, payload=None, missing=False, empty=False):
        url = path if path.startswith('https://') else API + path
        _api_url(url)
        body = None if payload is None else json.dumps(payload).encode('utf-8')
        headers = {
            'Authorization': f'Bearer {self._token}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': API_VERSION,
            'User-Agent': 'lab-index/1.0',
            'Content-Type': 'application/json',
        }
        attempts = 3 if method == 'GET' else 1
        spent = 0.0
        for attempt in range(attempts):
            retry_headers = {}
            try:
                request = Request(url, data=body, headers=headers, method=method)
                with self._opener.open(request, timeout=TIMEOUT) as response:
                    raw = response.read(MAX_RESPONSE + 1)
                    if len(raw) > MAX_RESPONSE:
                        raise APIError('API: ответ превышает допустимый размер', ambiguous=method == 'PUT')
                    length = response.headers.get('Content-Length')
                    if length is not None and (re.fullmatch(r'[0-9]{1,10}', length) is None
                                               or int(length) != len(raw)):
                        raise APIError('API: неполный HTTP-ответ', ambiguous=method == 'PUT')
                    if response.status != 200:
                        raise APIError('API: неожиданный успешный HTTP-статус', ambiguous=method == 'PUT')
                    try:
                        obj = json.loads(raw.decode('utf-8'))
                    except (ValueError, UnicodeError, RecursionError):
                        raise APIError('API: некорректный JSON', ambiguous=method == 'PUT') from None
                    return obj, response.headers
            except HTTPError as error:
                status, retry_headers = error.code, error.headers
                with error:
                    if status == 404 and missing:
                        return _MISSING, retry_headers
                    if status == 409 and empty:
                        raw = error.read(MAX_RESPONSE + 1)
                        try:
                            obj = json.loads(raw) if len(raw) <= MAX_RESPONSE else None
                        except (ValueError, UnicodeError, RecursionError):
                            obj = None
                        if isinstance(obj, dict) and obj.get('message') in {
                            'Git Repository is empty.', 'This repository is empty.',
                        }:
                            return _MISSING, retry_headers
                rate_limited = status == 403 and (
                    retry_headers.get('X-RateLimit-Remaining') == '0'
                    or retry_headers.get('Retry-After') is not None
                )
                if method != 'GET' or not (rate_limited or status in {429, 500, 502, 503, 504}):
                    raise APIError(f'API: HTTP {status}', status=status,
                                   ambiguous=method == 'PUT' and status >= 500) from None
                failure = APIError(f'API: HTTP {status}; попытки чтения исчерпаны', status=status)
            except (URLError, OSError, http.client.HTTPException):
                failure = APIError('API: сетевая ошибка или тайм-аут', ambiguous=method == 'PUT')
                if method != 'GET':
                    raise failure from None
            if attempt + 1 == attempts:
                raise failure from None
            delay = _retry_delay(retry_headers, attempt, spent)
            time.sleep(delay)
            spent += delay
        raise AssertionError('unreachable')

    def verify_owner(self) -> None:
        obj, _ = self._request('GET', '/user')
        if (not isinstance(obj, dict) or not isinstance(obj.get('login'), str)
                or obj['login'].casefold() != OWNER):
            raise LabIndexError(f'LABS_READ_TOKEN должен принадлежать {OWNER}')

    def repository(self, name: str) -> Repository:
        if not _valid_name(name):
            raise APIError('API: некорректное имя репозитория')
        obj, _ = self._request('GET', f'/repos/{OWNER}/{quote(name, safe="")}')
        repo = _repository(obj)
        if repo.name.casefold() != name.casefold():
            raise APIError('API: целевой репозиторий изменился; повторите сверку')
        return repo

    def repositories(self):
        url = f'{API}/user/repos?{urlencode(LIST_QUERY)}&page=1'
        page = last = 1
        ids, names = set(), set()
        while True:
            obj, headers = self._request('GET', url)
            if not isinstance(obj, list) or len(obj) > 100:
                raise APIError('API: вместо страницы репозиториев получен некорректный ответ')
            links = _links(headers.get('Link', ''))
            if 'last' in links:
                last = max(last, links['last'][1])
            if not obj and (page < last or 'next' in links):
                raise APIError('API: пустая промежуточная страница')
            for item in obj:
                if not isinstance(item, dict) or not isinstance(item.get('owner'), dict):
                    raise APIError('API: некорректный владелец в списке репозиториев')
                owner = item['owner'].get('login')
                if not isinstance(owner, str) or not owner:
                    raise APIError('API: некорректный владелец в списке репозиториев')
                if owner.casefold() != OWNER:
                    continue
                repo = _repository(item)
                repo_id = item.get('id')
                if (type(repo_id) is not int or repo_id <= 0 or repo_id in ids
                        or repo.name.casefold() in names):
                    raise APIError('API: противоречивый или повторный репозиторий в пагинации')
                ids.add(repo_id)
                names.add(repo.name.casefold())
                yield repo
            if 'next' not in links:
                if page < last:
                    raise APIError('API: пагинация оборвалась до последней страницы')
                break
            url, next_page = links['next']
            if next_page != page + 1:
                raise APIError('API: нарушен порядок страниц')
            page = next_page

    def file(self, repo: Repository, path: str) -> File | None:
        if path not in {'.lab.yml', 'README.md'}:
            raise APIError('API: неподдерживаемый путь')
        endpoint = (f'/repos/{OWNER}/{quote(repo.name, safe="")}/contents/{quote(path, safe="")}'
                    f'?{urlencode({"ref": repo.branch})}')
        optional = path == '.lab.yml'
        obj, _ = self._request('GET', endpoint, missing=optional, empty=optional)
        if obj is _MISSING and optional:
            return None
        # GitHub historically reports submodules as type=file; check their field too.
        if (not isinstance(obj, dict) or obj.get('type') != 'file'
                or 'submodule_git_url' in obj or 'target' in obj
                or obj.get('path') != path or obj.get('encoding') != 'base64'):
            raise APIError(f'API: {path}: ожидается обычный файл с Base64-содержимым')
        size, sha, content = obj.get('size'), obj.get('sha'), obj.get('content')
        limit = MAX_BYTES if optional else MAX_README
        if type(size) is not int or not 0 <= size <= limit:
            raise APIError(f'API: {path}: недопустимый размер файла')
        if not isinstance(sha, str) or SHA.fullmatch(sha) is None or not isinstance(content, str):
            raise APIError(f'API: {path}: некорректные поля файла')
        encoded = content.replace('\n', '').replace('\r', '')
        if len(encoded) != 4 * ((size + 2) // 3):
            raise APIError(f'API: {path}: размер Base64 не совпадает с размером файла')
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise APIError(f'API: {path}: некорректный Base64') from None
        if len(decoded) != size:
            raise APIError(f'API: {path}: размер содержимого не совпадает с ответом')
        return File(decoded, sha)

    def publish(self, repo: Repository, original: File, content: bytes) -> None:
        if content == original.content:
            return
        if len(content) > MAX_README:
            raise LabIndexError('README.md: результат больше 1 МиБ')
        endpoint = f'/repos/{OWNER}/{quote(repo.name, safe="")}/contents/README.md'
        try:
            obj, _ = self._request('PUT', endpoint, payload={
                'message': 'Обновлён каталог учебных работ', 'content': base64.b64encode(content).decode('ascii'),
                'sha': original.sha, 'branch': repo.branch,
            })
            if (not isinstance(obj, dict) or not isinstance(obj.get('content'), dict)
                    or obj['content'].get('path') != 'README.md'
                    or not isinstance(obj.get('commit'), dict)
                    or not isinstance(obj['commit'].get('sha'), str)
                    or SHA.fullmatch(obj['commit']['sha']) is None):
                raise APIError('API: неподтверждённый ответ записи', ambiguous=True)
        except APIError as error:
            if not error.ambiguous:
                if error.status in {409, 422}:
                    raise LabIndexError('README.md: конфликт версии или запрет записи; нужна новая полная сверка') from None
                raise
            # A timed-out PUT might already have committed. Never retry the write.
            try:
                actual = self.file(repo, 'README.md')
                if actual.content == content:
                    return
            except LabIndexError:
                pass
            raise LabIndexError('README.md: публикация не подтверждена; запись не повторялась') from None
