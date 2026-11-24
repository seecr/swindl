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

"""An OAI-PMH 2.0 provider for an Oai repository, as meresco-oai's OaiPmh answered:
the same XML, the same error codes and messages, the same resumption tokens
("m<prefix>|c<stamp>|f<from>|u<until>|s<set>|p"), and x-wait.

Independent of a web framework: the application's route gives the request's arguments
and gets an OaiResponse (status, body):

    provider = OaiProvider(oai, metadata=..., name="Example Repository", ...)

    async def oai_endpoint(request):
        response = await provider.handle(
            list(request.query_params.multi_items()),
            base_url=str(request.url.replace(query="")),
            client=request.headers.get("X-Meresco-Oai-Client-Identifier"),
        )
        return Response(response.body, status_code=response.status,
                        media_type=response.content_type)

x-wait (supports_x_wait=True): a ListRecords or ListIdentifiers with x-wait=True that
finds nothing waits until a change in its prefix (and set) is stored, and then
answers; its last part has a resumption token too, so the harvester goes on from
there. One waiting request per client (the X-Meresco-Oai-Client-Identifier header):
a new request of the same client ends the waiting one with 204 No Content, as does
waiting request max_waiting + 1 (a random one). A change wakes the requests after its
transaction, so the store must find changes at once: Commit(immediate=True) or
Commit(on_search=True)."""

import asyncio
import random
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

from lxml import etree

from .repository import OaiRecord, datestamp

OAI_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xsi:schemaLocation="http://www.openarchives.org/OAI/2.0/ '
    'http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd">'
)
OAI_FOOTER = "</OAI-PMH>"

# http://www.openarchives.org/OAI/openarchivesprotocol.html#ErrorConditions
ERROR_CODES = {
    "badArgument": "The request includes illegal arguments, is missing required "
    "arguments, includes a repeated argument, or values for arguments have an illegal "
    "syntax.",
    "badResumptionToken": "The value of the resumptionToken argument is invalid or "
    "expired.",
    "badVerb": "Value of the verb argument is not a legal OAI-PMH verb, the verb "
    "argument is missing, or the verb argument is repeated.",
    "cannotDisseminateFormat": "The metadata format identified by the value given for "
    "the metadataPrefix argument is not supported by the item or by the repository.",
    "idDoesNotExist": "The value of the identifier argument is unknown or illegal in "
    "this repository.",
    "noRecordsMatch": "The combination of the values of the from, until, set and "
    "metadataPrefix arguments results in an empty list.",
    "noMetadataFormats": "There are no metadata formats available for the specified "
    "item.",
    "noSetHierarchy": "The repository does not support sets.",
}
# the arguments are not echoed for these: they are not valid
_NOT_ECHOED = {"badArgument", "badResumptionToken", "badVerb"}

DEFAULT_BATCH_SIZE = 200
MAX_WAITING = 100
CLIENT_HEADER = "X-Meresco-Oai-Client-Identifier"
_DELETED = ' status="deleted"'

_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SECOND = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


@dataclass
class OaiResponse:
    status: int
    body: bytes
    content_type: str = "text/xml; charset=utf-8"
    error: str = None  # the OAI-PMH error code, if it is an error


class OaiError(Exception):
    def __init__(self, code, message=""):
        super().__init__(message)
        self.code = code
        self.message = message


class _ForcedResume(Exception):
    pass


