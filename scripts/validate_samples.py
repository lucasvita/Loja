"""Offline real-PDF validation. Reads exclusively explicit command-line paths.

No input PDFs, recipient names or addresses are copied into the report.
"""
from __future__ import annotations
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymupdf as fitz
import numpy as np
import zxingcpp
from hilf_print.classification import normalize
from hilf_print.configuration import Settings
from hilf_print.matching import Batch
from hilf_print.models import Kind, Status
from hilf_print.pdf_reader import read_pdf
from hilf_print.pdf_writer import MM, export_pdf, ordered_pairs


def decode(page, dpi: int = 203) -> set[tuple[str, str]]:
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
    pixels = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    return {(str(result.format), result.text) for result in zxingcpp.read_barcodes(pixels)}


def load(paths: list[Path]) -> Batch:
    batch = Batch()
    for path in paths:
        batch.add(*read_pdf(path))
    return batch


def independent_items(batch: Batch) -> int:
    count = 0
    for doc in batch.documents.values():
        if doc.kind != Kind.ORDER:
            continue
        assert doc.items_verified, f"Itens não confirmados: pedido #{doc.order_id}"
        expected = []
        subtotal = Decimal(0)
        with fitz.open(stream=doc.source.data, filetype="pdf") as pdf:
            for number in doc.pages:
                text = pdf[number].get_text(sort=True)
                # A separate text-based oracle checks table output against original
                # price/quantity columns, without calling our table parser.
                entries = re.findall(r"^(.*?)R\$\s*([\d.,]+)\s+(\d+)\s+R\$\s*([\d.,]+)\s*$", text, re.M)
                for title, unit, quantity, total in entries:
                    expected.append((" ".join(title.strip().split()), int(quantity)))
                    unit_value = Decimal(unit.replace(".", "").replace(",", "."))
                    total_value = Decimal(total.replace(".", "").replace(",", "."))
                    assert unit_value * int(quantity) == total_value, f"Valores de produto divergentes: #{doc.order_id}"
                    subtotal += total_value
                sm = re.search(r"Subtotal:\s*R\$\s*([\d.,]+)", text)
                if sm and len(doc.pages) == 1:
                    assert subtotal == Decimal(sm[1].replace(".", "").replace(",", ".")), f"Subtotal divergente: #{doc.order_id}"
        assert expected and len(expected) == len(doc.items), f"Contagem de produtos divergente: #{doc.order_id}"
        assert [quantity for _, quantity in expected] == [item.quantity for item in doc.items], f"Quantidades divergentes: #{doc.order_id}"
        for (title, _), item in zip(expected, doc.items):
            parts = title.split(" ", 1)
            assert len(parts) == 2 and parts[0] == item.sku, f"SKU divergente: #{doc.order_id}"
            assert normalize(parts[1]) == normalize(item.name), f"Nome de produto divergente: #{doc.order_id}"
        count += len(doc.items)
    return count


