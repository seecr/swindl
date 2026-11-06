# The WebAdapter

An HTML form only sends text; a model has dates, numbers, decimals and booleans.
`swindl.webadapter` converts and checks what comes in from a form, and gives the values for
the inputs of a form. It is declared once per model and used in the views that show and
save forms.

```python
from swindl.webadapter import (
    Adapt, FieldError, FormErrors, at_least, at_most, from_form, max_length, one_of, to_form,
)
```

## Principles

- **Fields define the model; the WebAdapter guards the boundary.** sjdbl's `Field`s say how
  a value is stored. The WebAdapter converts and checks what comes in from a web form. The
  two stay separate: no web or check knowledge in `Field`, and no conversions derived from
  `Field`s; the `ADAPTATIONS` say it.
- **`update` and `create` trust their input.** `Base.update` does no checks; an invalid
  value there is a programmer error. Checking happens in the WebAdapter, before.
- **Forms only.** The WebAdapter handles form input and the values for form inputs.
  Showing values (dates in a list, names of states) is done with template filters.
- **Simple data.** Results and errors are plain dicts.

## Declaring, in the model

```python
from sjdbl.field import Field
from swindl.store import Base

class Person(Base):
    FIELDS = [
        Field.str("name"),
        Field.date("dob"),
        Field.int("age"),
        Field.decimal("amount"),
        Field.bool("active", default=False),
        Field.str("state"),
    ]
    ADAPTATIONS = [
        Adapt.str("name", checks=[max_length(100)]),
        Adapt.date("dob"),
        Adapt.int("age", checks=[at_least(0)]),
        Adapt.decimal("amount", decimals=2),
        Adapt.bool("active"),
        Adapt.custom("state", from_web=state_from_web, to_web=state_to_web),
    ]
```

Every non-text field used in a form is declared; a field without an `Adapt` is text
(`Adapt.str` without checks). swindl's `Base` checks when the class is defined that every
`Adapt` names a field in `FIELDS` and that no field is adapted twice: a typo such as
`Adapt.date("dbo")` raises a `TypeError` at import.

| | From the form | To the form |
|---|---|---|
| `Adapt.str(name)` | the text | the text |
| `Adapt.int(name)` | `int` | `"42"` |
| `Adapt.decimal(name, decimals=2)` | `Decimal`, rounded to `decimals` | `"12.50"` |
| `Adapt.date(name)` | `date` from `2026-11-03` | `"2026-11-03"` |
| `Adapt.bool(name)` | a checkbox: sent is `True`, not sent is `False` | a bool, for `checked` |
| `Adapt.custom(name, from_web, to_web)` | `from_web(obj, form)` | `to_web(obj, value)` |

`str`, `int`, `decimal` and `date` take `checks=[...]`, and optional `from_web(text)` and
`to_web(value)` to replace the conversion, e.g. a decimal with a comma:

```python
Adapt.decimal("amount", from_web=lambda text: Decimal(text.replace(",", ".")))
```

**`Adapt.custom`** is for anything the standard types don't cover: a value made of other
fields, a multi-select (`form.getlist(name)`), a reference. `from_web(obj, form)` gets the
object (`None` when creating) and the whole form, and returns the value, which is used as
is (`None` included); `to_web(obj, value)` returns the value for the form. Both can raise
`FieldError`. A custom field in `fields` is always set: its `from_web` decides, also when
nothing of it was sent (an empty multi-select is not sent at all).

## The rules, per field, in this order

1. **Not in `fields`:** never touched (not in the result), whatever the form sends.
2. **Not sent** (not in the form): left alone (not in the result), so a form can save one
   field, or a few. Except a checkbox (`Adapt.bool`) in `fields`: not sent is `False`,
   because an unchecked box is not sent.
3. **Sent:** whitespace is stripped. Empty becomes `None`, so dates and numbers can be
   cleared; text keeps `""`.
4. **Converted;** a value that doesn't convert is a `FieldError` `invalid_int`,
   `invalid_decimal` or `invalid_date`. Then the checks run, only on values that are not
   `None`.
5. **`Adapt.custom`** gets the form itself and decides; its result is used as is.

## Checks

