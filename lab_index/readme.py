"""Literal rendering and byte-preserving replacement of the managed block."""

import html
import re
import string

from . import LabIndexError
from .catalog import Node
from .github import validate_repository_url

START = b'<!-- LAB-INDEX:START -->'
END = b'<!-- LAB-INDEX:END -->'
EMPTY = 'Пока нет учебных работ.'


def block_bounds(data: bytes) -> tuple[int, int, bytes]:
    try:
        data.decode('utf-8')
    except UnicodeDecodeError:
        raise LabIndexError('README.md: ожидается UTF-8') from None
    if data.count(START) != 1 or data.count(END) != 1:
        raise LabIndexError('README.md: нужна ровно одна пара маркеров LAB-INDEX')
    start = re.search(rb'(?m)^' + re.escape(START) + rb'(\r?\n)', data)
    end = re.search(rb'(?m)^' + re.escape(END) + rb'(?:\r?\n|\Z)', data)
    if start is None or end is None or start.end() > end.start():
        raise LabIndexError('README.md: маркеры должны идти по порядку на отдельных строках')
    return start.end(), end.start(), start.group(1)


def replace_block(data: bytes, rendered: str) -> bytes:
    start, end, newline = block_bounds(data)
    body = rendered.encode('utf-8').replace(b'\n', newline)
    return data[:start] + newline + body + newline + newline + data[end:]


def _heading(text: str) -> str:
    # Numeric entities cannot become Markdown links, autolinks, emoji, mentions,
    # emphasis or HTML. Entity decoding happens after Markdown structure parsing.
    return ''.join(f'&#{ord(c)};' if c in string.punctuation else c for c in text)


def _render_node(node: Node, path: tuple[int, ...]) -> list[str]:
    indent = '&nbsp;' * (4 * len(path))
    lines = []
    for number, work in sorted(node.assignments.items()):
        label = '.'.join(map(str, (*path, number)))
        repo = work.repository
        validate_repository_url(repo.url, repo.name)
        suffix = ' (Private)' if repo.private else ''
        lines.append(
            f'{indent}{label}. <a href="{html.escape(repo.url, quote=True)}">'
            f'{html.escape(work.metadata.assignment.title)}</a>{suffix}'
        )
    for number, child in sorted(node.sections.items()):
        child_path = (*path, number)
        label = '.'.join(map(str, child_path))
        lines.append(f'{indent}<strong>{label}. {html.escape(child.title)}</strong>')
        lines.extend(_render_node(child, child_path))
    return lines


def render_catalog(courses: list[Node]) -> str:
    if not courses:
        return EMPTY
    return '\n\n'.join(
        f'## {_heading(course.title)}\n\n<p>\n'
        + '<br>\n'.join(_render_node(course, ())) + '\n</p>'
        for course in courses
    )