def validate_export(batch: Batch, target: Path, mode: str) -> dict:
    settings = Settings(mode=mode)
    pairs = ordered_pairs(batch.pairs(), settings)
    report = export_pdf(pairs, target, settings, batch.original_paths)
    checked_barcodes = 0
    checked_labels = 0
    additional_300dpi_failures = []
    canonical_203dpi_failures = []
    tracking_300dpi_failures = []
    index = 0
    with fitz.open(target) as output:
        for pair in pairs:
            with fitz.open(stream=pair.label.source.data, filetype="pdf") as source:
                for original_page in pair.label.pages:
                    page = output[index]
                    text = page.get_text()
                    assert re.findall(r"\bPedido:\s*(\d+)\b", text, re.I) == [pair.label.order_id]
                    original_codes = decode(source[original_page], 600)
                    exported_codes = decode(page, 600)
                    assert original_codes, f"Código de barras original não decodificado: #{pair.order.order_id}"
                    assert exported_codes == original_codes, f"Código de barras divergente: #{pair.order.order_id}"
                    source_images = {image["digest"] for image in source[original_page].get_image_info(hashes=True)}
                    output_images = {image["digest"] for image in page.get_image_info(hashes=True)}
                    assert output_images == source_images, f"Imagem original alterada: #{pair.order.order_id}"
                    canonical_codes = original_codes
                    if decode(page, 203) != canonical_codes:
                        canonical_203dpi_failures.append(pair.order.order_id)
                    if decode(source[original_page], 300) != decode(page, 300):
                        additional_300dpi_failures.append(pair.order.order_id)
                    tracking_codes = set(re.findall(r"\b[A-Z]{2}\d{9}(?:BR|ZZ)\b", text))
                    for dpi in (203,):
                        read_values = {value for _, value in decode(page, dpi)}
                        assert tracking_codes and tracking_codes <= read_values, f"Rastreio não lido a {dpi} dpi: #{pair.order.order_id}"
                    if not tracking_codes <= {value for _, value in decode(page, 300)}:
                        tracking_300dpi_failures.append(pair.order.order_id)
                    checked_barcodes += len(original_codes)
                    checked_labels += 1
                    index += 1
            if mode == "original":
                for original_page in pair.order.pages:
                    assert f"Pedido de venda #{pair.order.order_id}" in output[index].get_text()
                    index += 1
            else:
                picking_text = ""
                while index < len(output) and f"PEDIDO #{pair.order.order_id}" in output[index].get_text():
                    page = output[index]
                    picking_text += page.get_text() + "\n"
                    for b in page.get_text("dict")["blocks"]:
                        if b["type"] != 0:
                            continue
                        for line in b["lines"]:
                            x0,y0,x1,y1 = line["bbox"]
                            assert x0 >= 0 and y0 >= 0 and x1 <= page.rect.width + .1 and y1 <= page.rect.height + .1, f"Texto cortado: #{pair.order.order_id}"
                            for span in line["spans"]:
                                if "TAM. / VAR.:" in span["text"] or "QTD.:" in span["text"]:
                                    assert abs(span["size"] - settings.emphasis_size) < .01
                                    assert "Bold" in span["font"]
                    index += 1
                assert f"TOTAL DE PEÇAS: {sum(i.quantity for i in pair.order.items)}" in picking_text
                normalized = normalize(picking_text)
                for item in pair.order.items:
                    assert normalize(item.name) in normalized, f"Produto ausente: #{pair.order.order_id}"
                    if item.variation:
                        assert normalize(item.variation) in normalized
            assert all(abs(output[p].rect.width / MM - 100) < .01 and abs(output[p].rect.height / MM - 150) < .01 for p in range(index))
        assert index == len(output), "Página sem associação no PDF final"
    return {"mode": mode, "pairs": report.pairs, "pages": report.pages, "labels_checked": checked_labels, "barcodes_decoded_and_equal": checked_barcodes, "barcode_validation_dpi": 600, "tracking_also_verified_dpi": [203], "additional_300dpi_decoder_mismatches": additional_300dpi_failures, "600dpi_reference_vs_203dpi_mismatches": canonical_203dpi_failures, "tracking_300dpi_not_decoded": tracking_300dpi_failures, "original_image_digests_equal": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, nargs="+", required=True, help="Arquivos originais explicitamente selecionados")
    parser.add_argument("--combined", type=Path, help="PDF já organizado, testado separadamente e junto para duplicidades")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    paths = args.inputs + ([args.combined] if args.combined else [])
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    batch = load(args.inputs)
    report = {"selected_files": len(paths), "original_files": len(args.inputs), "original_statuses": dict(Counter(r.status.value for r in batch.rows())), "products_checked_against_price_quantity_columns": independent_items(batch), "pending": [{"order": r.order_id, "status": r.status.value} for r in batch.rows() if r.pair is None], "exports": []}
    for mode in ["picking", "original"]:
        report["exports"].append(validate_export(batch, args.output_dir / f"Hilf-Print-{mode}.pdf", mode))
    if args.combined:
        combined = load([args.combined])
        report["combined_statuses"] = dict(Counter(r.status.value for r in combined.rows()))
        report["combined_products_checked"] = independent_items(combined)
        original_pairs = {p.order.order_id for p in batch.pairs()}
        assert {p.order.order_id for p in combined.pairs()} == original_pairs
        mixed = load(paths)
        duplicate_orders = {r.order_id for r in mixed.rows() if r.status == Status.DUPLICATE}
        assert duplicate_orders == original_pairs
        assert not mixed.pairs(), "Duplicidades não podem ser exportadas automaticamente"
        report["mixed_statuses"] = dict(Counter(r.status.value for r in mixed.rows()))
        report["mixed_export_blocked"] = True
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p,digest in before.items())
    report["all_originals_unchanged"] = True
    (args.output_dir / "real-validation.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
