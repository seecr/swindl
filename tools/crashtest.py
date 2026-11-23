## begin license ##
#
# "Swindl"(Seecr Web Index and Database Lib) combines sjdbl's files and sil's index
#
# Copyright (C) 2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "swindl"
#
# "swindl" is licensed under the MIT License; see the LICENSE file.
# SPDX-License-Identifier: MIT
#
## end license ##

"""Crash test: kills a process that runs transactions, at random moments, many times,
and checks after each kill that nothing was lost or half done.

    PYTHONPATH=. python tools/crashtest.py                 # 200 rounds, all modes
    PYTHONPATH=. python tools/crashtest.py --rounds 2000 --commit timer

The data: GROUPS groups of PER_GROUP items. Every transaction gives all items of one
group the next version, and sometimes replaces one of them (a delete and a create).
After every kill (SIGKILL: no cleanup, no finally) a fresh process opens the store
(which finishes what the crash left) and checks:

- every group has PER_GROUP items, all with the same version: no transaction is in the
  files halfway;
- swindl-check finds nothing: the index matches the files;
- nothing committed went missing: after each transaction returned, the killed process
  noted the group's version; the files have at least that version.

Not part of the package; run it before a release that touches the commit path."""

import argparse
import asyncio
import json
import os
import random
import signal
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from sil.indexfield import IndexField
from sjdbl.field import Field

from swindl.check import check
from swindl.store import Base
from swindl.store.indexes import Commit
from swindl.store.store import Store

GROUPS = 8
PER_GROUP = 4


class Item(Base):
    FIELDS = Base.FIELDS + [Field.int("group"), Field.int("version")]
    INDEX = Base.INDEX + [IndexField.int("group"), IndexField.int("version")]

    def index_values(self):
        values = super().index_values()
        values.update(group=self.group, version=self.version)
        return values


def by_group(store):
    groups = defaultdict(list)
    for item in store._store.list(Item):  # the files
        groups[item.group].append(item)
    return groups


def transactions(store, seen_file, rng):
    """Forever: one group to its next version. After each transaction, the version is
    appended to seen_file: it was committed, so it must survive the kill."""
    groups = by_group(store)
    if not groups:
        with store.transaction():
            for group in range(GROUPS):
                for _ in range(PER_GROUP):
                    store.put(Item.create(group=group, version=0))
        groups = by_group(store)
    with seen_file.open("a") as seen:
        while True:
            group = rng.randrange(GROUPS)
            items = groups[group]
            version = items[0].version + 1
            with store.transaction():
                for item in items:
                    item.update(version=version)
                    store.put(item)
                if rng.random() < 0.3:
                    gone = items.pop(rng.randrange(len(items)))
                    store.delete(gone)
                    new = Item.create(group=group, version=version)
                    store.put(new)
                    items.append(new)
            seen.write(f"{group} {version}\n")
            seen.flush()
            yield


def child(data_dir, mode, seed):
    rng = random.Random(seed)
    seen_file = data_dir / "seen"
    if mode == "immediate":
        store = Store(data_dir / "data", [Item], commit=Commit(immediate=True))
        for _ in transactions(store, seen_file, rng):
            pass
    elif mode == "on_search":
        commit = Commit(on_search=True, timeout=0)
        store = Store(data_dir / "data", [Item], commit=commit)
        for nr, _ in enumerate(transactions(store, seen_file, rng)):
            if nr % 3 == 0:  # a search now and then: it commits
                store.find_one(Item, group=rng.randrange(GROUPS))
    else:

        async def run():
            store = Store(data_dir / "data", [Item], commit=Commit(timeout=0.02))
            for nr, _ in enumerate(transactions(store, seen_file, rng)):
                if nr % 5 == 0:
                    await asyncio.sleep(0.001)  # let the timer commit

        asyncio.run(run())


def verify(data_dir):
    """In a fresh process: what the crash left, then open (recovery) and check."""
    data = data_dir / "data"
    left = []
    if (data / "store" / "commit.log").exists():
        left.append("commit.log")
    if list((data / "store").glob("*/*.tmp")):
        left.append("tmp")
    pending = data / "index" / "pending.log"
    if pending.exists() and pending.stat().st_size:
        left.append("pending")

    errors = []
    store = Store(data, [Item], commit=Commit(immediate=True))
    groups = by_group(store)
    store.disconnect()
    newest_seen = {}
    if (data_dir / "seen").exists():
        for line in (data_dir / "seen").read_text().split("\n"):
            if line.strip():
                group, version = map(int, line.split())
                newest_seen[group] = max(version, newest_seen.get(group, 0))
    for group, items in groups.items():
        versions = {item.version for item in items}
        if len(items) != PER_GROUP or len(versions) != 1:
            errors.append(f"group {group}: {len(items)} items, versions {versions}")
        elif versions.pop() < newest_seen.get(group, 0):
            errors.append(f"group {group}: a committed version is lost")
    errors.extend(check(data, [Item]))
    print(json.dumps({"left": left, "errors": errors}))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--rounds", type=int, default=200)
    parser.add_argument(
        "--commit", choices=["immediate", "timer", "on_search", "all"], default="all"
    )
    parser.add_argument("--dir", type=Path, help="default: a new temporary directory")
    parser.add_argument("--max-delay", type=float, default=0.3, help="seconds")
    parser.add_argument("--child", nargs=3, help=argparse.SUPPRESS)
    parser.add_argument("--verify", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        child(Path(args.child[0]), args.child[1], int(args.child[2]))
        return 0
    if args.verify:
        verify(args.verify)
        return 0

    modes = (
        ["immediate", "timer", "on_search"] if args.commit == "all" else [args.commit]
    )
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))
    failures = 0
    for mode in modes:
        data_dir = (args.dir or Path(tempfile.mkdtemp(prefix="crashtest-"))) / mode
        data_dir.mkdir(parents=True, exist_ok=True)
        left_counts = defaultdict(int)
        started = time.time()
        for round_nr in range(args.rounds):
            proc = subprocess.Popen(
                [
                    sys.executable,
                    __file__,
                    "--child",
                    str(data_dir),
                    mode,
                    str(round_nr),
                ],
                env=env,
            )
            time.sleep(random.uniform(0.05, args.max_delay))
            proc.send_signal(signal.SIGKILL)
            proc.wait()
            result = subprocess.run(
                [sys.executable, __file__, "--verify", str(data_dir)],
                env=env,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(result.stderr, file=sys.stderr)
                return 2
            outcome = json.loads(result.stdout.strip().split("\n")[-1])
            for what in outcome["left"]:
                left_counts[what] += 1
            if outcome["errors"]:
                failures += 1
                print(f"{mode} round {round_nr}: " + "; ".join(outcome["errors"]))
        print(
            f"{mode}: {args.rounds} kills in {time.time() - started:.0f}s; "
            f"left behind and finished at open: "
            + (", ".join(f"{k} {v}x" for k, v in sorted(left_counts.items())) or "-")
            + f"; failures: {failures}"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
