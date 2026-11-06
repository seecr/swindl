## begin license ##
#
# "Swindl"(Seecr Web Index and Database Lib) combines swl, sil and sdbl
#
# Copyright (C) 2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "Swindl"
#
# "Swindl" is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# "Swindl" is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with "Swindl"; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
## end license ##

"""The WebAdapter: from the text of a web form to typed values and back.

Each step prints what happens; run it:

    PYTHONPATH=. python examples/webadapter.py

In an SWL view the form is `async with request.form() as form:` (Starlette's FormData);
here dicts stand in for it. See doc/webadapter.md for the rules.
"""

from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from sjdbl.field import Field

from swindl.store import Base, Commit, Store
from swindl.webadapter import (
    Adapt,
    FieldError,
    FormErrors,
    at_least,
    at_most,
    from_form,
    max_length,
    one_of,
    to_form,
)


def not_on_sunday(value):
    # a check of your own: gets the converted value (never None), raises FieldError
    if value.weekday() == 6:
        raise FieldError("sunday")


class Product(Base):
    FIELDS = [Field.str("title")]


class Order(Base):
    FIELDS = [
        Field.str("customer"),
        Field.str("product"),
        Field.str("status"),
        Field.int("amount"),
        Field.decimal("price"),
        Field.date("deliver_on"),
        Field.bool("paid", default=False),
    ]

    # How fields come from a form. A field without an Adapt is text. An Adapt for a
    # name that is not in FIELDS raises when this class is defined.
    ADAPTATIONS = [
        Adapt.str("customer", checks=[max_length(40)]),
        Adapt.str("status", checks=[one_of(["new", "sent", "done"])]),  # fixed list
        Adapt.int("amount", checks=[at_least(1), at_most(1000)]),
        Adapt.decimal("price", decimals=2),
        Adapt.date("deliver_on", checks=[not_on_sunday]),
        Adapt.bool("paid"),  # a checkbox
    ]


FIELDS = ["customer", "status", "amount", "price", "deliver_on", "paid"]


def show(title, value):
    print(f"\n## {title}\n   {value}")


def try_form(form, fields, **kwargs):
    try:
        return from_form(Order, form, fields, **kwargs)
    except FormErrors as e:
        return {name: (err.code, err.params) for name, err in e.errors.items()}


def main(path):
    store = Store(path, [Product, Order], commit=Commit(immediate=True))
    for title in ["Pat", "Pak"]:
        store.create(Product, dict(title=title))

    # 1. Creating: convert and check first, then create. A wrong value raises
    #    FormErrors before anything is in the store.
    form = dict(customer=" Acme ", status="new", amount="3", price="12.5",
                deliver_on="2026-11-09", paid="on")
    values = from_form(Order, form, FIELDS)
    show("1. create: the form, converted (stripped, typed)", values)
    order = store.create(Order, values)

    # 2. Only the listed fields; and a field that is not sent is left alone, so a form
    #    can save a few fields. customer is sent but not listed: never touched.
    show("2. amount and price listed, only amount sent",
         from_form(Order, dict(amount="5", customer="Evil"), ["amount", "price"]))

    # 3. A checkbox in fields that is not sent is False: an unchecked box is not sent.
    show("3. checkbox listed, not sent", from_form(Order, dict(), ["paid"]))

    # 4. Empty is None for numbers and dates, so they can be cleared; text keeps "".
    form = dict(deliver_on="", price=" ", status="")
    show("4. emptied", from_form(Order, form, ["deliver_on", "price", "status"]))

    # 5. Wrong values: the errors of all fields together, as code and params. The
    #    application translates them: _(MESSAGES[error.code], **error.params).
    form = dict(customer="x" * 41, status="lost", amount="0", price="cheap",
                deliver_on="2026-11-08")
    show("5. errors per field", try_form(form, FIELDS))

    # 6. Choices from the store: build the check in the view with the values of that
    #    moment, and pass the Adapt for this form; it overrides the model's.
    products = {p.title: p.id for p in store.list(Product)}
    adaptations = [Adapt.str("product", checks=[one_of(products.values())])]
    show("6a. a product from the store", try_form(
        dict(product=products["Pat"]), ["product"], adaptations=adaptations))
    show("6b. one that is not", try_form(
        dict(product="Pof"), ["product"], adaptations=adaptations))

    # 7. Adapt.custom: from_web(obj, form) gets the object (None when creating) and the
    #    whole form; to_web(obj, value) gives the value for the form.
    def total_price(obj, form):
        amount = obj.amount if obj else 1
        return Decimal(form.get("unit_price", "0")) * amount

    adaptations = [Adapt.custom("price", total_price, lambda obj, value: str(value))]
    show("7. price from unit_price * the stored amount", from_form(
        Order, dict(unit_price="2.50"), ["price"], obj=order, adaptations=adaptations))

    # 8. to_form: the values for the inputs of the form. None is "", a date is
    #    2026-11-09, a checkbox a bool (for `checked`).
    order.update(deliver_on=None)
    show("8. to_form", to_form(order, FIELDS))

    # 9. After errors, show the form again with what was typed (not what is stored).
    show("9. to_form with form=", to_form(order, FIELDS, form=dict(amount="many")))

    store.disconnect()


if __name__ == "__main__":
    with TemporaryDirectory() as tmp:
        main(Path(tmp))