class OaiProvider:
    """metadata(record, prefix): the metadata of a record (OaiRecord) in prefix, as
    an lxml element or XML text; None leaves <metadata> empty. about(record, prefix):
    XML text for <about> (or None). identifier_prefix: put before the identifiers
    shown (e.g. "oai:example.org:") and taken off those asked for;
    repository_identifier gives Identify its oai-identifier description.
    descriptions: more XML texts for Identify; watermark: XML text after the
    OAI-PMH element's start (a comment, as meresco's oaiWatermark). about may give
    "" (an empty <about>, as meresco) or None (no <about>). delete_in_sets: mark the
    sets a record is deleted in (status="deleted"); default as the Oai."""

    def __init__(
        self,
        oai,
        metadata,
        name,
        admin_email,
        about=None,
        repository_identifier=None,
        identifier_prefix="",
        descriptions=(),
        watermark="",
        batch_size=DEFAULT_BATCH_SIZE,
        supports_x_wait=False,
        max_waiting=MAX_WAITING,
        store=None,
        delete_in_sets=None,
    ):
        self._oai = oai
        self._metadata = metadata
        self._about = about
        self._name = name
        self._admin_email = admin_email
        self._repository_identifier = repository_identifier
        self._identifier_prefix = identifier_prefix
        self._descriptions = list(descriptions)
        self._watermark = watermark
        # setSpecs a record is deleted in get status="deleted" in its header (as
        # meresco's OaiPmh(deleteInSets=...)); default: when the Oai deletes in sets
        self._delete_in_sets = (
            oai.supports_delete_in_sets if delete_in_sets is None else delete_in_sets
        )
        self._batch_size = batch_size
        self.supports_x_wait = supports_x_wait
        self._max_waiting = max_waiting
        self._waiting = {}  # client -> (future, prefix, set)
        self._version = 0  # changes seen, to not miss one between select and wait
        self._loop = None
        if supports_x_wait:
            store = store or oai._store
            if not store.sees_changes_at_once:
                raise ValueError(
                    "x-wait needs a store with Commit(immediate=True) or "
                    "Commit(on_search=True)"
                )
            store.on_transaction(self._changed)

    # --- requests ---

    async def handle(self, arguments, base_url, client=None, now=None):
        """The answer to a request: arguments as (name, value) pairs (repeated names
        allowed: they are an error). Waits with x-wait."""
        args = _as_dict(arguments)
        verb = args.get("verb", [None])
        if verb[0] in ("ListRecords", "ListIdentifiers") and self.supports_x_wait:
            if [v.lower() for v in args.get("x-wait", [])] == ["true"]:
                self._loop = asyncio.get_running_loop()
                try:
                    return await self._wait_and_list(args, base_url, client, now)
                except _ForcedResume as e:
                    return OaiResponse(204, str(e).encode(), "text/plain")
        return self.respond(arguments, base_url, now=now)

    def respond(self, arguments, base_url, now=None):
        """The answer to a request, without waiting (x-wait answers at once)."""
        args = _as_dict(arguments)
        return self._respond(args, base_url, now, wait=False)

    def _respond(self, args, base_url, now, wait):
        response_date = _zulu(now)
        try:
            verb = self._verb(args)
            body = getattr(self, f"_{verb}")(args, base_url, wait)
        except OaiError as e:
            body = self._error(e, args, base_url, response_date)
            return OaiResponse(200, body, error=e.code)
        return OaiResponse(
            200,
            "".join(
                [
                    OAI_HEADER,
                    self._watermark,
                    f"<responseDate>{response_date}</responseDate>",
                    _request(args, base_url),
                    body,
                    OAI_FOOTER,
                ]
            ).encode(),
        )

    async def _wait_and_list(self, args, base_url, client, now):
        client = client or str(uuid.uuid4())
        while True:
            version = self._version
            response = self._respond(args, base_url, now, wait=True)
            # as meresco: also wait for a prefix that is not there yet
            if response.error not in ("noRecordsMatch", "cannotDisseminateFormat"):
                return response
            if self._version != version:
                continue  # a change came in while selecting: select again
            await self._suspend(client, args)

    async def _suspend(self, client, args):
        prefix, set_ = self._list_scope(args)
        if client in self._waiting:
            self._waiting.pop(client)[0].set_exception(
                _ForcedResume(
                    "Aborting suspended request because of new request for the same "
                    f"OaiClient with identifier: {client}."
                )
            )
        elif len(self._waiting) >= self._max_waiting:
            other = random.choice(list(self._waiting))
            self._waiting.pop(other)[0].set_exception(
                _ForcedResume("OAI x-wait connection has been forcefully resumed.")
            )
        future = self._loop.create_future()
        self._waiting[client] = (future, prefix, set_)
        try:
            await future
        finally:
            if self._waiting.get(client, (None,))[0] is future:
                del self._waiting[client]

    def _list_scope(self, args):
        if "resumptionToken" in args:
            token = _token_from(args["resumptionToken"][0])
            return token["m"], token["s"] or None
        return args.get("metadataPrefix", [None])[0], args.get("set", [None])[0]

    def _changed(self, changes):
        """Store.on_transaction: wake the waiting requests the changes are for."""
        scopes = [
            (obj.prefixes, obj.sets)
            for obj in changes.values()
            if isinstance(obj, OaiRecord) and obj.repository == self._oai.repository
        ]
        if scopes and self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._wake, scopes)

    def _wake(self, scopes):
        self._version += 1
        for client, (future, prefix, set_) in list(self._waiting.items()):
            if any(
                prefix in prefixes and (set_ is None or set_ in sets)
                for prefixes, sets in scopes
            ):
                del self._waiting[client]
                if not future.done():
                    future.set_result(None)

    @property
    def waiting(self):
        """The clients with a waiting request."""
        return set(self._waiting)

    # --- the verbs ---

    def _verb(self, args):
        verbs = args.get("verb", [None])
        if verbs[0] in (None, ""):
            raise OaiError("badArgument", 'No "verb" argument found.')
        if len(verbs) > 1:
            raise OaiError("badArgument", 'More than one "verb" argument found.')
        if verbs[0] not in (
            "Identify",
            "ListMetadataFormats",
            "ListSets",
            "GetRecord",
            "ListIdentifiers",
            "ListRecords",
        ):
            raise OaiError("badVerb")
        for name, values in args.items():
            if len(values) > 1:
                raise OaiError("badArgument", f'Argument "{name}" may not be repeated.')
        return verbs[0]

    def _Identify(self, args, base_url, wait):
        if set(args) != {"verb"}:
            illegal = ", ".join(f'"{key}"' for key in sorted(args) if key != "verb")
            raise OaiError("badArgument", f"Argument(s) {illegal} is/are illegal.")
        parts = [
            "<Identify>",
            f"<repositoryName>{escape(self._name)}</repositoryName>",
            f"<baseURL>{escape(base_url)}</baseURL>",
            "<protocolVersion>2.0</protocolVersion>",
            f"<adminEmail>{escape(self._admin_email)}</adminEmail>",
            "<earliestDatestamp>1970-01-01T00:00:00Z</earliestDatestamp>",
            "<deletedRecord>persistent</deletedRecord>",
            "<granularity>YYYY-MM-DDThh:mm:ssZ</granularity>",
        ]
        if self._repository_identifier:
            identifier = escape(self._repository_identifier)
            parts.append(
                "<description>"
                '<oai-identifier xmlns="http://www.openarchives.org/OAI/2.0/'
                'oai-identifier" xsi:schemaLocation="http://www.openarchives.org/OAI/'
                "2.0/oai-identifier http://www.openarchives.org/OAI/2.0/"
                'oai-identifier.xsd">'
                "<scheme>oai</scheme>"
                f"<repositoryIdentifier>{identifier}</repositoryIdentifier>"
                "<delimiter>:</delimiter>"
                f"<sampleIdentifier>oai:{identifier}:5324</sampleIdentifier>"
                "</oai-identifier></description>"
            )
        parts.extend(self._descriptions)
        parts.append("</Identify>")
        return "".join(parts)

    def _ListMetadataFormats(self, args, base_url, wait):
        _only(args, optional={"identifier"})
        formats = self._oai.formats
        if "identifier" in args:
            record = self._record(args["identifier"][0])
            prefixes = record.prefixes
            if not prefixes:
                raise OaiError("noMetadataFormats")
            formats = {p: formats.get(p, {}) for p in sorted(prefixes)}
        parts = ["<ListMetadataFormats>"]
        # sorted as meresco did: on (prefix, schema, namespace)
        for prefix, info in sorted(formats.items()):
            parts.append(
                "<metadataFormat>"
                f"<metadataPrefix>{escape(prefix)}</metadataPrefix>"
                f"<schema>{escape(info.get('schema', ''))}</schema>"
                f"<metadataNamespace>{escape(info.get('namespace', ''))}"
                "</metadataNamespace>"
                "</metadataFormat>"
            )
        parts.append("</ListMetadataFormats>")
        return "".join(parts)

    def _ListSets(self, args, base_url, wait):
        if "resumptionToken" in args:
            if set(args) != {"verb", "resumptionToken"}:
                raise OaiError(
                    "badArgument",
                    '"resumptionToken" argument may only be used exclusively.',
                )
            raise OaiError("badResumptionToken")
        _only(args)
        sets = self._oai.sets
        if not sets:
            raise OaiError("noSetHierarchy")
        parts = ["<ListSets>"]
        for spec, name in sorted(sets.items()):
            parts.append(
                f"<set><setSpec>{escape(spec)}</setSpec>"
                f"<setName>{escape(name)}</setName></set>"
            )
        parts.append("</ListSets>")
        return "".join(parts)

    def _GetRecord(self, args, base_url, wait):
        _only(args, required={"identifier", "metadataPrefix"})
        prefix = args["metadataPrefix"][0]
        if prefix not in self._oai.formats:
            raise OaiError("cannotDisseminateFormat")
        record = self._record(args["identifier"][0])
        if prefix not in record.prefixes:
            raise OaiError("cannotDisseminateFormat")
        return f"<GetRecord>{self._record_xml(record, prefix, None)}</GetRecord>"

    def _ListIdentifiers(self, args, base_url, wait):
        return self._list("ListIdentifiers", args, wait)

    def _ListRecords(self, args, base_url, wait):
        return self._list("ListRecords", args, wait)

    def _list(self, verb, args, wait):
        given = set(args) - {"verb", "x-wait"}
        if "x-wait" in args and not (
            self.supports_x_wait and args["x-wait"][0].lower() == "true"
        ):
            if self.supports_x_wait:
                raise OaiError(
                    "badArgument",
                    "The argument 'x-wait' only supports 'True' as valid value.",
                )
            given.add("x-wait")
        if "resumptionToken" in given:
            if given != {"resumptionToken"}:
                raise OaiError(
                    "badArgument",
                    '"resumptionToken" argument may only be used exclusively.',
                )
            token = _token_from(args["resumptionToken"][0])
            prefix, set_ = token["m"], token["s"] or None
            from_, until = token["f"] or None, token["u"] or None
            continue_after = token["c"]
        else:
            if "metadataPrefix" not in given:
                raise OaiError(
                    "badArgument",
                    'Missing argument(s) "resumptionToken" or "metadataPrefix".',
                )
            if illegal := given - {"metadataPrefix", "from", "until", "set"}:
                names = ", ".join(f'"{name}"' for name in sorted(illegal))
                raise OaiError("badArgument", f"Argument(s) {names} is/are illegal.")
            prefix = args["metadataPrefix"][0]
            set_ = args.get("set", [None])[0]
            from_, until = _from_until(
                args.get("from", [None])[0], args.get("until", [None])[0]
            )
            continue_after = 0
        if prefix not in self._oai.formats:
            raise OaiError("cannotDisseminateFormat")
        records, more = self._oai.select(
            prefix,
            set=set_,
            continue_after=continue_after,
            from_=_stamp(from_),
            until=_stamp(until, end=True),
            size=self._batch_size,
        )
        if not records:
            raise OaiError("noRecordsMatch")
        requested_sets = [set_] if set_ and self._oai.supports_delete_in_sets else None
        parts = [f"<{verb}>"]
        for record in records:
            if verb == "ListRecords":
                parts.append(self._record_xml(record, prefix, requested_sets))
            else:
                parts.append(self._header_xml(record, prefix, requested_sets))
        if more or wait:
            token = (
                f"m{prefix}|c{records[-1].stamp}|f{from_ or ''}|u{until or ''}"
                f"|s{set_ or ''}|p"
            )
            parts.append(f"<resumptionToken>{escape(token)}</resumptionToken>")
        elif "resumptionToken" in args:
            parts.append("<resumptionToken/>")
        parts.append(f"</{verb}>")
        return "".join(parts)

    # --- records ---

    def _record(self, identifier):
        if identifier.startswith(self._identifier_prefix):
            record = self._oai.get(identifier[len(self._identifier_prefix) :])
            if record is not None:
                return record
        raise OaiError("idDoesNotExist")

    def _header_xml(self, record, prefix, requested_sets):
        deleted = record.is_deleted_for(prefix, requested_sets)
        deleted_sets = record.deleted_sets if self._delete_in_sets else ()
        set_specs = "".join(
            f"<setSpec{_DELETED if spec in deleted_sets else ''}>"
            f"{escape(spec)}</setSpec>"
            for spec in sorted(record.sets)
        )
        identifier = escape(self._identifier_prefix + record.identifier)
        return (
            f"<header{_DELETED if deleted else ''}>"
            f"<identifier>{identifier}</identifier>"
            f"<datestamp>{datestamp(record.stamp)}</datestamp>"
            f"{set_specs}</header>"
        )

    def _record_xml(self, record, prefix, requested_sets):
        parts = ["<record>", self._header_xml(record, prefix, requested_sets)]
        if not record.is_deleted_for(prefix, requested_sets):
            parts.append(
                f"<metadata>{_text(self._metadata(record, prefix))}</metadata>"
            )
            if self._about is not None and (
                (about := self._about(record, prefix)) is not None
            ):
                parts.append(f"<about>{_text(about)}</about>")
        parts.append("</record>")
        return "".join(parts)

    def _error(self, error, args, base_url, response_date):
        space = " " if error.message else ""
        message = ERROR_CODES[error.code] + space + escape(error.message)
        echoed = {} if error.code in _NOT_ECHOED else args
        return "".join(
            [
                OAI_HEADER,
                f"<responseDate>{response_date}</responseDate>",
                _request(echoed, base_url),
                f'<error code="{error.code}">{message}</error>',
                OAI_FOOTER,
            ]
        ).encode()


