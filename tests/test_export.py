from pathlib import Path
import pymupdf as fitz
import pytest
from hilf_print.configuration import Settings
from hilf_print.models import Item
from hilf_print.pdf_writer import MM, export_pdf
from hilf_print.matching import Batch
from hilf_print.pdf_reader import read_pdf
from conftest import label_text, order_text


def test_thermal_dimensions_pair_identity_and_vector_barcodes(matched_batch, tmp_path):
    batch = matched_batch(qty=3)
    target = tmp_path / "output.pdf"
    source_bytes = {s.path: s.path.read_bytes() for s in batch.sources.values()}
    report = export_pdf(batch.pairs(), target, Settings(), batch.original_paths)
    assert (report.pairs, report.pages) == (1, 2)
    with fitz.open(target) as pdf:
        assert all(abs(p.rect.width / MM - 100) < 0.01 and abs(p.rect.height / MM - 150) < 0.01 for p in pdf)
        assert "Pedido: 10001" in pdf[0].get_text()
        assert "PEDIDO #10001" in pdf[1].get_text()
        assert "TOTAL DE PEÇAS: 4" in pdf[1].get_text()
        assert len(pdf[0].get_drawings()) == 35
        assert not pdf[0].get_images()
        assert not pdf[1].get_images()  # picking text stays vectorial
    assert all(p.read_bytes() == data for p, data in source_bytes.items())


def test_original_mode_preserves_document(matched_batch, tmp_path):
    batch = matched_batch()
    target = tmp_path / "original.pdf"
    export_pdf(batch.pairs(), target, Settings(mode="original"), batch.original_paths)
    with fitz.open(target) as out:
        assert "SKU: CALCA-38" in out[1].get_text()
        assert "Quantidade: 1" in out[1].get_text()


def test_pagination_no_cut_and_total(matched_batch, tmp_path):
    batch = matched_batch()
    order = batch.pairs()[0].order
    order.items = [Item(f"PRODUTO {i} " + "MUITO LONGO " * 8, i + 1, "G / PRETO", "A" * 100) for i in range(30)]
    target = tmp_path / "long.pdf"
    export_pdf(batch.pairs(), target, Settings(font_size=16), batch.original_paths)
    with fitz.open(target) as pdf:
        assert len(pdf) > 10
        text = " ".join(p.get_text() for p in pdf)
        for i in range(30):
            assert f"PRODUTO {i} " in text
        assert "TOTAL DE PEÇAS: 465" in text
        for page in list(pdf)[1:]:
            for block in page.get_text("dict")["blocks"]:
                if block["type"] != 0:
                    continue
                for line in block["lines"]:
                    x0,y0,x1,y1 = line["bbox"]
                    assert x0 >= 0 and y0 >= 0 and x1 <= page.rect.width + .1 and y1 <= page.rect.height + .1


def test_no_output_for_missing_items(matched_batch, tmp_path):
    batch = matched_batch()
    batch.pairs()[0].order.items_verified = False
    target = tmp_path / "blocked.pdf"
    with pytest.raises(ValueError, match="revise"):
        export_pdf(batch.pairs(), target, Settings(), batch.original_paths)
    assert not target.exists()
    assert not list(tmp_path.glob(".hilf-*"))


def test_never_overwrite_original(matched_batch):
    batch = matched_batch()
    pair = batch.pairs()[0]
    target = pair.order.source.path
    data = target.read_bytes()
    with pytest.raises(ValueError, match="original"):
        export_pdf(batch.pairs(), target, Settings(), batch.original_paths)
    assert target.read_bytes() == data


def test_mixed_file_export_each_order_own_pages(pdf_factory, tmp_path):
    batch = Batch()
    batch.add(*read_pdf(pdf_factory("mixed.pdf", [order_text("222"), label_text("111"), order_text("111"), label_text("222")], True)))
    target = tmp_path / "output.pdf"
    export_pdf(batch.pairs(), target, Settings(), batch.original_paths)
    with fitz.open(target) as pdf:
        assert len(pdf) == 4
        for i, number in enumerate(["111", "222"]):
            assert f"Pedido: {number}" in pdf[i * 2].get_text()
            assert f"PEDIDO #{number}" in pdf[i * 2 + 1].get_text()
            assert f"Pedido: {'222' if number == '111' else '111'}" not in pdf[i * 2].get_text()


def test_duplicate_reuse_rejected(matched_batch, tmp_path):
    batch = matched_batch()
    with pytest.raises(ValueError, match="mais de um par"):
        export_pdf(batch.pairs() * 2, tmp_path / "bad.pdf", Settings(), batch.original_paths)


def test_reversed_order(matched_batch, tmp_path):
    batch = matched_batch()
    p = tmp_path / "reversed.pdf"
    export_pdf(batch.pairs(), p, Settings(page_order="order_first"), batch.original_paths)
    with fitz.open(p) as pdf:
        assert "ITENS PARA SEPARAÇÃO" in pdf[0].get_text()
        assert "Loggi" in pdf[1].get_text()


def test_failed_export_keeps_existing_destination(matched_batch, tmp_path):
    batch = matched_batch()
    batch.pairs()[0].order.items_verified = False
    target = tmp_path / "existing.pdf"
    target.write_bytes(b"existing output")
    with pytest.raises(ValueError):
        export_pdf(batch.pairs(), target, Settings(), batch.original_paths)
    assert target.read_bytes() == b"existing output"


def test_size_quantity_only_are_larger_and_bold(matched_batch, tmp_path):
    batch = matched_batch()
    target = tmp_path / "emphasis.pdf"
    export_pdf(batch.pairs(), target, Settings(font_size=12, emphasis_size=18), batch.original_paths)
    with fitz.open(target) as pdf:
        spans = [s for b in pdf[1].get_text("dict")["blocks"] if b['type'] == 0 for line in b["lines"] for s in line["spans"]]
        sizes = [s for s in spans if "TAM. / VAR.:" in s["text"] or "QTD.:" in s["text"]]
        assert len(sizes) == 4
        assert all(abs(s["size"] - 18) < .01 and "Bold" in s["font"] for s in sizes)
        products = [s for s in spans if "CALÇA" in s["text"]]
        assert products and all(abs(s["size"] - 12) < .01 for s in products)


def test_existing_output_is_never_overwritten_even_in_new_session(matched_batch, tmp_path):
    batch = matched_batch()
    target = tmp_path / "old-original.pdf"
    target.write_bytes(b"original from a past session")
    with pytest.raises(ValueError, match="novo nome"):
        export_pdf(batch.pairs(), target, Settings(), set())
    assert target.read_bytes() == b"original from a past session"


def test_unsupported_hard_links_use_exclusive_copy(matched_batch, tmp_path, monkeypatch):
    import errno
    from hilf_print import pdf_writer
    def unsupported(*_):
        raise OSError(errno.ENOTSUP, "unsupported")
    monkeypatch.setattr(pdf_writer.os, "link", unsupported)
    batch = matched_batch()
    target = tmp_path / "fat-output.pdf"
    export_pdf(batch.pairs(), target, Settings(), batch.original_paths)
    with fitz.open(target) as pdf:
        assert len(pdf) == 2
