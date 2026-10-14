from __future__ import annotations
import random
import pytest
from hilf_print.classification import identify, normalize
from hilf_print.extraction import extract_items, table_items
from hilf_print.matching import Batch
from hilf_print.models import Kind, Status
from hilf_print.pdf_reader import ImportFailure, read_pdf
from conftest import label_text, order_text


@pytest.mark.parametrize("carrier", ["Loggi", "Correios"])
def test_correct_pair_and_carriers(matched_batch, carrier):
    batch = matched_batch(carrier=carrier)
    row, = batch.rows()
    assert row.status == Status.MATCHED
    assert row.pair.order.order_id == row.pair.label.order_id == "10001"
    assert row.carrier == carrier


def test_random_filenames_and_shuffled_upload(pdf_factory):
    paths = []
    for n in range(100, 160):
        paths += [pdf_factory(f"q{n * 7}.pdf", [order_text(str(n))]), pdf_factory(f"x{n * 9}.pdf", [label_text(str(n))])]
    random.Random(20).shuffle(paths)
    batch = Batch()
    for p in paths:
        batch.add(*read_pdf(p))
    assert len(batch.sources) == 120
    assert len(batch.pairs()) == 60
    assert all(p.order.order_id == p.label.order_id for p in batch.pairs())


def test_duplicate_order_is_blocked(matched_batch, pdf_factory):
    batch = matched_batch()
    batch.add(*read_pdf(pdf_factory("other.pdf", [order_text() + "\nSegunda cópia"])))
    assert batch.rows()[0].status == Status.DUPLICATE
    assert batch.pairs() == []


def test_duplicate_label_is_blocked(matched_batch, pdf_factory):
    batch = matched_batch()
    batch.add(*read_pdf(pdf_factory("other.pdf", [label_text() + "\nOutra etiqueta"])))
    assert batch.rows()[0].status == Status.DUPLICATE
    assert not batch.pairs()


def test_same_bytes_ignored(matched_batch):
    batch = matched_batch()
    source = next(iter(batch.sources.values()))
    assert not batch.add(*read_pdf(source.path))
    assert batch.duplicate_imports == 1
    assert len(batch.pairs()) == 1


@pytest.mark.parametrize("text,status", [(order_text(), Status.NO_LABEL), (label_text(), Status.NO_ORDER), ("CEP: 66820000\nCPF: 12345678900", Status.UNKNOWN)])
def test_unmatched_and_unidentified(pdf_factory, text, status):
    batch = Batch()
    batch.add(*read_pdf(pdf_factory("random.pdf", [text])))
    assert batch.rows()[0].status == status
    assert not batch.pairs()


def test_items_variations_and_quantity(matched_batch):
    doc = matched_batch(qty=3).pairs()[0].order
    assert doc.items_verified
    assert len(doc.items) == 2
    assert doc.items[0].quantity == 3
    assert doc.items[0].variation == "38"
    assert doc.items[1].variation == "P / Preto"
    assert sum(i.quantity for i in doc.items) == 4


def test_multipage_order_explicit_id(pdf_factory):
    p = pdf_factory("multi.pdf", [order_text() + "\nPágina 1 de 2", order_text().replace("CALÇA RETA", "CAMISETA") + "\nPágina 2 de 2"])
    _, docs = read_pdf(p)
    assert len(docs) == 1
    assert docs[0].pages == (0, 1)
    assert len(docs[0].items) == 4


def test_identical_order_pages_are_duplicates(pdf_factory):
    batch = Batch()
    batch.add(*read_pdf(pdf_factory("same.pdf", [order_text(), order_text()])))
    assert len(batch.documents) == 2
    assert batch.rows()[0].status == Status.DUPLICATE


def test_mixed_order_pages_never_join(pdf_factory):
    _, docs = read_pdf(pdf_factory("mixed.pdf", [order_text("111"), label_text("222"), order_text("333"), "Produto sem número"]))
    assert [d.order_id for d in docs] == ["111", "222", "333", None]
    assert [d.pages for d in docs] == [(0,), (1,), (2,), (3,)]


