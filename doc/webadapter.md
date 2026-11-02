# The WebAdapter: notes for later

Nothing of this is changed yet. Notes from November 2026 on `swindl/webadapter.py`: the
idea is useful, the implementation needs work. To be thought over and worked on later.

## What it is for

An HTML form only knows text; an object in the store has types (`date`, `Decimal`, `int`,
`bool`). The WebAdapter translates both ways, declared once per field (`ADAPTATIONS` on
the model, or extra ones per form):

- `WebAdapter.adapt(obj, form, fields)`: the named fields from the form, converted, as a
  dict for `obj.update(**values)`. Only the listed fields: a form cannot set anything else.
  A field that is not in the form stays out, so it keeps its value (saving per field).
- `WebAdapter(obj)`: a wrapper for templates; reading an attribute gives its web form
  (a date as `2026-11-03`), `original(name)` the stored value.

It is in swindl rather than in SWL because it belongs with the models: swindl is the
storage side of an app (sjdbl's objects with sil's index), as SWL is the web side. The
model classes are built on `Base` and its `Field`s (in sjdbl), so a model knows its fields
and their types. That could go further: derive the adaptations from `FIELDS` (a
`Field.date` gets the date conversion by itself), and declare only the exceptions.

## What goes wrong now

Tried with an object with a text field, a date, a number and a checkbox:

| The form sends | Comes out | The problem |
|---|---|---|
| only `name` | `country: 'None'`, `active: False` | A text field that is not sent becomes the text `"None"`; a checkbox that is not sent becomes `False`. Both overwrite what was not sent: saving per field breaks. |
| `dob` empty | `{}` | Empty becomes `None` and is then left out: a date can never be cleared. |
| `age` missing | `TypeError` | `int(None)`: a number (or decimal) that is not sent crashes. |
| `age` empty | `ValueError` | `int("")`: an empty number crashes too. |
| for a template, `country` is `None` | `'None'` | An input without a value shows the word "None". |

And `Adapt.method` gives the conversion only the field's own value, not the object and the
form, so it cannot use other fields or what is stored.

## What it needs

1. **Not sent means: leave it alone**, for every type. Checkboxes need the form to say
   which ones it has (an unchecked checkbox is not sent at all).
2. **Empty means `None`** for dates and numbers, so they can be cleared; `None` goes to the
   form as `""`.
3. **Errors per field**: a wrong value raises an error that names the field, with a message
   that can be chosen and translated, instead of a bare `ValueError`. Room for checks
   (lengths, ranges, values from a fixed list) next to the conversion.
4. **`Adapt.method`** gets the object and the form, as intended.
5. **Creating**: convert before creating, so a wrong value does not leave an empty object
   in the store (`adapt` on the class, `create(store, **values)`).

## Form values and showing values are two different things

`2026-11-03` is what `<input type="date" value="...">` needs. A person reading a list
expects "3 November 2026", in their own language. The wrapper does the first everywhere,
also where the second is meant. Better:

- `to_web` only for the values of form fields;
- showing values with template filters that use the visitor's language (dates, numbers,
  money; SWL's `swl.i18n`, Babel);
- then lists can work with the objects themselves, without a wrapper.

If the wrapper stays (for lists), it has to behave like the object where it matters:
`==` and `in` compare the object it wraps (now `obj == other` is never true), `None`
becomes `""`, and properties and methods are converted the same way as plain attributes
(now only plain attributes are). `isinstance` and calculating with values (`obj.dob.year`,
sorting) do not work on it: a reason to keep it out of anything but forms.
