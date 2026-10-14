from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from uuid import uuid4


class Kind(StrEnum):
    ORDER = "pedido"
    LABEL = "etiqueta"
    UNKNOWN = "não identificado"


class Status(StrEnum):
    MATCHED = "Pareado"
    MANUAL = "Pareado manualmente"
    NO_ORDER = "Etiqueta sem documento"
    NO_LABEL = "Documento sem etiqueta"
    UNKNOWN = "Não identificado"
    DUPLICATE = "Duplicidade"
    CONFLICT = "Conflito entre destinatários"
    EXCLUDED = "Excluído"


@dataclass(frozen=True)
class Item:
    name: str
    quantity: int
    variation: str = ""
    sku: str = ""


@dataclass
class Source:
    path: Path
    data: bytes = field(repr=False)
    digest: str = ""
    id: str = field(default_factory=lambda: uuid4().hex)


@dataclass
class Document:
    source: Source
    pages: tuple[int, ...]
    kind: Kind
    order_id: str | None
    recipient: str = ""
    carrier: str = ""
    items: list[Item] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    items_verified: bool = False
    ambiguous_orders: bool = False
    id: str = field(default_factory=lambda: uuid4().hex)

    @property
    def description(self) -> str:
        pages = ", ".join(str(p + 1) for p in self.pages)
        return f"{self.source.path.name} · páginas {pages} · {self.kind} · #{self.order_id or '?'}"


@dataclass
class Pair:
    order: Document
    label: Document
    manual: bool = False


@dataclass
class Row:
    order_id: str | None
    documents: list[Document]
    status: Status
    pair: Pair | None = None
    detail: str = ""

    @property
    def recipient(self) -> str:
        return next((d.recipient for d in self.documents if d.recipient), "")

    @property
    def carrier(self) -> str:
        return next((d.carrier for d in self.documents if d.carrier), "")
