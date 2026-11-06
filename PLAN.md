# Plan: WebAdapter 2 (swindl 2.0.0, sjdbl 0.3.0)

Agreed design for rewriting `swindl/webadapter.py`, plus the model changes it needs in
sjdbl and swindl. `doc/webadapter.md` holds the earlier notes (what goes wrong now); this
plan replaces its "What it needs" section.

## Before starting

- In both `swindl` and `sjdbl`: check for uncommitted changes and unpushed commits, then
  `git pull`. If anything is off, stop and ask.
- Work on a branch `webadapter-2` in swindl and `model-checks` in sjdbl.
- Commit messages start with `JJ: `. Run `flake8` and `pytest` before any push.

## Principles

- **Fields define the model; the WebAdapter guards the boundary.** `Field`s (sjdbl) say how
  a value is stored. The WebAdapter (swindl) converts and checks what comes in from a web
  form. The two stay separate: no web or check knowledge in `Field`, and no conversions
  derived from `Field`s.
- **`update` and `create` trust their input.** `Base.update` does no checks; an invalid
  value there is a programmer error. Checking happens in the WebAdapter.
- **Forms only.** The WebAdapter handles form input and the values for form inputs. Showing
  values (dates in a list, state names) is done by template filters, not by the WebAdapter.
- **Simple data.** Results and errors are plain dicts.

## 1. sjdbl: Base checks its fields (release 0.3.0)

- Remove `INDEX = []` from `sjdbl.base.Base`: sjdbl never uses it; it moves to swindl.
- Add `__init_subclass__` to `Base` that raises at class definition when:
  - two fields in `FIELDS` have the same name;
  - a field name clashes with an attribute of `Base` (`id`, `qid`, `qrid`, `type_name`,
    `update`, `delete`, `archive`, `deletable`, `mark_archived`, `create`, `is_archived`,
    `index_values`, `to_storage`, `from_storage`, ... take them from `dir(Base)`) or with a
    `META` name. Such a field is silently hidden today, because attribute access goes
    through `__getattr__`, which only runs when normal lookup fails.
- Do NOT merge inherited `FIELDS` automatically: models write `Base.FIELDS + [...]` (or
  `Parent.FIELDS + [...]`), and merging would then count fields twice.
- Tests in `base_test.py` for each check. Update `CHANGELOG.md` and `README.md`.
- A search of the existing apps found no clashing field names, so this breaks nothing.

## 2. swindl: its own Base

- `swindl/store/__init__.py` exports `Base` from sjdbl today. Replace that with a swindl
  `Base(sjdbl.base.Base)` with `INDEX = []` and `ADAPTATIONS = []`, so apps keep importing
  `from swindl.store import Base`.
- Its `__init_subclass__` checks that every `Adapt` in `ADAPTATIONS` names a field in
  `FIELDS` (a typo like `Adapt.date("dbo")` is silently ignored today) and that no name is
  adapted twice.
- `Indexes.__init__` and `Store.reindex` use `hasattr(model, "INDEX")`. Since sjdbl's Base
  had `INDEX = []`, that was always true; keep the behaviour the same (models of swindl's
  Base have `INDEX`), do not change which models get an index in this release.
- Raise the sjdbl requirement in `pyproject.toml` to `>= 0.3.0, < 1`.

## 3. swindl: the new WebAdapter

Rewrite `swindl/webadapter.py`. Everything in the current module goes, including the
wrapper `WebAdapter(obj)` with `__getattr__` and `original()`, `as_is`,
`from_web_method`, `to_web_method` and `Adapt.method`.

### Declaring, in the model

```python
ADAPTATIONS = [
    Adapt.date("dob"),
    Adapt.int("age", checks=[at_least(0)]),
    Adapt.str("name", checks=[max_length(100)]),
    Adapt.decimal("amount", decimals=2),
    Adapt.bool("active"),
    Adapt.custom("state", from_web=..., to_web=...),
]
```

- Every non-text field used in a form is declared; an undeclared field is text
  (`Adapt.str` without checks).
- `Adapt`: a name, `convert(text) -> value`, `to_web(value) -> text`, `checks`, and
  whether it is a checkbox. Constructors: `str`, `int`, `decimal`, `date`, `bool`,
  `custom`. Each takes optional `from_web`/`to_web` to override the conversion.
- `Adapt.custom(name, from_web, to_web, checks=None)`: `from_web(obj, form)` gets the
  object (None when creating) and the whole form, and returns the value;
  `to_web(obj, value)` returns the text. This is the hook for anything the standard
  types do not cover (other fields, multi-selects via `form.getlist`, references).
- Checks: `at_least(n)`, `at_most(n)`, `max_length(n)`, `one_of(values)`. A check takes the
  converted value and raises `FieldError(code, **params)` (e.g. `too_long`,
  `{"max": 100}`). Checks only run on values that are not None.

