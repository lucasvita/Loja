from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from .configuration import Settings
from .models import Document, Item, Kind


class PreviewDialog(QDialog):
    def __init__(self, document: Document, parent=None):
        super().__init__(parent)
        self.setWindowTitle(document.description)
        self.resize(800, 850)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Visualização local do PDF original. Confira número, destinatário e produtos."))
        self.buffer = QBuffer(self)
        self.buffer.setData(QByteArray(document.source.data))
        self.buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.pdf = QPdfDocument(self)
        self.pdf.load(self.buffer)
        self.view = QPdfView(self)
        self.view.setDocument(self.pdf)
        self.view.setZoomMode(QPdfView.ZoomMode.FitInView)
        self.view.setPageMode(QPdfView.PageMode.SinglePage)
        layout.addWidget(self.view)
        self.pages = QComboBox()
        for page in document.pages:
            self.pages.addItem(f"Página {page + 1}", page)
        self.pages.currentIndexChanged.connect(self.jump)
        layout.addWidget(self.pages)
        self.jump()
        self.finished.connect(self.release)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def release(self, *_):
        self.pdf.close()
        self.buffer.close()
        self.buffer.setData(QByteArray())
        self.deleteLater()

    def jump(self, *_):
        self.view.pageNavigator().jump(self.pages.currentData(), self.view.pageNavigator().currentLocation(), 0)


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurações de impressão")
        self.result_settings = settings
        layout = QFormLayout(self)
        self.numbers = {}
        for key, label, low, high in [
            ("width_mm", "Largura (mm)", 70, 210),
            ("height_mm", "Altura (mm)", 100, 297),
            ("font_size", "Fonte geral (pt)", 9, 22),
            ("emphasis_size", "Tamanho / quantidade (pt)", 12, 28),
            ("margin_mm", "Margem do documento (mm)", 2, 12),
            ("label_margin_mm", "Margem adicional da etiqueta (mm)", 0, 12),
        ]:
            widget = QDoubleSpinBox()
            widget.setRange(low, high)
            widget.setValue(getattr(settings, key))
            widget.setSuffix(" pt" if key in {"font_size", "emphasis_size"} else " mm")
            layout.addRow(label, widget)
            self.numbers[key] = widget
        self.mode = QComboBox()
        self.mode.addItem("A — Etiqueta + Lista de separação", "picking")
        self.mode.addItem("B — Etiqueta + Documento original", "original")
        self.mode.setCurrentIndex(self.mode.findData(settings.mode))
        layout.addRow("Documento", self.mode)
        self.order = QComboBox()
        self.order.addItem("Etiqueta antes do documento", "label_first")
        self.order.addItem("Documento antes da etiqueta", "order_first")
        self.order.setCurrentIndex(self.order.findData(settings.page_order))
        layout.addRow("Ordem das páginas", self.order)
        self.sort = QComboBox()
        self.sort.addItem("Número do pedido", "order")
        self.sort.addItem("Transportadora e pedido", "carrier")
        self.sort.setCurrentIndex(self.sort.findData(settings.sort_by))
        layout.addRow("Ordenação do lote", self.sort)
        self.folder = QLineEdit(settings.save_directory)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder)
        choose = QPushButton("Escolher…")
        choose.clicked.connect(self.choose_folder)
        folder_row.addWidget(choose)
        layout.addRow("Pasta sugerida para salvar", folder_row)
        note = QLabel("A pasta é somente uma sugestão para salvar. Nenhum arquivo será procurado.\nA lista de separação não é uma declaração de conteúdo oficial.\nImprima em tamanho real (100%), sem ajuste adicional do driver.")
        note.setWordWrap(True)
        layout.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.commit)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def choose_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Pasta sugerida para salvar", self.folder.text())
        if directory:
            self.folder.setText(directory)

    def commit(self):
        self.result_settings = Settings(**{key: widget.value() for key, widget in self.numbers.items()}, mode=self.mode.currentData(), page_order=self.order.currentData(), sort_by=self.sort.currentData(), save_directory=self.folder.text())
        self.result_settings.validate()
        self.accept()


