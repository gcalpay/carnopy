from __future__ import annotations

import json
from dataclasses import dataclass

from carnopy.sources import evidence
from carnopy.sources.errors import SourceImportError
from carnopy.sources.evidence import EvidenceElement
from carnopy.sources.files import Checkpoint, checkpoint


class _NumericText(str):
    """Keep JSON numeric lexemes distinct from strings while decoding metadata."""


@dataclass
class _Container:
    opening: str
    property_values: bool = False
    expecting_item: bool = True


def _string_end(text: str, start: int, cancel: Checkpoint | None) -> int:
    position = start + 1
    # Six source characters can encode one decoded character as \\uXXXX.
    maximum = 6 * evidence.MAX_SCALAR_BYTES + 2
    while position < len(text):
        if position % (64 * 1024) == 0:
            checkpoint(cancel)
        if position - start > maximum:
            raise SourceImportError("scalar_limit", "JSON string is too long")
        if text[position] == '"':
            return position + 1
        position += 2 if text[position] == "\\" else 1
    raise SourceImportError("malformed_json", "unterminated JSON string")


def _check_limits(text: str, cancel: Checkpoint | None) -> None:
    """Check resources before the standard decoder allocates containers.

    This lexical pass does not accept JSON syntax: json.loads remains its
    authority. It understands strings so braces and keys inside text cannot
    disguise nesting or property-value counts.
    """
    stack: list[_Container] = []
    pending_key = ""
    last_string = ""
    position = nodes = records = 0
    while position < len(text):
        checkpoint(cancel)
        char = text[position]
        if char.isspace():
            position += 1
            continue
        if char == ":":
            pending_key = last_string
            position += 1
            continue
        if char == ",":
            pending_key = ""
            if stack:
                stack[-1].expecting_item = True
            position += 1
            continue
        if char in "}]":
            if not stack or stack.pop().opening != ("{" if char == "}" else "["):
                raise SourceImportError("malformed_json", "unbalanced JSON containers")
            pending_key = ""
            position += 1
            continue
        if stack and stack[-1].property_values and stack[-1].expecting_item:
            records += 1
            stack[-1].expecting_item = False
        if pending_key == "PropertyValue" and char != "[":
            records += 1
        if records > evidence.MAX_PROPERTY_VALUES:
            raise SourceImportError("record_limit", "too many property values")
        nodes += 1
        if nodes > evidence.MAX_NODES:
            raise SourceImportError("node_limit", "too many JSON evidence tokens")
        if char in "{[":
            stack.append(_Container(char, char == "[" and pending_key == "PropertyValue"))
            if len(stack) > evidence.MAX_DEPTH:
                raise SourceImportError("depth_limit", "JSON nesting is too deep")
            pending_key = ""
            position += 1
        elif char == '"':
            end = _string_end(text, position, cancel)
            value = json.loads(text[position:end])
            if len(value.encode("utf-8")) > evidence.MAX_SCALAR_BYTES:
                raise SourceImportError("scalar_limit", "JSON string is too long")
            last_string = value
            pending_key = ""
            position = end
        else:
            end = position
            while end < len(text) and text[end] not in ",]} \t\r\n":
                end += 1
                if end - position > evidence.MAX_SCALAR_BYTES:
                    raise SourceImportError("scalar_limit", "JSON scalar is too long")
            position = end
            pending_key = ""


def read_json(data: bytes, *, cancel: Checkpoint | None = None) -> EvidenceElement:
    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        checkpoint(cancel)
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise SourceImportError("duplicate_json_key", f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> object:
        raise SourceImportError("malformed_json", f"nonstandard JSON constant {value}")

    try:
        text = data.decode("utf-8-sig")
        _check_limits(text, cancel)
        value = json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_int=_NumericText,
            parse_float=_NumericText,
            parse_constant=reject_constant,
        )
        if not isinstance(value, dict) or "tml_elements" not in value:
            raise SourceImportError("unsupported_root", "expected the NIST ThermoML JSON object")
        return _element("DataReport", value, cancel=cancel, root=True)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SourceImportError("malformed_json", str(exc)) from exc


def _element(
    name: str,
    value: object,
    *,
    cancel: Checkpoint | None,
    root: bool = False,
) -> EvidenceElement:
    checkpoint(cancel)
    if not isinstance(value, dict):
        if isinstance(value, list):
            raise SourceImportError("ambiguous_structure", "nested JSON lists are not ThermoML")
        if value is None:
            return EvidenceElement(name)
        return EvidenceElement(name, str(value))
    order = value.get("tml_elements")
    if not isinstance(order, list) or not all(type(key) is str for key in order):
        raise SourceImportError("ambiguous_structure", f"missing/invalid tml_elements in {name}")
    if len(order) != len(set(order)) or any(key not in value for key in order):
        raise SourceImportError("ambiguous_structure", f"ambiguous tml_elements in {name}")
    metadata = {"tml_elements", "THERMOML_MD5_CHECKSUM"} if root else {"tml_elements"}
    if set(order) != set(value) - metadata:
        raise SourceImportError("ambiguous_structure", f"tml_elements omits evidence in {name}")
    children: list[EvidenceElement] = []
    for key in order:
        item = value[key]
        entries = item if isinstance(item, list) else [item]
        for entry in entries:
            children.append(_element(key, entry, cancel=cancel))
    # The archive checksum is provenance, not the SHA-256 of either input file.
    if root and "THERMOML_MD5_CHECKSUM" in value:
        children.append(
            _element("THERMOML_MD5_CHECKSUM", value["THERMOML_MD5_CHECKSUM"], cancel=cancel)
        )
    return EvidenceElement(name, children=tuple(children))