def _as_dict(arguments):
    """{name: [values]} from (name, value) pairs or a dict of lists."""
    if isinstance(arguments, dict):
        return {k: list(v) for k, v in arguments.items()}
    result = {}
    for name, value in arguments:
        result.setdefault(name, []).append(value)
    return result


def _only(args, required=(), optional=()):
    given = set(args) - {"verb"}
    if missing := set(required) - given:
        names = " and ".join(f'"{name}"' for name in sorted(missing))
        raise OaiError("badArgument", f"Missing argument(s) {names}.")
    if illegal := given - set(required) - set(optional):
        names = ", ".join(f'"{name}"' for name in sorted(illegal))
        raise OaiError("badArgument", f"Argument(s) {names} is/are illegal.")


def _request(args, base_url):
    attributes = " ".join(
        f'{escape(name)}="{_attribute(values[0])}"'
        for name, values in sorted(args.items())
    )
    return f"<request {attributes}>{escape(base_url)}</request>"


def _attribute(value):
    return escape(value).replace('"', "&quot;")


def _token_from(text):
    parts = dict((part[0], part[1:]) for part in text.split("|") if part)
    if not {"m", "c", "f", "u", "s"} <= set(parts):
        raise OaiError("badResumptionToken")
    try:
        parts["c"] = int(parts["c"])
    except ValueError:
        raise OaiError("badResumptionToken") from None
    return parts


