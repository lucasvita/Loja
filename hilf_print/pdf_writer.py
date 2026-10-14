from __future__ import annotations

import os
import errno
import shutil
import tempfile
from pathlib import Path
from dataclasses import dataclass
import pymupdf as fitz
from .configuration import Settings
from .models import Pair, Kind
from .validation import divergent

MM = 72 / 25.4


@dataclass
class ExportReport:
    pairs: int
    pages: int
    warnings: list[str]


def ordered_pairs(pairs: list[Pair], settings: Settings) -> list[Pair]:
    def key(pair: Pair) -> tuple:
        number = pair.order.order_id or ""
        numeric = (0, int(number)) if number.isdigit() else (1, number)
        return (pair.label.carrier, numeric) if settings.sort_by == "carrier" else (numeric, pair.label.carrier)
    return sorted(pairs, key=key)


def export_warnings(pairs: list[Pair], settings: Settings) -> list[str]:
    warnings = []
    for pair in pairs:
        with fitz.open(stream=pair.label.source.data, filetype="pdf") as pdf:
            for page_no in pair.label.pages:
                rect = pdf[page_no].rect
                scale = min((settings.width_mm - 2 * settings.label_margin_mm) * MM / rect.width, (settings.height_mm - 2 * settings.label_margin_mm) * MM / rect.height)
                if scale < 0.75:
                    warnings.append(f"Pedido #{pair.order.order_id}: etiqueta será reduzida a {scale:.0%}. Confira a leitura do código de barras; recorte a etiqueta no PDF de origem ou ajuste o formato.")
    if settings.mode == "original":
        warnings.append("Documento original será ajustado proporcionalmente; textos de páginas A4 podem ficar pequenos em 100 × 150 mm.")
    return warnings


def _original(output: fitz.Document, document, settings: Settings) -> None:
    with fitz.open(stream=document.source.data, filetype="pdf") as source:
        for index in document.pages:
            page = output.new_page(width=settings.width_mm * MM, height=settings.height_mm * MM)
            margin = (settings.label_margin_mm if document.kind == Kind.LABEL else settings.margin_mm) * MM
            page.show_pdf_page(page.rect + (margin, margin, -margin, -margin), source, index, keep_proportion=True)


def _wrap(text: str, width: float, font: fitz.Font, size: float) -> list[str]:
    # Character-level fallback guarantees even long SKUs cannot cross the margin.
    result, current = [], ""
    for word in text.replace("\n", " ").split():
        candidate = f"{current} {word}".strip()
        if font.text_length(candidate, fontsize=size) <= width:
            current = candidate
            continue
        if current:
            result.append(current)
            current = ""
        fragment = ""
        for char in word:
            if fragment and font.text_length(fragment + char, fontsize=size) > width:
                result.append(fragment)
                fragment = ""
            fragment += char
        current = fragment
    if current:
        result.append(current)
    return result or [""]


def _picking(output: fitz.Document, pair: Pair, settings: Settings) -> None:
    doc = pair.order
    if not doc.items or not doc.items_verified:
        raise ValueError(f"Pedido #{doc.order_id}: revise e confirme os produtos, ou selecione o modo Documento original.")
    font = fitz.Font("helv")
    bold_font = fitz.Font("hebo")
    margin = settings.margin_mm * MM
    width, height = settings.width_mm * MM, settings.height_mm * MM
    usable = width - 2 * margin
    size = settings.font_size
    line_height = size * 1.4
    page = None
    y = 0.0
    page_number = 0

    def new_page() -> None:
        nonlocal page, y, page_number
        page_number += 1
        page = output.new_page(width=width, height=height)
        page.insert_font(fontname="HilfUnicode", fontbuffer=font.buffer)
        page.insert_font(fontname="HilfBold", fontbuffer=bold_font.buffer)
        y = margin + (size + 4)
        for line in _wrap(f"PEDIDO #{doc.order_id or '?'}", usable, font, size + 4):
            page.insert_text((margin, y), line, fontsize=size + 4, fontname="HilfUnicode")
            y += (size + 4) * 1.4
        # Even exceptionally long client names are paginated instead of clipped.
        page.insert_text((margin, height - margin), f"Lista de separação · {page_number}", fontsize=8, fontname="HilfUnicode")

    def write(text: str, font_size: float = size, space: float = 0, emphasis: bool = False) -> None:
        nonlocal y
        use_bold = emphasis and all(bold_font.has_glyph(ord(c)) for c in text)
        chosen_font = bold_font if use_bold else font
        font_name = "HilfBold" if use_bold else "HilfUnicode"
        if not all(chosen_font.has_glyph(ord(c)) for c in text):
            chosen_font = fitz.Font("cjk")
            font_name = "HilfFallback"
        for line in _wrap(text, usable, chosen_font, font_size):
            if y + font_size * 0.4 > height - margin - 18:
                new_page()
            if font_name == "HilfFallback":
                page.insert_font(fontname=font_name, fontbuffer=chosen_font.buffer)
            page.insert_text((margin, y), line, fontsize=font_size, fontname=font_name)
            y += font_size * 1.4
        y += space

    new_page()
    write(f"CLIENTE: {doc.recipient or 'Não extraído — conferir documento'}", space=5)
    write("ITENS PARA SEPARAÇÃO", space=5)
    for i, item in enumerate(doc.items, 1):
        if y + line_height * 3 > height - margin - 18:
            new_page()
        write(f"{i}. {item.name.upper()}", size, space=2)
        write(f"TAM. / VAR.: {item.variation or 'Não informada — conferir'}", settings.emphasis_size, emphasis=True)
        write(f"QTD.: {item.quantity}", settings.emphasis_size, emphasis=True)
        if item.sku:
            write(f"SKU: {item.sku}", max(9, size - 1))
        y += 7
    write(f"TOTAL DE PEÇAS: {sum(item.quantity for item in doc.items)}", size + 2)


