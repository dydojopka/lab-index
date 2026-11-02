"""Catalogue identity and conflicts; presentation order is locale-independent."""

from dataclasses import dataclass, field
from collections.abc import Iterable
import unicodedata

from . import LabIndexError
from .github import Repository
from .metadata import Metadata


@dataclass(frozen=True)
class Work:
    repository: Repository
    metadata: Metadata


@dataclass
class Node:
    title: str
    assignments: dict[int, Work] = field(default_factory=dict)
    sections: dict[int, 'Node'] = field(default_factory=dict)


def course_key(name: str) -> tuple[str, str]:
    return unicodedata.normalize('NFC', name).casefold().replace('ё', 'е'), name


def build_catalog(works: Iterable[Work]) -> list[Node]:
    courses: dict[str, Node] = {}
    for work in works:
        metadata = work.metadata
        node = courses.setdefault(metadata.course, Node(metadata.course))
        for i, section in enumerate(metadata.sections):
            existing = node.sections.get(section.number)
            if existing is not None and existing.title != section.title:
                raise LabIndexError(
                    f'{work.repository.name}: .lab.yml: sections[{i}]: конфликт названия для номера раздела'
                )
            if any(n != section.number and child.title == section.title for n, child in node.sections.items()):
                raise LabIndexError(
                    f'{work.repository.name}: .lab.yml: sections[{i}]: название раздела имеет другой номер'
                )
            node = node.sections.setdefault(section.number, Node(section.title))
        number = metadata.assignment.number
        if number in node.assignments:
            raise LabIndexError(
                f'{work.repository.name}: .lab.yml: assignment.number: номер занят другой работой'
            )
        node.assignments[number] = work
    return [courses[name] for name in sorted(courses, key=course_key)]