def _from_until(from_, until):
    """from and until as meresco kept them: a whole second ("...T00:00:00Z" for a
    day's from, "...T23:59:59Z" for a day's until)."""
    try:
        if from_ is not None:
            short_from = bool(_DAY.match(from_))
            from_ = _moment(from_)
        if until is not None:
            short_until = bool(_DAY.match(until))
            until = _moment(until, end=True)
    except ValueError:
        raise OaiError(
            "badArgument", "From and/or until arguments are faulty."
        ) from None
    if from_ is not None and until is not None:
        if short_from != short_until:
            raise OaiError(
                "badArgument", "From and/or until arguments must match in length."
            )
        if from_ > until:
            raise OaiError(
                "badArgument", "From argument must be smaller than until argument."
            )
    return from_, until


def _moment(text, end=False):
    if _DAY.match(text):
        day = datetime.strptime(text, "%Y-%m-%d")
        if end:
            day += timedelta(hours=23, minutes=59, seconds=59)
        return day.strftime("%Y-%m-%dT%H:%M:%SZ")
    if _SECOND.match(text):
        datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")  # a valid moment
        return text
    raise ValueError(text)


def _stamp(moment, end=False):
    """A whole second (text) as a stamp: its first microsecond, or with end its
    last."""
    if not moment:
        return None
    seconds = int(
        datetime.strptime(moment, "%Y-%m-%dT%H:%M:%SZ")
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )
    return (seconds + 1) * 1_000_000 - 1 if end else seconds * 1_000_000


def _text(xml):
    if xml is None:
        return ""
    if isinstance(xml, (str, bytes)):
        return xml.decode() if isinstance(xml, bytes) else xml
    return etree.tostring(xml, encoding="unicode")


def _zulu(now):
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
