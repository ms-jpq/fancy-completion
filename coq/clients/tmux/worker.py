from dataclasses import dataclass
from shutil import which
from subprocess import CalledProcessError, check_output
from time import sleep
from typing import AbstractSet, Iterator, Sequence, Tuple

from ...shared.parse import coalesce
from ...shared.runtime import Supervisor
from ...shared.runtime import Worker as BaseWorker
from ...shared.types import Completion, Context, Edit
from .database import Database

_POLL_INTERVAL = 1
_PREFIX_LEN = 3


@dataclass(frozen=True)
class _Pane:
    uid: str
    pane_active: bool
    window_active: bool


def _panes() -> Sequence[_Pane]:
    try:
        out = check_output(
            (
                "tmux",
                "list-panes",
                "-s",
                "-F",
                "#{pane_id} #{pane_active} #{window_active}",
            ),
            text=True,
        )

    except CalledProcessError:
        return ()
    else:

        def cont() -> Iterator[_Pane]:
            for line in out.strip().splitlines():
                pane_id, pane_active, window_active = line.split(" ")
                pane = _Pane(
                    uid=pane_id,
                    pane_active=bool(int(pane_active)),
                    window_active=bool(int(window_active)),
                )
                yield pane

        return tuple(cont())


def _cur() -> _Pane:
    for pane in _panes():
        if pane.window_active and pane.window_active:
            return pane
    else:
        assert False


def _screenshot(unifying_chars: AbstractSet[str], uid: str) -> Sequence[str]:
    try:
        out = check_output(("tmux", "capture-pane", "-p", "-t", uid), text=True)
    except CalledProcessError:
        return ()
    else:
        return tuple(coalesce(out, unifying_chars=unifying_chars))


class Worker(BaseWorker[None]):
    def __init__(self, supervisor: Supervisor, misc: None) -> None:
        self._db = Database(supervisor.pool, location=":memory:")

        if which("tmux"):
            supervisor.pool.submit(self._poll)

        super().__init__(supervisor, misc=misc)

    def _poll(self) -> None:
        def cont(pane: _Pane) -> Tuple[_Pane, Sequence[str]]:
            words = _screenshot(self._supervisor.options.unifying_chars, uid=pane.uid)
            return pane, words

        while True:
            snapshot = {
                pane.uid: words
                for pane, words in self._supervisor.pool.map(cont, _panes())
            }
            self._db.periodical(snapshot)
            sleep(_POLL_INTERVAL)

    def work(self, context: Context) -> Iterator[Sequence[Completion]]:
        active = _cur()

        def cont() -> Iterator[Completion]:
            for word in self._db.select(
                _PREFIX_LEN, word=context.words, active_pane=active.uid
            ):
                edit = Edit(new_text=word)
                completion = Completion(primary_edit=edit)
                yield completion

        yield tuple(cont())
