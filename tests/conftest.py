from __future__ import annotations
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import pymupdf as fitz
import pytest
from hilf_print.matching import Batch
from hilf_print.pdf_reader import read_pdf


@pytest.fixture
def pdf_factory(tmp_path):
    def create(name: str, texts: list[str], barcode: bool = False) -> Path:
        target = tmp_path / name
        with fitz.open() as pdf:
            for text in texts:
                page = pdf.new_page(width=283.4646, height=425.1969)
                page.insert_text((10, 20), text, fontsize=10)
                if barcode:
                    for i in range(35):
                        x = 15 + i * 5
                        page.draw_rect(fitz.Rect(x, 310, x + (1 if i % 2 else 3), 360), color=None, fill=(0, 0, 0))
            pdf.save(target)
        return target
    return create


def order_text(number="10001", name="Cliente Exemplo", qty=1):
    return f"Pedido de venda #{number}\nCliente: {name}\nProduto: CALÇA RETA CINZA SARJA (CINTO)\nSKU: CALCA-38\nTamanho: 38\nQuantidade: {qty}\nProduto: CALÇA CARPINTEIRO PRETA\nVariação: P / Preto\nQuantidade: 1\nTotal de peças: {qty + 1}"


def label_text(number="10001", name="Cliente Exemplo", carrier="Loggi"):
    return f"{carrier}\nPedido: {number}\nDestinatário: {name}\nRastreio: AA123456789ZZ\nCEP: 66820000"


@pytest.fixture
def matched_batch(pdf_factory):
    def create(number="10001", qty=1, carrier="Loggi"):
        batch = Batch()
        for path in [pdf_factory("x7.pdf", [label_text(number, carrier=carrier)], True), pdf_factory("z99.pdf", [order_text(number, qty=qty)])]:
            batch.add(*read_pdf(path))
        return batch
    return create
