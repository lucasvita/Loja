from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from .models import Document, Kind, Pair, Row, Source, Status
from .pdf_reader import MAX_BATCH_BYTES
from .validation import divergent


class Batch:
    def __init__(self) -> None:
        self.sources: dict[str, Source] = {}
        self.documents: dict[str, Document] = {}
        self.manual: list[Pair] = []
        self.excluded: set[str] = set()
        self.original_paths: set[Path] = set()
        self.errors: list[str] = []
        self.duplicate_imports = 0

    def add(self, source: Source, documents: list[Document]) -> bool:
        self.original_paths.add(source.path)
        if any(s.digest == source.digest for s in self.sources.values()):
            self.duplicate_imports += 1
            return False
        if sum(len(s.data) for s in self.sources.values()) + len(source.data) > MAX_BATCH_BYTES:
            raise ValueError("Lote excede 512 MiB. Divida os arquivos em lotes menores.")
        self.sources[source.id] = source
        self.documents.update({d.id: d for d in documents})
        return True

    def remove_source(self, source_id: str) -> None:
        ids = {d.id for d in self.documents.values() if d.source.id == source_id}
        self.manual = [p for p in self.manual if p.order.id not in ids and p.label.id not in ids]
        self.excluded.difference_update(ids)
        for doc_id in ids:
            del self.documents[doc_id]
        self.sources.pop(source_id, None)

    def pair_manually(self, order_id: str, label_id: str, confirmed: bool = False) -> None:
        order, label = self.documents[order_id], self.documents[label_id]
        if order.ambiguous_orders or label.ambiguous_orders:
            raise ValueError("Página com vários pedidos: separe o PDF antes de parear.")
        if order.id == label.id or order.kind != Kind.ORDER or label.kind != Kind.LABEL:
            raise ValueError("Selecione um documento de pedido e uma etiqueta distintos e reconhecidos.")
        if order.id in self.excluded or label.id in self.excluded:
            raise ValueError("Reinclua os documentos antes de parear.")
        if divergent(order, label) and not confirmed:
            raise ValueError("Dados divergentes ou incompletos: confirmação explícita necessária.")
        self.manual = [p for p in self.manual if p.order.id not in {order.id, label.id} and p.label.id not in {order.id, label.id} and p.order.order_id != order.order_id and p.label.order_id != label.order_id]
        self.manual.append(Pair(order, label, True))

    def clear(self) -> None:
        self.__init__()

    def rows(self) -> list[Row]:
        rows: list[Row] = []
        used: set[str] = set()
        for pair in self.manual:
            used.update((pair.order.id, pair.label.id))
            rows.append(Row(pair.order.order_id, [pair.order, pair.label], Status.MANUAL, pair, "; ".join(divergent(pair.order, pair.label))))
        grouped: dict[str, list[Document]] = defaultdict(list)
        for doc in self.documents.values():
            if doc.id in used:
                continue
            if doc.id in self.excluded:
                rows.append(Row(doc.order_id, [doc], Status.EXCLUDED))
            elif doc.kind == Kind.UNKNOWN or not doc.order_id:
                rows.append(Row(doc.order_id, [doc], Status.UNKNOWN, detail="; ".join(doc.issues)))
            else:
                grouped[doc.order_id].append(doc)
        reserved = {d.order_id for p in self.manual for d in (p.order, p.label)}
        for order_id, docs in grouped.items():
            orders = [d for d in docs if d.kind == Kind.ORDER]
            labels = [d for d in docs if d.kind == Kind.LABEL]
            if order_id in reserved:
                rows.append(Row(order_id, docs, Status.DUPLICATE, detail="Cópias remanescentes de um pedido já pareado manualmente; não serão exportadas."))
            elif len(orders) > 1 or len(labels) > 1:
                rows.append(Row(order_id, docs, Status.DUPLICATE, detail="Escolha manualmente o par correto; nenhuma cópia é escolhida automaticamente."))
            elif not orders:
                rows.append(Row(order_id, docs, Status.NO_ORDER))
            elif not labels:
                rows.append(Row(order_id, docs, Status.NO_LABEL))
            elif divergent(orders[0], labels[0]) and orders[0].recipient and labels[0].recipient:
                rows.append(Row(order_id, docs, Status.CONFLICT, detail="Destinatários divergentes; confirmação manual obrigatória."))
            else:
                pair = Pair(orders[0], labels[0])
                rows.append(Row(order_id, docs, Status.MATCHED, pair, "Nome ausente: pareamento pelo número explícito do pedido." if not orders[0].recipient or not labels[0].recipient else ""))
        return rows

    def pairs(self) -> list[Pair]:
        return [row.pair for row in self.rows() if row.pair is not None]
