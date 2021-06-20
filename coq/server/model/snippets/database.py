from contextlib import closing
from locale import strcoll
from sqlite3 import Connection, Cursor, Row
from typing import Iterable, Iterator, Mapping, MutableSet, Sequence, TypedDict
from uuid import uuid4

from std2.sqllite3 import escape, with_transaction

from ....consts import SNIPPET_DB
from ....registry import pool
from ....shared.executor import Executor
from ....shared.parse import lower, normalize
from ....snippets.types import ParsedSnippet
from .sql import sql


class _Snip(TypedDict):
    grammar: str
    prefix: str
    snippet: str
    label: str
    doc: str


def _like_esc(like: str) -> str:
    escaped = escape(nono={"%", "_"}, escape="!", param=like)
    return f"{escaped}%"


def _init() -> Connection:
    conn = Connection(SNIPPET_DB, isolation_level=None)
    conn.row_factory = Row
    conn.create_collation("X_COLL", strcoll)
    conn.create_function("X_LOWER", narg=1, func=lower, deterministic=True)
    conn.create_function("X_NORM", narg=1, func=normalize, deterministic=True)
    conn.create_function("X_LIKE_ESC", narg=1, func=_like_esc, deterministic=True)
    conn.executescript(sql("create", "pragma"))
    conn.executescript(sql("create", "tables"))
    return conn


def _ensure_ft(cursor: Cursor, filetypes: Iterable[str]) -> None:
    def it() -> Iterator[Mapping]:
        for ft in filetypes:
            yield {"filetype": ft}

    cursor.executemany(sql("insert", "filetype"), it())


class SDB:
    def __init__(self) -> None:
        self._ex = Executor(pool)
        self._conn: Connection = self._ex.submit(_init)
        self._seen: MutableSet[str] = set()

    def add_exts(self, exts: Mapping[str, Iterable[str]]) -> None:
        def it() -> Iterator[Mapping]:
            for src, dests in exts.items():
                for dest in dests:
                    yield {"src": src, "dest": dest}

        def cont() -> None:
            with closing(self._conn.cursor()) as cursor:
                with with_transaction(cursor):
                    _ensure_ft(cursor, filetypes=exts)
                    cursor.executemany(sql("insert", "extension"), it())

        self._ex.submit(cont)

    def populate(self, filetype: str, snippets: Iterable[ParsedSnippet]) -> None:
        def cont() -> None:
            if filetype not in self._seen:
                self._seen.add(filetype)
                with closing(self._conn.cursor()) as cursor:
                    with with_transaction(cursor):
                        _ensure_ft(cursor, filetypes=(filetype,))
                        for row_id, snippet in zip(iter(uuid4, None), snippets):
                            cursor.execute(
                                sql("insert", "snippet"),
                                {
                                    "rowid": row_id,
                                    "filetype": filetype,
                                    "grammar": snippet.grammar,
                                    "content": snippet.content,
                                    "label": snippet.label,
                                    "doc": snippet.doc,
                                },
                            )
                            for match in snippet.matches:
                                cursor.execute(
                                    sql("insert", "match"),
                                    {"snippet_id": row_id, "match": match},
                                )
                            for option in snippet.options:
                                cursor.execute(
                                    sql("insert", "option"),
                                    {"snippet_id": row_id, "option": option},
                                )

        self._ex.submit(cont)

    def select(self, filetype: str, word: str) -> Sequence[_Snip]:
        def cont() -> Sequence[_Snip]:
            with closing(self._conn.cursor()) as cursor:
                with with_transaction(cursor):
                    cursor.execute(
                        sql("select", "snippets"), {"filetype": filetype, "word": word}
                    )

                    def c1() -> Iterator[_Snip]:
                        for row in cursor.fetchall():
                            cursor.execute(
                                sql("select", "matches"),
                                {"snippet_id": row["snippet_id"], "word": word},
                            )
                            snip = _Snip(
                                grammar=row["grammar"],
                                prefix=cursor.fetchone()["match"],
                                snippet=row["content"],
                                label=row["label"],
                                doc=row["doc"],
                            )
                            yield snip

                    return tuple(c1())

        return self._ex.submit(cont)
