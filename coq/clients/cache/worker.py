from dataclasses import dataclass, replace
from typing import AsyncIterator, Mapping, Sequence, Tuple
from uuid import UUID, uuid4

from ...shared.runtime import Supervisor
from ...shared.timeit import timeit
from ...shared.types import Completion, Context, Edit, SnippetEdit
from .database import Database


@dataclass(frozen=True)
class _CacheCtx:
    change_id: UUID
    commit_id: UUID
    buf_id: int
    row: int
    line_before: str
    comps: Mapping[bytes, Completion]


def _use_cache(cache: _CacheCtx, ctx: Context) -> bool:
    row, _ = ctx.position
    return (
        cache.commit_id == ctx.commit_id
        and len(cache.comps) > 0
        and ctx.buf_id == cache.buf_id
        and row == cache.row
        and ctx.line_before.startswith(cache.line_before)
    )


def _trans(comp: Completion) -> Completion:
    p_edit = comp.primary_edit
    edit = (
        p_edit
        if type(p_edit) in {Edit, SnippetEdit}
        else Edit(new_text=p_edit.new_text)
    )
    return replace(comp, primary_edit=edit, secondary_edits=())


class CacheWorker:
    def __init__(self, supervisor: Supervisor) -> None:
        self._soup = supervisor
        self._db = Database(supervisor.pool)
        self._cache_ctx = _CacheCtx(
            change_id=uuid4(),
            commit_id=uuid4(),
            buf_id=-1,
            row=-1,
            line_before="",
            comps={},
        )

    async def _use_cache(
        self, context: Context
    ) -> Tuple[bool, AsyncIterator[Completion]]:
        cache_ctx = self._cache_ctx
        use_cache = _use_cache(cache_ctx, ctx=context)

        async def cont() -> AsyncIterator[Completion]:
            if use_cache:
                with timeit("CACHE -- GET"):
                    match = context.words or context.syms
                    hashes = await self._db.select(
                        self._soup.options, word=match, limitless=context.manual
                    )
                    for hash_id in hashes:
                        cmp = cache_ctx.comps.get(hash_id)
                        if cmp:
                            yield cmp

        return use_cache, cont()

    async def _set_cache(
        self, context: Context, completions: Sequence[Completion]
    ) -> None:
        with timeit("CACHE -- SET"):
            cache_ctx = self._cache_ctx

            use_cache = _use_cache(cache_ctx, ctx=context)
            row, _ = context.position
            new_comps = {c.uid.bytes: c for c in map(_trans, completions)}

            comps = {**cache_ctx.comps, **new_comps} if use_cache else new_comps
            new_cache_ctx = _CacheCtx(
                change_id=context.change_id,
                commit_id=context.commit_id,
                buf_id=context.buf_id,
                row=row,
                line_before=context.line_before,
                comps=comps,
            )
            pool = {
                hash_id: c.primary_edit.new_text for hash_id, c in new_comps.items()
            }
            await self._db.populate(use_cache, pool=pool)
            self._cache_ctx = new_cache_ctx

