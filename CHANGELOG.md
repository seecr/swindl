# Changelog

## 2.0.0 (2026-11-06)

A new WebAdapter: a form saves only what it sends, empty dates and numbers can be
cleared, and wrong values give an error per field instead of a crash. See
`doc/webadapter.md`. Needs sjdbl 0.3.0.

### Breaking changes

- `swindl.webadapter` is rewritten; its API is new (see "Upgrading from 1.x").
- `swindl.store.Base` is swindl's own subclass of sjdbl's `Base`, with `INDEX = []` and
  `ADAPTATIONS = []`. sjdbl 0.3.0 no longer has `INDEX`: a model built on sjdbl's `Base`
  directly gets no index any more.
- Raised at import, when the model class is defined: an `Adapt` for a name that is not a
  field, a field adapted twice (swindl), and a field name used twice or clashing with an
  attribute of `Base` such as `id`, `qid` or `update` (sjdbl 0.3.0).

### Added

- `from_form(model, form, fields, obj=None, adaptations=None)`: the converted and checked
  values of a form, for `update` or `create`. Not sent is left alone (a checkbox is
  `False`), empty is `None` (text: `""`), all errors in one `FormErrors`.
- `to_form(obj, fields, form=None, adaptations=None)`: the values for the inputs of a
  form, or with `form=` what was typed, to show a form again after errors.
- Checks `at_least`, `at_most`, `max_length` and `one_of`; `FieldError(code, **params)`
  for checks of your own.
- `Adapt.custom(name, from_web(obj, form), to_web(obj, value))`.
- `doc/reference.md`, `examples/` and this changelog.

### Upgrading from 1.x

Pin `swindl >= 1.2, < 2` until an application is converted; an application that pins swindl
without an upper bound should get `< 2` first.

- Import `Base` from `swindl.store`, not from `sjdbl.base`, for every model that is indexed
  or has `ADAPTATIONS`.
- `WebAdapter.adapt(obj, form, fields)` becomes `from_form(type(obj), form, fields,
  obj=obj)`.
- The wrapper `WebAdapter(obj)` is gone: use `to_form(obj, fields)` for form inputs, and
  template filters (`format_date`, `format_number`) on the object to show values.
- `Adapt.method(name, from_web, to_web)` becomes `Adapt.custom(name, from_web, to_web)`;
  `from_web` now gets `(obj, form)` and `to_web` `(obj, value)`.
- Not sent is left alone, empty is `None`, and wrong values raise `FormErrors`: a view that
  saves a form catches `FormErrors` and shows the form again with
  `to_form(obj, fields, form=form)` and the errors. A workaround that only passes the
  fields that were sent is no longer needed.
- Error messages are the application's: translate `error.code` with `error.params`.
- An `Adapt` that names no field, and a field name that clashes with `Base`, now raise at
  import: fix the name.