def export_pdf(pairs: list[Pair], target: Path, settings: Settings, original_paths: set[Path]) -> ExportReport:
    settings.validate()
    if not pairs:
        raise ValueError("Nenhum pedido com pareamento confirmado.")
    target = target.expanduser().resolve()
    if target.suffix.lower() != ".pdf":
        raise ValueError("O arquivo de saída deve ter extensão .pdf.")
    for original in original_paths:
        if target == original.resolve() or (target.exists() and original.exists() and target.samefile(original)):
            raise ValueError("O PDF de saída não pode sobrescrever um arquivo original importado.")
    if target.exists():
        raise ValueError("Escolha um novo nome: o Hilf Print não substitui PDFs existentes.")
    for pair in pairs:
        if pair.order.ambiguous_orders or pair.label.ambiguous_orders:
            raise ValueError("Página com vários pedidos não pode ser exportada como um único pedido.")
        if pair.order.kind != Kind.ORDER or pair.label.kind != Kind.LABEL:
            raise ValueError("Par contém documentos de tipos inválidos.")
        differences = divergent(pair.order, pair.label)
        if not pair.manual and any("diferentes" in reason.lower() for reason in differences):
            raise ValueError("Par conflitante sem confirmação manual.")
    ids = [d.id for p in pairs for d in (p.order, p.label)]
    if len(ids) != len(set(ids)):
        raise ValueError("Um documento não pode ser exportado em mais de um par.")
    numbers = [p.order.order_id for p in pairs]
    if len(numbers) != len(set(numbers)):
        raise ValueError("Mais de um par para o mesmo número de pedido.")
    warnings = export_warnings(pairs, settings)
    temporary = None
    try:
        with fitz.open() as output:
            for pair in ordered_pairs(pairs, settings):
                def label() -> None:
                    _original(output, pair.label, settings)
                def order() -> None:
                    _original(output, pair.order, settings) if settings.mode == "original" else _picking(output, pair, settings)
                first, second = (label, order) if settings.page_order == "label_first" else (order, label)
                first()
                second()
            pages = output.page_count
            # Save atomically only after all pages succeed. Failed exports leave no partial PDF.
            fd, temporary = tempfile.mkstemp(prefix=".hilf-", suffix=".pdf", dir=target.parent)
            os.close(fd)
            output.subset_fonts()
            output.save(temporary, garbage=4, deflate=True)
        try:
            os.link(temporary, target)  # Atomic publication without overwriting any existing file.
        except FileExistsError as exc:
            raise ValueError("O destino já existe; escolha um novo nome.") from exc
        except OSError as exc:
            if exc.errno not in {errno.EPERM, errno.EXDEV, errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS}:
                raise
            # FAT/exFAT do not support hard links. Exclusive creation still protects originals.
            created = False
            try:
                with target.open("xb") as dest, open(temporary, "rb") as src:
                    created = True
                    shutil.copyfileobj(src, dest)
                    dest.flush()
                    os.fsync(dest.fileno())
            except Exception:
                if created:
                    target.unlink(missing_ok=True)
                raise
        Path(temporary).unlink()
        temporary = None
        return ExportReport(len(pairs), pages, warnings)
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