class ReviewDialog(QDialog):
    def __init__(self, doc: Document, parent=None):
        super().__init__(parent)
        self.document = doc
        self.setWindowTitle("Revisar documento e produtos")
        self.resize(800, 600)
        layout = QVBoxLayout(self)
        info = QLabel(doc.description + "\n" + "\n".join(doc.issues))
        info.setWordWrap(True)
        layout.addWidget(info)
        preview = QPushButton("Visualizar original antes de confirmar")
        preview.clicked.connect(lambda: PreviewDialog(doc, self).exec())
        layout.addWidget(preview)
        form = QFormLayout()
        self.kind = QComboBox()
        for kind in Kind:
            self.kind.addItem(kind.value, kind)
        self.kind.setCurrentIndex(self.kind.findData(doc.kind))
        self.number = QLineEdit(doc.order_id or "")
        self.name = QLineEdit(doc.recipient)
        self.carrier = QComboBox()
        self.carrier.addItems(["", "Loggi", "Correios", "Outra (confirmada pelo operador)"])
        self.carrier.setCurrentText(doc.carrier)
        form.addRow("Tipo", self.kind)
        form.addRow("Número do pedido", self.number)
        form.addRow("Destinatário", self.name)
        form.addRow("Transportadora", self.carrier)
        layout.addLayout(form)
        layout.addWidget(QLabel("Produtos: copie e confira o PDF original. Quantidade inteira positiva; não invente dados."))
        self.items = QTableWidget(0, 4)
        self.items.setHorizontalHeaderLabels(["Produto", "Tamanho / variação", "Quantidade", "SKU"])
        self.items.horizontalHeader().setStretchLastSection(True)
        for item in doc.items:
            self.add_item(item)
        layout.addWidget(self.items)
        actions = QHBoxLayout()
        add = QPushButton("Adicionar produto")
        add.clicked.connect(lambda: self.add_item())
        remove = QPushButton("Remover produto selecionado")
        remove.clicked.connect(lambda: self.items.removeRow(self.items.currentRow()) if self.items.currentRow() >= 0 else None)
        actions.addWidget(add)
        actions.addWidget(remove)
        layout.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.commit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def add_item(self, item: Item | None = None):
        row = self.items.rowCount()
        self.items.insertRow(row)
        values = [item.name, item.variation, str(item.quantity), item.sku] if item else ["", "", "", ""]
        for index, value in enumerate(values):
            self.items.setItem(row, index, QTableWidgetItem(value))

    def commit(self):
        kind = self.kind.currentData()
        number = self.number.text().strip()
        if self.document.ambiguous_orders and kind != Kind.UNKNOWN:
            QMessageBox.warning(self, "Página com vários pedidos", "Separe esta página em PDFs por pedido antes de importar. Uma página com vários pedidos não pode ser liberada como um único documento.")
            return
        if kind != Kind.UNKNOWN and (not number.isdigit() or not 1 <= len(number) <= 12):
            QMessageBox.warning(self, "Confira o pedido", "Informe um número de pedido de 1 a 12 dígitos, conferido no original.")
            return
        if kind == Kind.LABEL and not self.carrier.currentText():
            QMessageBox.warning(self, "Confira a etiqueta", "Informe a transportadora.")
            return
        items = []
        for row in range(self.items.rowCount()):
            values = [(self.items.item(row, col).text().strip() if self.items.item(row, col) else "") for col in range(4)]
            if not any(values):
                continue
            if not values[0] or not values[2].isdigit() or not 0 < int(values[2]) <= 99999:
                QMessageBox.warning(self, "Confira os produtos", f"Produto {row + 1}: nome e quantidade inteira positiva obrigatórios.")
                return
            items.append(Item(values[0], int(values[2]), values[1], values[3]))
        if QMessageBox.question(self, "Confirmar revisão", "Confirma que os dados foram conferidos no PDF original?\nA revisão substitui o reconhecimento automático deste documento.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        doc = self.document
        doc.kind, doc.order_id = kind, number or None
        doc.recipient = self.name.text().strip()
        doc.carrier = self.carrier.currentText() if kind == Kind.LABEL else ""
        doc.items = items if kind == Kind.ORDER else []
        doc.items_verified = bool(items) and kind == Kind.ORDER
        doc.issues = ["Dados revisados e confirmados pelo operador."]
        self.accept()
