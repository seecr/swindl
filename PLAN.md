# Plan: crash-safe transactions over store and index (sjdbl 0.4.0, swindl 2.2.1 and 3.0.0)

Agreed in November 2026. This replaces the WebAdapter 2 plan (done in swindl 2.0.0; see
git history). The store (sjdbl's files) is the source of truth; the index is derived
from it and can always be redone from the files. So a transaction needs no two-phase
commit: the files are committed atomically with a small redo log, and the index changes
are recorded before that commit and done after it. A crash in between is finished at
startup from the log. That is part of the transaction, not a reindex (see CLAUDE.md).

## Before starting

- In `swindl` and `sjdbl`: check for uncommitted changes and unpushed commits, then
  `git pull`. If anything is off, stop and ask.
- Commit messages start with `JJ: `. flake8, isort and the tests must pass before any
  push (the pre-push hook does this).
- Don't tag or push unless asked.

## What it fixes

1. Two threads saving the same object: swindl's `put` writes the file and then indexes
   without a lock around both, so the older values can reach the index last. The
   `Indexes._indexed` cache has no lock either (a `KeyError` is possible when plain
   `def` endpoints save from Starlette's thread pool).
2. A crash between the file delete and the index delete leaves a dangling id in the
   index; `query()` then returns `None` among its objects.
3. `put(a, b)` is not atomic across files: a crash between two renames leaves half the
   change.
4. `sjdbl.Store.batch()` uses `os.sync()`, which syncs every file system on the machine,
   not just the store.
5. A failing `swindl.Store.batch()` still has its puts in the files and the index; there
   is no way to say "all of this, or nothing".

## 1. swindl 2.2.1: a lock and no `None` in results (fixes 1 and 2)

- `swindl.Store` gets one `threading.RLock`. `put()` and `delete()` hold it around the
  sjdbl write and the index change, so file and index change in the same order.
  `reindex()` holds it too. `Indexes.add_record`/`delete_record` (and the `_indexed`
  cache) are only called with it held; say so in a comment.
- `query()` and `find_by_field()` skip hits whose file is gone (deleted between the
  search and the read, or a dangling id after a crash). `total` stays the index count;
  note that in the reference.
- Tests: several threads (`concurrent.futures.ThreadPoolExecutor`) saving and changing
  the same objects at once; afterwards the index has the values of the files and there is
  no exception. A test with an id in the index but no file: `query()` returns no `None`.
- CHANGELOG: 2.2.1, "Fixed".

## 2. sjdbl 0.4.0: `Store.transaction()` with a commit log (fixes 3 and 4)

### The commit

All writes of a store go through one method `_commit(writes, deletes)` (`writes`:
qid -> serialized JSON; `deletes`: qids), with the store's lock held:

1. Write every `writes` entry to its temp file (`<uuid>.tmp` in the class directory),
   then `fsync` each temp file (first all writes, then all fsyncs: the kernel can write
   them out together).
2. Write the commit log `<store>/commit.log`: JSON `{"write": [qids], "delete": [qids]}`,
   via a temp file, `fsync`, rename, `fsync` of the store directory. **This is the commit
   point.**
3. Rename each temp file into place; unlink each deleted file (`missing_ok`). `fsync`
   each changed class directory once.
4. Remove `commit.log` and `fsync` the store directory.

Only after a successful commit do objects get their new `__rev__`; on an error before the
commit point they keep (get back) their old one and the temp files are removed.

A single `put(obj)` without a transaction writes one file, which a rename already makes
atomic: it may skip the log (steps 1 and 3 only), as today. Anything with more than one
file, or a delete together with writes, uses the log.

### Recovery, in `Store.__init__`

- If `commit.log` exists: for every qid in `write` whose temp file exists, rename it into
  place; unlink every qid in `delete`; `fsync` the directories; remove the log. Log at
  WARNING which qids were finished.
- Then remove stray `*.tmp` files in the class directories (a transaction that never
  reached its commit point).

### `Store.transaction()`

Replaces `batch()` (one clean switch, no alias). Behaves as `batch()` does now (puts are
checked and serialized at `put()`, written at the end; `get()` sees them, `list()` does
not; nesting: the outermost commits; an exception discards everything and restores the
revisions), plus:

- `delete()` inside a transaction is buffered as well and committed with the rest.
- At the end everything goes through `_commit` (no `os.sync()`).

### Also in 0.4.0

- Remember the revision of every qid read or written (`dict` qid -> rev, filled by
  `get()`, `list()` and the commit; dropped on delete). `_stored_rev` uses it and only
  reads the file for a qid it has not seen. sjdbl is single process, so the dict is the
  truth once filled. (Measure a put before and after; drop this if it gains nothing.)
- Tests for crash safety: make `_commit` raise right after step 1, after step 2 and
  halfway through step 3 (monkeypatch `Path.replace` to raise on the second call), then
  open a new `Store` on the same directory and check: before the commit point nothing
  changed, after it everything did; no `.tmp` files are left.
- CHANGELOG with "Upgrading": `batch()` becomes `transaction()`. CLAUDE.md: update
  "Invariants to keep" (the commit log, recovery, no `os.sync`). README: transactions.

## 3. swindl 3.0.0: `Store.transaction()` over files and index (fixes 5)

### Index changes are recorded before the file commit

`<data>/index/pending.log`: the qids whose index entry may not match the files. Written
(temp file, `fsync`, rename) **before** sjdbl commits, removed after the index committed
those changes. Listing a qid too many is harmless: redoing it from the file gives the same
entry.

`swindl.Store.transaction()`, with swindl's lock held for the whole block:

- `put()` and `delete()` are buffered: in sjdbl's transaction for the files, and in a
  dict qid -> object or "delete" for the index.
- At the end of the outermost block:
  1. add the qids to `pending.log`;
  2. let sjdbl's transaction commit (the files);
  3. apply the index changes (`add_record`, `delete_record`), and commit the changed
     indexes;
  4. take the qids out of `pending.log` (remove the file when it is empty).
- An exception before 2: sjdbl discards the files, the index changes are dropped, the
  qids are taken out of `pending.log` again. Nothing changed.
- Within the block `get()` sees its puts (sjdbl), `query()` and `list()` don't (the
  index), as with `batch()` now.

A `put()` or `delete()` outside a transaction is a transaction of one.

### When the index commits

The apps use both modes: `Commit(immediate=True)` (tests, imports) and
`Commit(immediate=False)` with sil's auto-commit (the servers).

- Immediate: step 3 commits at once, step 4 follows.
- Auto-commit: the qids stay in `pending.log` until the next commit. To know when that
  is, swindl does the auto-commit itself instead of sil: the sil `Index`es are made
  without their own commit task (`commit_timeout=0`), and `Indexes` runs one task that
  commits every changed index and then clears `pending.log`. The interval stays
  `Commit.timeout`. (sil itself does not change.)
- `Commit(timeout=0)` (no commit until shutdown, used by scripts) keeps working:
  `shutdown()` commits and clears `pending.log`.

### Recovery, in `swindl.Store.__init__`

After sjdbl's recovery (which `JsonStore(...)` does) and opening the indexes: if
`pending.log` exists, for each qid `get` it from the files and `add_record` it, or
`delete_record` it when the file is gone; commit; remove the log. Log at WARNING how many
were redone. Nothing else is reindexed: a changed model still only reports
`needs_reindex`.

### Also in 3.0.0

- `batch()` is removed; `transaction()` replaces it. One app uses
  `batch()` (`store.py`, `chat.py`, `news.py`, `notifications.py`): it moves to
  `transaction()` when it upgrades. Note in "Upgrading" that a failing block now writes
  nothing (with `batch()` the files kept the puts).
- Tests: the same crash points as in sjdbl, plus a crash after the file commit and before
  the index commit; a new `Store` on the same directory has the index matching the files.
  An exception in a transaction leaves files and index unchanged. Both commit modes.
- `doc/reference.md`: "Storing" gets transactions; a short "After a crash" section (what
  is finished at startup and what is logged).
- CHANGELOG 3.0.0 with "Upgrading"; requires `sjdbl >= 0.4.0, < 1`. CLAUDE.md: invariants
  (store first, index after; `pending.log` written before the file commit, cleared after
  the index commit; swindl's lock around every change).

## 4. Proving it: crash test, check tool, guarantees

"Crash safe" is a claim; these make it one we can back up.

- **Crash test script** (`tools/crashtest.py` in swindl, not part of the package): a child
  process runs transactions in a loop (puts, deletes, several objects per transaction,
  both commit modes); the parent kills it with `SIGKILL` at a random moment, opens the
  store, and checks: every transaction is in the files completely or not at all, the
  index matches the files, no `.tmp` files. A few thousand rounds before a release of
  sjdbl or swindl that touches the commit path. (The unit tests raise at chosen points;
  this kills at any point.)
- **`swindl-check <data dir> <models module>`**: reports, never repairs:
  - ids in the index without a file, files without an index entry, index values that
    differ from the file;
  - stray `.tmp` files, a leftover `commit.log` or `pending.log` (the app was not
    started since a crash);
  - files that are not valid JSON, references to objects that don't exist.
  Exit code 0 when all is well. The repair stays `actions/reindex` (and a person for
  the files).
- **`doc/guarantees.md`** (swindl, linked from sjdbl's README): what is promised
  (atomic transactions, durable on Linux after the transaction ends, lost updates
  prevented by revisions, the index catches up after a crash) and what not (readers can
  see part of a transaction while it commits; only written objects are revision-checked;
  no unique or reference constraints; macOS `fsync` does not flush the drive cache), the
  limits (one process: no `uvicorn --workers`; `list()` and `reindex()` read every file),
  and how to back up (a filesystem snapshot, or a copy while holding the store's lock; a
  copy taken during a commit is finished when it is opened).

## Not in this plan (deliberately)

- Isolation for readers: `get()` and `query()` take no lock, so during step 3 of a commit
  a reader can see part of a transaction. Fine for our apps; a luxury problem.
- Security items from the review, separately: a "user query" mode in sil (no field syntax
  or raw regexes from a search box, or an allow-list of fields), and creating the store
  directory with mode `0o700`.
