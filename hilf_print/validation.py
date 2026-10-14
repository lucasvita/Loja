from __future__ import annotations

from .classification import normalize
from .models import Document


def divergent(order: Document, label: Document) -> list[str]:
    reasons = []
    if order.order_id != label.order_id or not order.order_id:
        reasons.append("Números dos pedidos diferentes ou ausentes.")
    if order.recipient and label.recipient and normalize(order.recipient) != normalize(label.recipient):
        reasons.append("Destinatários diferentes.")
    if not order.recipient or not label.recipient:
        reasons.append("Nome do destinatário ausente em um dos documentos.")
    return reasons


def declaration_missing() -> list[str]:
    # A picking list is never represented as an official postal declaration.
    return ["Modo de declaração formal indisponível: remetente/destinatário completos, CPF/CNPJ, valores, assinatura e requisitos postais não são validados por este aplicativo."]
