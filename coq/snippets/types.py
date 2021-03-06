from dataclasses import dataclass
from typing import AbstractSet, Mapping, Sequence


class LoadError(Exception):
    pass


@dataclass(frozen=True)
class ParsedSnippet:
    grammar: str
    content: str
    label: str
    doc: str
    matches: AbstractSet[str]
    options: AbstractSet[str]


@dataclass(frozen=True)
class MetaSnippets:
    snippets: Sequence[ParsedSnippet]
    extends: AbstractSet[str]


@dataclass(frozen=True)
class SnippetSpecs:
    snippets: Mapping[str, Sequence[ParsedSnippet]]
    extends: Mapping[str, AbstractSet[str]]

