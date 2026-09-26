from __future__ import annotations

from dataclasses import dataclass, field
from xml.etree.ElementTree import ParseError

from carnopy.sources import evidence
from carnopy.sources.errors import SourceImportError
from carnopy.sources.evidence import EvidenceElement
from carnopy.sources.files import Checkpoint, checkpoint


@dataclass
class _Frame:
    name: str
    attributes: tuple[tuple[str, str], ...]
    children: list[EvidenceElement] = field(default_factory=list)
    text: list[str] = field(default_factory=list)
    text_bytes: int = 0


class _EvidenceTarget:
    def __init__(self, cancel: Checkpoint | None) -> None:
        self.cancel = cancel
        self.stack: list[_Frame] = []
        self.root: EvidenceElement | None = None
        self.nodes = 0
        self.records = 0

    def start(self, tag: str, attributes: dict[str, str]) -> None:
        checkpoint(self.cancel)
        prefix = "{" + evidence.THERMOML_NAMESPACE + "}"
        if not tag.startswith(prefix):
            raise SourceImportError("unsupported_namespace", "expected the ThermoML namespace")
        name = tag[len(prefix) :]
        if len(name.encode("utf-8")) > evidence.MAX_SCALAR_BYTES:
            raise SourceImportError("scalar_limit", "XML name is too long")
        if not self.stack and name != "DataReport":
            raise SourceImportError("unsupported_root", "expected ThermoML DataReport")
        self.nodes += 1
        if self.nodes > evidence.MAX_NODES:
            raise SourceImportError("node_limit", "too many evidence elements")
        if len(self.stack) >= evidence.MAX_DEPTH:
            raise SourceImportError("depth_limit", "XML nesting is too deep")
        if name == "PropertyValue":
            self.records += 1
            if self.records > evidence.MAX_PROPERTY_VALUES:
                raise SourceImportError("record_limit", "too many property values")
        for key, value in attributes.items():
            if (
                max(len(key.encode("utf-8")), len(value.encode("utf-8")))
                > evidence.MAX_SCALAR_BYTES
            ):
                raise SourceImportError("scalar_limit", "XML attribute is too long")
        self.stack.append(_Frame(name, tuple(attributes.items())))

    def data(self, value: str) -> None:
        checkpoint(self.cancel)
        if not self.stack:
            return
        frame = self.stack[-1]
        frame.text_bytes += len(value.encode("utf-8"))
        if frame.text_bytes > evidence.MAX_SCALAR_BYTES:
            raise SourceImportError("scalar_limit", "XML text is too long")
        frame.text.append(value)

    def end(self, tag: str) -> None:
        frame = self.stack.pop()
        text = "".join(frame.text)
        if frame.children and text.strip():
            raise SourceImportError("ambiguous_structure", "mixed XML content is unsupported")
        node = EvidenceElement(
            frame.name,
            None if frame.children else text,
            tuple(frame.children),
            frame.attributes,
        )
        if self.stack:
            self.stack[-1].children.append(node)
        else:
            self.root = node

    def close(self) -> EvidenceElement:
        if self.root is None:
            raise SourceImportError("unsupported_root", "missing DataReport")
        return self.root


def read_xml(data: bytes, *, cancel: Checkpoint | None = None) -> EvidenceElement:
    from defusedxml.common import DefusedXmlException
    from defusedxml.ElementTree import DefusedXMLParser

    target = _EvidenceTarget(cancel)
    parser = DefusedXMLParser(
        target=target,
        forbid_dtd=True,
        forbid_entities=True,
        forbid_external=True,
    )
    try:
        for offset in range(0, len(data), 64 * 1024):
            checkpoint(cancel)
            parser.feed(data[offset : offset + 64 * 1024])
        parser.close()
    except DefusedXmlException as exc:
        raise SourceImportError("unsafe_xml", str(exc)) from exc
    except (ParseError, ValueError) as exc:
        raise SourceImportError("malformed_xml", str(exc)) from exc
    return target.close()
