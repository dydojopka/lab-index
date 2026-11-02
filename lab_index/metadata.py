"""Bounded, deliberately strict .lab.yml parsing."""

from dataclasses import dataclass
import unicodedata

import yaml
from yaml.events import (
    AliasEvent, DocumentStartEvent, MappingEndEvent, MappingStartEvent,
    SequenceEndEvent, SequenceStartEvent,
)

from . import LabIndexError

MAX_BYTES = 64 * 1024
MAX_TITLE = 500
MAX_SECTIONS = 32
MAX_NUMBER = 2_147_483_647
MAX_YAML_DEPTH = 16  # YAML nesting, not the length of the flat sections list.


@dataclass(frozen=True)
class NumberedTitle:
    number: int
    title: str


@dataclass(frozen=True)
class Metadata:
    course: str
    sections: tuple[NumberedTitle, ...]
    assignment: NumberedTitle


class MetadataError(LabIndexError):
    pass


class StrictLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            # Schema keys are strings; reject complex keys before constructing them.
            if not isinstance(key_node, yaml.ScalarNode) or key_node.tag != 'tag:yaml.org,2002:str':
                raise MetadataError('ключи должны быть строками')
            key = self.construct_object(key_node, deep=deep)
            if key == '<<':
                raise MetadataError('merge keys запрещены')
            if key in result:
                raise MetadataError('повторяющиеся ключи запрещены')
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _check_events(text: str) -> None:
    """Check resource bounds and YAML features before composing any object tree."""
    depth = documents = 0
    for event in yaml.parse(text, Loader=yaml.SafeLoader):
        if isinstance(event, DocumentStartEvent):
            documents += 1
            if documents > 1:
                raise MetadataError('разрешён только один YAML-документ')
        if isinstance(event, AliasEvent) or getattr(event, 'anchor', None) is not None:
            raise MetadataError('anchors и aliases запрещены')
        if getattr(event, 'tag', None) is not None:
            raise MetadataError('явные YAML-теги запрещены')
        if isinstance(event, (MappingStartEvent, SequenceStartEvent)):
            depth += 1
            if depth > MAX_YAML_DEPTH:
                raise MetadataError('превышена допустимая глубина YAML')
        elif isinstance(event, (MappingEndEvent, SequenceEndEvent)):
            depth -= 1


def _object(value, fields: set[str], path: str) -> dict:
    if type(value) is not dict:
        raise MetadataError(f'{path}: ожидается объект')
    missing = fields - value.keys()
    if missing:
        raise MetadataError(f'{path}: отсутствуют поля {", ".join(sorted(missing))}')
    if value.keys() - fields:
        # Do not echo unknown keys: arbitrary input can contain secrets or log commands.
        raise MetadataError(f'{path}: неизвестные поля')
    return value


def _title(value, path: str) -> str:
    if type(value) is not str or not value or len(value) > MAX_TITLE:
        raise MetadataError(f'{path}: нужна непустая строка до {MAX_TITLE} символов')
    if value.strip() != value or any(
        unicodedata.category(char).startswith('C') or char in '\u2028\u2029'
        for char in value
    ):
        raise MetadataError(f'{path}: запрещены управляющие символы, переводы строк и пробелы по краям')
    return value


def _numbered(value, path: str) -> NumberedTitle:
    obj = _object(value, {'number', 'title'}, path)
    number = obj['number']
    if type(number) is not int or not 1 <= number <= MAX_NUMBER:
        raise MetadataError(f'{path}.number: нужно целое число от 1 до {MAX_NUMBER}')
    return NumberedTitle(number, _title(obj['title'], f'{path}.title'))


def parse_metadata(data: bytes) -> Metadata:
    if len(data) > MAX_BYTES:
        raise MetadataError('файл больше 64 КиБ')
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        raise MetadataError('файл должен быть в UTF-8') from None
    try:
        _check_events(text)
        obj = yaml.load(text, Loader=StrictLoader)
    except (yaml.YAMLError, ValueError, RecursionError):
        # PyYAML errors include source snippets; never expose them in public logs.
        raise MetadataError('некорректный YAML') from None
    obj = _object(obj, {'course', 'sections', 'assignment'}, 'метаданные')
    course = _title(obj['course'], 'course')
    sections = obj['sections']
    if type(sections) is not list or len(sections) > MAX_SECTIONS:
        raise MetadataError(f'sections: нужен список не более {MAX_SECTIONS} разделов')
    return Metadata(
        course,
        tuple(_numbered(item, f'sections[{i}]') for i, item in enumerate(sections)),
        _numbered(obj['assignment'], 'assignment'),
    )