def test_corrupted_file_and_valid_next(pdf_factory, tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a PDF")
    with pytest.raises(ImportFailure):
        read_pdf(bad)
    _, docs = read_pdf(pdf_factory("ok.pdf", [order_text()]))
    assert docs[0].order_id == "10001"


def test_recipient_conflict_manual_confirmation(pdf_factory):
    batch = Batch()
    batch.add(*read_pdf(pdf_factory("order.pdf", [order_text()])))
    batch.add(*read_pdf(pdf_factory("label.pdf", [label_text(name="Outra Pessoa")])))
    row, = batch.rows()
    assert row.status == Status.CONFLICT
    assert not batch.pairs()
    order = next(d for d in row.documents if d.kind == Kind.ORDER)
    label = next(d for d in row.documents if d.kind == Kind.LABEL)
    with pytest.raises(ValueError, match="confirmação"):
        batch.pair_manually(order.id, label.id)
    batch.pair_manually(order.id, label.id, confirmed=True)
    assert batch.rows()[0].status == Status.MANUAL


def test_normalized_names_match(pdf_factory):
    batch = Batch()
    for path in [pdf_factory("a.pdf", [order_text(name="João  DA Silva")]), pdf_factory("b.pdf", [label_text(name="JOAO da-Silva")])]:
        batch.add(*read_pdf(path))
    assert len(batch.pairs()) == 1
    assert normalize("João") == "joao"


def test_mismatched_number_is_never_auto_matched(pdf_factory):
    batch = Batch()
    for path in [pdf_factory("a.pdf", [order_text("111")]), pdf_factory("b.pdf", [label_text("222")])]:
        batch.add(*read_pdf(path))
    assert not batch.pairs()
    order = next(d for d in batch.documents.values() if d.kind == Kind.ORDER)
    label = next(d for d in batch.documents.values() if d.kind == Kind.LABEL)
    with pytest.raises(ValueError):
        batch.pair_manually(order.id, label.id)


def test_clear_all_session_state(matched_batch):
    batch = matched_batch()
    pair = batch.pairs()[0]
    batch.pair_manually(pair.order.id, pair.label.id)
    batch.errors.append("error")
    batch.duplicate_imports = 1
    batch.excluded.add("anything")
    batch.clear()
    assert not any([batch.sources, batch.documents, batch.manual, batch.excluded, batch.errors, batch.original_paths, batch.duplicate_imports, batch.pairs()])


def test_remove_file_and_exclusion(matched_batch):
    batch = matched_batch()
    pair = batch.pairs()[0]
    batch.excluded.add(pair.order.id)
    assert not batch.pairs()
    batch.excluded.clear()
    batch.remove_source(pair.label.source.id)
    assert batch.rows()[0].status == Status.NO_LABEL
    assert pair.label.source.path.exists()


def test_multiple_ids_same_page_and_tracking_not_order():
    assert identify("Loggi\nPedido: 111\nPedido: 222")[0] == Kind.UNKNOWN
    assert identify("Loggi\nCEP: 10001\nAA123456789ZZ")[1] is None
    assert identify("Pedido de venda #10001X")[1] is None


def test_correios_logo_not_in_text():
    kind, number, carrier, _ = identify("Pedido: 10002\nSEDEX\nAB123456789BR\nDESTINATÁRIO\nPessoa")
    assert (kind, number, carrier) == (Kind.LABEL, "10002", "Correios")


def test_loja_integrada_table_name_variation():
    rows = [["Código", "Nome", "Valor unitário", "Qtd.", "Valor total"], ["sku38", "Calça Cinza\nTamanho de calça: 38\nDisponibilidade: Imediata", "R$ 99,00", "2", "R$ 198,00"]]
    items, verified = table_items(rows)
    assert verified
    assert (items[0].name, items[0].variation, items[0].quantity, items[0].sku) == ("Calça Cinza", "38", 2, "sku38")


def test_incomplete_items_and_total_do_not_pass():
    items, ok, _ = extract_items("Produto: Teste\nQuantidade: 1\nProduto: Sem quantidade")
    assert items and not ok
    assert not extract_items(order_text(qty=1).replace("Total de peças: 2", "Total de peças: 5"))[1]
    assert not table_items([["Produto", "Quantidade"], ["Válido", "1"], ["Inválido", "?"]])[1]


def test_adjacent_different_documents_same_number_blocked(pdf_factory):
    batch = Batch()
    batch.add(*read_pdf(pdf_factory("different.pdf", [order_text(), order_text(qty=2)])))
    assert len(batch.documents) == 2
    assert batch.rows()[0].status == Status.DUPLICATE


def test_wrapped_recipient_surname():
    from hilf_print.extraction import recipient
    assert recipient("DESTINATÁRIO: Nome Exemplo Sobrenome Composto\nFinal\nRua Ator Paulo Gustavo, 168\nApto 502") == "Nome Exemplo Sobrenome Composto Final"
    assert recipient("DESTINATÁRIO\n\nPessoa Teste\nRua X, 20") == "Pessoa Teste"


def test_manual_resolution_never_exports_remaining_duplicate_copy(matched_batch, pdf_factory):
    batch = matched_batch()
    original = batch.pairs()[0]
    batch.add(*read_pdf(pdf_factory("second-order.pdf", [order_text() + "\nCópia dois"])))
    batch.add(*read_pdf(pdf_factory("second-label.pdf", [label_text() + "\nCópia dois"])))
    assert not batch.pairs()
    batch.pair_manually(original.order.id, original.label.id)
    assert len(batch.pairs()) == 1
    assert sum(r.status == Status.DUPLICATE for r in batch.rows()) == 1


def test_shirt_size_alias_from_real_layout():
    items, ok = table_items([["Código", "Nome", "Qtd."], ["XYZ-g", "Calça cargo jeans clara\nTamanho de camisa/camiseta: G\nDisponibilidade: Imediata", "1"]])
    assert ok and items[0].name == "Calça cargo jeans clara" and items[0].variation == "G"


def test_children_size_alias():
    items, ok = table_items([["Nome", "Qtd."], ["Calça Infantil\nTamanho juvenil-infantil: 14\nDisponibilidade: Imediata", "2"]])
    assert ok and items[0].name == "Calça Infantil" and items[0].variation == "14"


def test_ambiguous_page_cannot_be_manually_relabelled_into_a_pair(pdf_factory):
    batch = Batch()
    batch.add(*read_pdf(pdf_factory("ambiguous.pdf", ["Pedido de venda #111\nPedido de venda #222"])))
    batch.add(*read_pdf(pdf_factory("label.pdf", [label_text("111")])))
    doc = next(d for d in batch.documents.values() if d.kind == Kind.UNKNOWN)
    label = next(d for d in batch.documents.values() if d.kind == Kind.LABEL)
    assert doc.ambiguous_orders
    doc.kind, doc.order_id = Kind.ORDER, "111"
    with pytest.raises(ValueError, match="vários pedidos"):
        batch.pair_manually(doc.id, label.id, confirmed=True)
