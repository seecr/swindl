# What swindl promises

swindl keeps objects in sjdbl's JSON files and makes them searchable with sil's index.
This page says what you can count on, what you cannot, and where the limits are. It is
for deciding whether swindl fits an application, and for knowing what to do after
something went wrong.

The short version: **one process, crash safe, the files are the truth.**

## Promised

**Transactions are atomic.** Every `put` and `delete` is a transaction, and so is a
`with store.transaction():` block with many of them. A transaction is in the files
completely or not at all:

- an exception in the block: nothing is stored, and the objects get their old revisions
  back;
- a crash of the process or the machine at any moment: when the store is opened again, a
  transaction that reached its commit point is finished, and one that didn't leaves no
  trace.

**Durable when it returns.** When `put`, `delete` or the transaction block returns, the
change is on disk (`fsync` of the files and their directories) on Linux. A power failure
after that does not lose it.

**The index catches up.** The index is derived from the files. Changes that a crash left
unindexed or uncommitted are indexed again from the files when the store is opened. You
never need a reindex because of a crash.

**No lost updates.** Every object has a revision that changes at every put. Saving an
object that someone else saved since you loaded it raises `HasChangedException` instead
of overwriting their change. A form that carries the `qrid` finds out the same way.

**Threads are safe.** Puts, deletes and transactions from several threads are serialized
by the store's lock; the index gets changes in the same order as the files.

**Readable without swindl.** Every object is an indented JSON file:
`store/<Model>/<id>.json`. You can read, grep, diff and (carefully, with the application
stopped) fix them by hand.

## Not promised

**Readers are not isolated.** `get` and `query` take no lock. While a transaction is
being written (milliseconds), another thread can see some of its files new and others
still old. Within the transaction's own thread, `get` sees the transaction.

**Only what you write is checked.** The revision check covers the objects a transaction
puts, not the ones it only read. Two transactions that each decide on something the other
changes, without writing it, are not detected ("write skew"). Put what a decision depends
on, or keep such decisions in one place.

**No constraints.** There is no "unique" and no foreign keys. A reference to an object
that was deleted shows up when it is loaded (`DanglingReferenceError`), and
`swindl-check` reports it.

**Queries see committed changes.** With the default `Commit()` the index commits every
5 seconds; a query can be up to that much behind the files. `get` never is.

**Durability on macOS is weaker.** `fsync` there does not flush the drive's own cache. A
development machine is fine; run production on Linux.

## Limits

**One process per data directory.** Several threads, yes; several processes (e.g.
`uvicorn --workers 4`) on the same directory, no. sil's index allows one writer, and
sjdbl's revision checks and recovery assume one process.

**Full passes read every file.** `store.reindex()` and sjdbl's `list()` read all files of
a model. That is fine for tens to hundreds of thousands of objects per model; see the
benchmarks for numbers. Searching never reads all files: it uses the index and reads only
the objects of the page.

**Many files in one directory.** One file per object, one directory per model. Modern
file systems (ext4, XFS, APFS) handle hundreds of thousands of files in a directory well;
`ls` gets slow before swindl does.

**What you can search is what you indexed.** Queries go to sil's index; there are no
ad-hoc queries over fields that are not in `INDEX`. A new index field needs a reindex.

## After a crash

Nothing to do: open the store as always. In the log you may see

- `finished a transaction interrupted by a crash` (sjdbl): a commit was completed;
- `removed (a transaction that never committed)` (sjdbl): leftovers of one that never
  reached its commit point;
- `Indexed N object(s) again that a crash left unindexed` (swindl): the index caught up.

To look before opening (it changes nothing):

```sh
swindl-check /data/myapp myapp.models:ALL_MODELS
```

It reports a leftover `commit.log`, temporary files, objects waiting in
`index/pending.log`, index entries that differ from the files, unreadable files and
references to objects that don't exist. Exit code 0 means all is well.

What repairs what:

| Found | Repair |
|---|---|
| `commit.log`, `.tmp` files, `pending.log` | open the store |
| index differs from the files | reindex (`actions/reindex`) |
| an unreadable file, a dangling reference | a person: the file is plain JSON |

## Backups

The index is derived: back up `store/` (and the rest of the application's data
directory), not `index/`. After a restore, reindex.

For a consistent backup, the files must not change while they are copied:

- a file system snapshot (LVM, ZFS, btrfs) and back up the snapshot; or
- stop the application, or hold the store's lock while copying.

A copy that happened to include a `commit.log` and `.tmp` files is fine: the commit is
finished when the restored store is opened. A copy made without any of these precautions
can have one object newer than another; each file on its own is always whole (files are
replaced by a rename, never written in place).

## How we know

- Unit tests raise at each step of a commit, and real crashes are tested with a child
  process that dies with `os._exit` at each step of a transaction
  (`swindl/store/crash_test.py`, `sjdbl/commit_test.py`).
- `tools/crashtest.py` kills a process that runs transactions with `SIGKILL` at random
  moments, hundreds of times, and checks after each kill that every transaction is whole,
  nothing committed was lost, and `swindl-check` finds nothing. Run before every release
  that touches the commit path.
