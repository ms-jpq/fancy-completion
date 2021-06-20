from typing import Iterator
from unittest import TestCase
from uuid import uuid4

from ...coq.ci.load import load
from ...coq.shared.types import Context, EditEnv, SnippetEdit
from ...coq.snippets.parse import parse

_THRESHOLD = 0.95


class Parser(TestCase):
    def test_1(self) -> None:
        ctx = Context(
            uid=uuid4(),
            cwd="",
            filename="",
            filetype="",
            position=(0, 0),
            line="",
            line_before="",
            line_after="",
            words="",
            words_before="",
            words_after="",
            syms="",
            syms_before="",
            syms_after="",
        )
        env = EditEnv(linefeed="\n", tabstop=4, expandtab=True)

        def cont() -> Iterator[SnippetEdit]:
            specs = load()
            for snippets in specs.snippets.values():
                for snippet in snippets:
                    edit = SnippetEdit(
                        new_text=snippet.content,
                        grammar=snippet.grammar,
                    )
                    yield edit

        edits = tuple(cont())

        def errs() -> Iterator[Exception]:
            for edit in edits:
                try:
                    parse(ctx, env=env, snippet=edit)
                except Exception as e:
                    print(e)
                    yield e

        errors = tuple(errs())
        succ = len(errors) / len(edits) if edits else 0

        self.assertGreater(succ, _THRESHOLD)

        if succ < _THRESHOLD:
            for err in errors:
                print(err)