| | Error |
|---|---|
| `at_least(n)` | `too_small`, `{"min": n}` |
| `at_most(n)` | `too_large`, `{"max": n}` |
| `max_length(n)` | `too_long`, `{"max": n}` |
| `one_of(values)` | `not_allowed` |

A check is a function of the converted value that raises `FieldError(code, **params)`:

```python
def not_on_sunday(value):
    if value.weekday() == 6:
        raise FieldError("sunday")

Adapt.date("deliver_on", checks=[not_on_sunday])
```

**Choices.** `one_of(values)` takes the values when it is called. For a fixed list, call
it in `ADAPTATIONS`. For a list that changes (objects from the store), call it in the
view and pass the Adapt for that form only; it overrides the model's:

```python
products = [p.id for p in store.list(Product)]
values = from_form(Order, form, ["product"], obj=order,
                   adaptations=[Adapt.str("product", checks=[one_of(products)])])
```

The `<select>` gets its options from the same list.

## `from_form` and `to_form`

`from_form(model, form, fields, obj=None, adaptations=None)` returns the values of
`fields` as a dict, for `obj.update(**values)` or `store.create(Model, values)`. `model`
is the class: its `ADAPTATIONS` are used, and `adaptations` adds or overrides per form.
`obj` is passed to `Adapt.custom`. It collects the errors of all fields and raises
`FormErrors`; nothing is returned partially.

`to_form(obj, fields, form=None, adaptations=None)` returns the values for the form
inputs, as text: `None` becomes `""`, a date `2026-11-03`, a decimal with its decimals; a
checkbox gives a bool. With `form=` (showing a form again after errors) it gives what was
typed instead of the stored value, for the fields that were sent; a checkbox then is
whether it was sent. For a new object: `to_form(Person(), fields)`.

`form` is anything with `get` and `__contains__` (and `getlist` for a custom multi-select),
such as Starlette's `FormData` or a dict.

## Errors and translation

`FieldError(code, **params)` has `.code` and `.params`; `FormErrors` has `.errors`, a dict
field name → `FieldError`. swindl has no messages: the application translates the codes,
e.g. with `swl.i18n`, and keeps the texts in its own catalog:

```python
from swl.i18n import N_

ERRORS = {
    "invalid_date": N_("Not a date"),
    "too_long": N_("At most %(max)d characters"),
    ...
}
```

```jinja
{% if errors.dob %}
    <div class="error">{{ _(ERRORS[errors.dob.code], **errors.dob.params) }}</div>
{% endif %}
```

## A complete view

```python
FIELDS = ["name", "dob", "age", "active"]

async def person_save(request, swl, store, **kwargs):
    async with request.form() as form:
        person = store.get(form["qid"], assert_type=Person)
        try:
            values = from_form(Person, form, FIELDS, obj=person)
        except FormErrors as e:
            html = swl.template("person/form.j2").render(
                person=person, values=to_form(person, FIELDS, form=form), errors=e.errors
            )
            return swl.success().hydrate("person-form", html)
    person.update(**values)
    store.put(person)
    return swl.success().toast(_("Saved"))
```

```jinja
<input name="name" value="{{ values.name }}">
<input type="date" name="dob" value="{{ values.dob }}">
<input type="checkbox" name="active" {% if values.active %}checked{% endif %}>
```

Creating converts before creating, so a wrong value never leaves an object in the store:

```python
values = from_form(Person, form, FIELDS)
person = store.create(Person, values)
```

## Showing values

`to_form` is for form inputs only: `2026-11-03` is what `<input type="date">` needs, not
what a person reading a list expects. To show values, use the objects themselves with
SWL's template filters in the visitor's language: `{{ person.dob|format_date }}`,
`format_number`, and the application's own filters for e.g. the names of states.

## Why not a library

Considered in November 2026: WTForms, Pydantic and marshmallow. WTForms is made for HTML
forms, but assumes the whole form is sent: a missing field is empty, which breaks saving
per field. Pydantic and marshmallow know "not sent" but nothing of HTML (empty fields,
checkboxes), and Pydantic's messages are not translated. All of them declare the fields a
second time and add a dependency. The WebAdapter is small and does exactly these rules.
