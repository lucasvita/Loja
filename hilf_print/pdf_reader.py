from __future__ import annotations

import hashlib
import re
from pathlib import Path
import pymupdf as fitz
from .classification import identify
from .extraction import extract_items, page_recipient
from .models import Document, Kind, Source

MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_BATCH_BYTES = 512 * 1024 * 1024


class ImportFailure(ValueError):
    pass


def read_pdf(path: Path) -> tuple[Source, list[Document]]:
    path = path.expanduser().resolve()
    if path.suffix.lower() != ".pdf":
        raise ImportFailure("Selecione apenas arquivos PDF.")
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise ImportFailure("PDF excede o limite de 128 MiB por arquivo.")
        source = Source(path, data, hashlib.sha256(data).hexdigest())
        documents: list[Document] = []
        page_texts: dict[str, str] = {}
        sequences: dict[str, tuple[int, int]] = {}
        with fitz.open(stream=data, filetype="pdf") as pdf:
            if pdf.needs_pass:
                raise ImportFailure("PDF protegido por senha; forneça uma cópia desbloqueada.")
            if pdf.page_count == 0:
                raise ImportFailure("PDF sem páginas.")
            for page in pdf:
                try:
                    text = page.get_text(sort=True)
                    kind, order_id, carrier, issues = identify(text)
                    items, verified = [], False
                    if kind == Kind.ORDER:
                        tables = []
                        try:
                            tables = [table.extract() for table in page.find_tables().tables]
                        except Exception:
                            # Text fallback is conservative and never fabricates products.
                            pass
                        items, verified, item_issues = extract_items(text, tables)
                        issues.extend(item_issues)
                    doc = Document(source, (page.number,), kind, order_id, page_recipient(page, text), carrier, items, issues, verified, ambiguous_orders=any(issue.startswith("Mais de um número") for issue in issues))
                    sequence_match = re.search(r"p[aá]gina\s+(\d+)\s*(?:de|/)\s*(\d+)", text, re.I)
                    sequence = (int(sequence_match[1]), int(sequence_match[2])) if sequence_match else None
                    # Repeated IDs alone do not prove continuation: require explicit page numbering.
                    previous = next((d for d in documents if d.kind == Kind.ORDER and kind == Kind.ORDER and d.order_id == order_id and d.pages[-1] == page.number - 1 and page_texts.get(d.id) != text and sequence is not None and sequences.get(d.id) == (sequence[0] - 1, sequence[1]) and 1 < sequence[0] <= sequence[1]), None)
                    if previous:
                        if previous.recipient and doc.recipient:
                            from .classification import normalize
                            if normalize(previous.recipient) != normalize(doc.recipient):
                                documents.append(doc)
                                continue
                        previous.pages += doc.pages
                        previous.items.extend(items)
                        previous.items_verified = previous.items_verified and verified
                        previous.issues.extend(issues)
                        previous.recipient = previous.recipient or doc.recipient
                        sequences[previous.id] = sequence
                    else:
                        documents.append(doc)
                        page_texts[doc.id] = text
                        if sequence and sequence[0] == 1 and sequence[1] > 1:
                            sequences[doc.id] = sequence
                except Exception:
                    documents.append(Document(source, (page.number,), Kind.UNKNOWN, None, issues=["Falha ao analisar esta página; confira o PDF original."]))
        return source, documents
    except ImportFailure:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise ImportFailure("Não foi possível abrir o PDF: arquivo inválido, corrompido ou inacessível.") from exc
