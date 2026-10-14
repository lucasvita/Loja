from __future__ import annotations

import re
import unicodedata
from .models import Kind


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(re.sub(r"[^a-z0-9]+", " ", "".join(c for c in value if not unicodedata.combining(c))).split())


def identify(text: str) -> tuple[Kind, str | None, str, list[str]]:
    # Explicit context is required. Never infer an order from a bare numeric token.
    ids = set(re.findall(r"\bpedido(?:\s+de\s+venda)?\s*(?:n[º°o.]?\s*)?[:#\-]?\s*(\d{1,12})(?![\dA-Za-z])", text, re.I))
    normalized = normalize(text)
    carrier = "Loggi" if re.search(r"\bloggi\b", normalized) else "Correios" if re.search(r"\bcorreios\b", normalized) else ""
    if not carrier and re.search(r"\b[A-Z]{2}\d{9}BR\b", text) and re.search(r"\b(?:SEDEX|PAC)\b", text, re.I) and "destinatario" in normalized:
        carrier = "Correios"
    if len(ids) != 1:
        reason = "Mais de um número de pedido na mesma página; separe o PDF antes de importar." if ids else "Número do pedido não encontrado com contexto confiável."
        return Kind.UNKNOWN, None, carrier, [reason]
    order_id = next(iter(ids))
    is_order = bool(re.search(r"pedido\s+de\s+venda", text, re.I))
    if is_order and carrier and re.search(r"\betiqueta\b", normalized):
        return Kind.UNKNOWN, order_id, carrier, ["Página contém sinais de pedido e etiqueta; conferir manualmente."]
    if is_order:
        return Kind.ORDER, order_id, "", []
    if carrier:
        return Kind.LABEL, order_id, carrier, []
    return Kind.UNKNOWN, order_id, "", ["Tipo de documento não reconhecido; número isolado não define o tipo."]