### Rules, per field, in this order

1. Not in `fields`: never touched (not in the result).
2. Not sent (not in the form): left alone (not in the result). Exception: a checkbox
   (`Adapt.bool`) that is in `fields` but not sent is `False`, because an unchecked box is
   not sent.
3. Sent: strip whitespace. Empty becomes `None`, except `str`, which keeps `""`.
4. Otherwise convert; a conversion error becomes `FieldError("invalid_<type>")`
   (`invalid_int`, `invalid_decimal`, `invalid_date`). Then run the checks.
5. `Adapt.custom` gets the form itself and decides; its result is used as is (None
   included). It can raise `FieldError` too.

### Functions

Module-level functions in `swindl.webadapter`, no state:

- `from_form(model, form, fields, obj=None, adaptations=None) -> dict`
  - `model` is the class (its `ADAPTATIONS` are used); `adaptations` adds or overrides
    per form; `obj` is passed to `Adapt.custom`.
  - Returns the values for `obj.update(**values)` or `Model.create(store, **values)`.
  - Collects the errors of all fields and raises `FormErrors` with
    `errors = {name: FieldError}`. Nothing is returned partially.
- `to_form(obj, fields, form=None, adaptations=None) -> dict`
  - The values for form inputs, as text: `None` becomes `""`, a date `2026-11-03`, a
    decimal with its decimals. A checkbox gives a bool (for `checked`).
  - With `form=` (re-showing a form after errors) it gives what was typed instead of the
    stored value; a checkbox then is `name in form`.
- `FieldError(code, **params)` with `.code` and `.params`; `FormErrors(errors)` with
  `.errors`. Messages are translated by the app (e.g. `swl.i18n`):
  `{{ _(errors.dob.code, **errors.dob.params) }}`.

Typical view:

```python
fields = ["name", "dob", "country"]
try:
    person.update(**from_form(Person, form, fields, obj=person))
except FormErrors as e:
    return render("person_form", values=to_form(person, fields, form=form), errors=e.errors)
```

`form` is anything with `get`, `__contains__` (and `getlist` for custom multi-selects),
such as Starlette's `FormData` or a dict.

### Tests

Rewrite `swindl/webadapter_test.py` around the rules. At least the cases from the table
in `doc/webadapter.md`:

- only some fields sent: the others are not in the result (no `'None'` text, no `False`
  for a checkbox that is not in `fields`);
- empty date and empty number become `None` (can be cleared);
- missing number is left alone, empty number is `None` (no `TypeError`/`ValueError`);
- wrong values give `FieldError` per field, all collected in one `FormErrors`;
- checks (`at_least`, `at_most`, `max_length`, `one_of`) with their codes and params;
- checkbox in `fields` but not sent is `False`;
- `Adapt.custom` gets obj and form; works with `obj=None`;
- per-form `adaptations` override the model's;
- `to_form`: `None` is `""`, dates, decimals, checkbox bool, and with `form=` the typed
  values;
- swindl Base: an `Adapt` for a field that does not exist raises at class definition.

## 4. Documentation

- Rewrite `doc/webadapter.md` from notes into documentation: purpose, principles, declaring,
  the rules, `from_form`/`to_form`, errors and translation, a full view example, and
  showing values with template filters instead of the old wrapper. Use generic names in
  examples (`Person`, `Order`), no names of the projects it is used in.
- Add `CHANGELOG.md` to swindl (it has none yet) with 2.0.0, including an
  "Upgrading from 1.x" section:
  - `WebAdapter.adapt(obj, form, fields)` -> `from_form(type(obj), form, fields, obj=obj)`;
  - `WebAdapter(obj)` wrapper is gone: use `to_form` for form inputs and template filters
    for showing values;
  - `Adapt.method(name, from_web, to_web)` -> `Adapt.custom` (now gets obj and form);
  - not sent is left alone, empty is `None`, bad values raise `FormErrors`: views that save
    a form should catch `FormErrors` and show the form again with `to_form(..., form=form)`;
  - a workaround that only passes the fields that were sent is no longer needed;
  - `Adapt` names that do not match a field, and field names that clash with `Base`,
    now raise at import.
- Add a short `README.md` if the build needs it (`pyproject.toml` refers to it).

## 5. Release

- sjdbl 0.3.0, then swindl 2.0.0 (breaking: WebAdapter API). Tag as `x.y.z`.
- Apps pin `swindl >= 1.x, < 2` and keep working on 1.x until they upgrade; no maintenance
  branch for 1.x unless an urgent fix is needed.
- Apps to convert later (not part of this plan): those using `swindl.webadapter`; an app
  that pins swindl without an upper bound should get `< 2` first.
