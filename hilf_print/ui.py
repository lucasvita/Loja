from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)
from .configuration import Settings
from .dialogs import PreviewDialog, ReviewDialog, SettingsDialog
from .matching import Batch
from .models import Kind, Status
from .pdf_reader import MAX_BATCH_BYTES
from .pdf_writer import export_warnings
from .validation import divergent
from .workers import ExportWorker, ImportWorker


class OrderCell(QTableWidgetItem):
    def __lt__(self, other):
        a, b = self.text().lstrip("#"), other.text().lstrip("#")
        return int(a) < int(b) if a.isdigit() and b.isdigit() else a < b


class MainWindow(QMainWindow):
    def __init__(self, store: QSettings | None = None):
        super().__init__()
        self.batch = Batch()
        self.store = store or QSettings("Hilf Streetwear", "Hilf Print")
        self.settings = Settings.load(self.store)
        self.worker = None
        self._close_pending = False
        self.rows = []
        self.setWindowTitle("HILF PRINT — Hilf Streetwear")
        self.resize(1120, 760)
        self.setAcceptDrops(True)
        widget = QWidget()
        self.setCentralWidget(widget)
        layout = QVBoxLayout(widget)
        title = QLabel("HILF PRINT")
        title.setStyleSheet("font-size: 28px; font-weight: 700;")
        layout.addWidget(title)
        layout.addWidget(QLabel("Organizador de etiquetas e pedidos — Hilf Streetwear"))
        self.drop_area = QLabel("ARRASTE SEUS PDFs AQUI\nSomente os arquivos selecionados serão analisados. Funcionamento 100% offline.")
        self.drop_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_area.setStyleSheet("border: 2px dashed #64748b; border-radius: 10px; padding: 24px; font-size: 16px;")
        layout.addWidget(self.drop_area)
        toolbar = QHBoxLayout()
        self.add_button = QPushButton("Adicionar PDFs")
        self.generate_button = QPushButton("Gerar PDF")
        self.clear_button = QPushButton("Novo lote")
        self.settings_button = QPushButton("Configurações")
        for button, callback in [(self.add_button, self.choose_files), (self.generate_button, self.generate), (self.clear_button, self.new_batch), (self.settings_button, self.configure)]:
            button.clicked.connect(callback)
            toolbar.addWidget(button)
        layout.addLayout(toolbar)
        self.counter = QLabel()
        layout.addWidget(self.counter)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Pedido", "Cliente", "Transportadora", "Status"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(1, 300)
        self.table.setColumnWidth(2, 150)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        layout.addWidget(self.table, 1)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(110)
        layout.addWidget(self.details)
        actions = QHBoxLayout()
        self.preview_button = QPushButton("Visualizar arquivo")
        self.review_button = QPushButton("Revisar dados / itens")
        self.manual_button = QPushButton("Parear manualmente")
        self.exclude_button = QPushButton("Excluir / reincluir pedido")
        self.remove_button = QPushButton("Remover arquivo do lote")
        for button, callback in [(self.preview_button, self.preview), (self.review_button, self.review), (self.manual_button, self.manual_pair), (self.exclude_button, self.exclude), (self.remove_button, self.remove_file)]:
            actions.addWidget(button)
            button.clicked.connect(callback)
        layout.addLayout(actions)
        self.warning = QLabel("Lista de separação ≠ declaração de conteúdo oficial. Imprima a 100%, sem ajuste adicional.")
        self.warning.setWordWrap(True)
        layout.addWidget(self.warning)
        self.setStyleSheet("QMainWindow { background: #f8fafc; } QPushButton { padding: 9px 12px; } QTableWidget { background: white; } QLabel { color: #172033; }")
        self.refresh()

    @property
    def busy(self) -> bool:
        return self.worker is not None

    def set_busy(self, busy: bool):
        for button in [self.add_button, self.clear_button, self.settings_button, self.preview_button, self.review_button, self.manual_button, self.exclude_button, self.remove_button]:
            button.setEnabled(not busy)
        self.generate_button.setEnabled(not busy and bool(self.batch.pairs()))
        self.progress.setVisible(busy)
        if busy:
            self.progress.setRange(0, 0)
        else:
            self.selection_changed()

    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Adicionar PDFs deste lote", "", "PDF (*.pdf)")
        self.import_paths([Path(p) for p in files])

    def dragEnterEvent(self, event):
        if not self.busy and event.mimeData().hasUrls() and any(u.isLocalFile() and Path(u.toLocalFile()).suffix.lower() == ".pdf" for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.busy:
            return
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        self.import_paths(paths)
        event.acceptProposedAction()

    def import_paths(self, paths: list[Path]):
        if self.busy or not paths:
            return
        # No glob, traversal, directory watcher or restoration of historical paths.
        self.worker = ImportWorker(paths, MAX_BATCH_BYTES - sum(len(s.data) for s in self.batch.sources.values()), {s.digest for s in self.batch.sources.values()}, self)
        self.worker.imported.connect(self.received)
        self.worker.failed.connect(self.import_error)
        self.worker.progress.connect(self.import_progress)
        self.worker.finished.connect(self.finished)
        self.set_busy(True)
        self.worker.start()

    def received(self, source, documents):
        try:
            self.batch.add(source, documents)
        except ValueError as exc:
            self.batch.errors.append(str(exc))
        self.refresh()

    def import_error(self, message):
        self.batch.errors.append(message)
        self.refresh()

    def import_progress(self, done, total):
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.statusBar().showMessage(f"Analisando PDFs: {done}/{total}")

    def finished(self):
        worker = self.worker
        self.worker = None
        worker.deleteLater()
        self.set_busy(False)
        self.refresh()
        self.statusBar().showMessage("Processamento concluído. Confira o lote antes de gerar.")
        if self._close_pending:
            self.close()

    def refresh(self):
        self.rows = self.batch.rows()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.rows))
        for index, row in enumerate(self.rows):
            values = [f"#{row.order_id}" if row.order_id else "—", row.recipient or "Não extraído", row.carrier or "—", row.status.value]
            for column, value in enumerate(values):
                cell = OrderCell(value) if column == 0 else QTableWidgetItem(value)
                cell.setData(Qt.ItemDataRole.UserRole, index)
                if row.pair is None and row.status != Status.EXCLUDED:
                    cell.setForeground(QColor("#92400e"))
                cell.setToolTip(row.detail + "\n" + "\n".join(d.description for d in row.documents))
                self.table.setItem(index, column, cell)
        self.table.setSortingEnabled(True)
        self.table.sortItems(2 if self.settings.sort_by == "carrier" else 0)
        pairs = self.batch.pairs()
        pending = sum(r.pair is None and r.status != Status.EXCLUDED for r in self.rows)
        duplicates = sum(r.status == Status.DUPLICATE for r in self.rows) + self.batch.duplicate_imports
        self.counter.setText(f"Arquivos importados: {len(self.batch.sources)}   |   Pedidos pareados: {len(pairs)}   |   Pendências: {pending}   |   Duplicados: {duplicates}   |   Erros: {len(self.batch.errors)}")
        warnings = []
        if pending:
            warnings.append(f"{pending} pendência(s) ficará(ão) fora do PDF. Somente pares confirmados são exportados.")
        if self.batch.duplicate_imports:
            warnings.append(f"{self.batch.duplicate_imports} importação(ões) de PDFs idênticos ignorada(s).")
        if self.batch.errors:
            warnings.append("Erros de importação:\n" + "\n".join(self.batch.errors))
        self.warning.setText("\n".join(warnings) or "Lista de separação ≠ declaração de conteúdo oficial. Imprima a 100%, sem ajuste adicional.")
        self.generate_button.setEnabled(bool(pairs) and not self.busy)
        self.selection_changed()

    def selected_row(self):
        selected = self.table.selectedItems()
        return self.rows[selected[0].data(Qt.ItemDataRole.UserRole)] if selected else None

    def selection_changed(self):
        row = self.selected_row()
        for button in [self.preview_button, self.review_button, self.exclude_button, self.remove_button]:
            button.setEnabled(row is not None and not self.busy)
        self.manual_button.setEnabled(not self.busy and len(self.batch.documents) >= 2)
        self.details.setPlainText((row.detail + "\n" + "\n".join(d.description + ("\n  " + "; ".join(d.issues) if d.issues else "") for d in row.documents)) if row else "Selecione um pedido para visualizar os arquivos associados.")

    def choose_document(self, title):
        row = self.selected_row()
        if not row:
            return None
        if len(row.documents) == 1:
            return row.documents[0]
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        layout = QVBoxLayout(dialog)
        combo = QComboBox()
        for doc in row.documents:
            combo.addItem(doc.description, doc)
        layout.addWidget(combo)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        result = combo.currentData() if dialog.exec() == QDialog.DialogCode.Accepted else None
        dialog.deleteLater()
        return result

    def preview(self):
        if self.busy:
            return
        doc = self.choose_document("Escolher arquivo para visualizar")
        if doc:
            PreviewDialog(doc, self).exec()

    def review(self):
        if self.busy:
            return
        doc = self.choose_document("Escolher documento para revisar")
        if doc:
            dialog = ReviewDialog(doc, self)
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
            dialog.deleteLater()
            if accepted:
                self.batch.manual = [p for p in self.batch.manual if p.order.id != doc.id and p.label.id != doc.id]
                self.refresh()

    def manual_pair(self):
        if self.busy:
            return
        orders = [d for d in self.batch.documents.values() if d.kind == Kind.ORDER and d.id not in self.batch.excluded]
        labels = [d for d in self.batch.documents.values() if d.kind == Kind.LABEL and d.id not in self.batch.excluded]
        if not orders or not labels:
            QMessageBox.information(self, "Revisão necessária", "Reveja documentos não identificados e defina o tipo/número antes de parear. É necessário um pedido e uma etiqueta.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Pareamento manual — confira os originais")
        layout = QFormLayout(dialog)
        order_box, label_box = QComboBox(), QComboBox()
        for doc in orders:
            order_box.addItem(doc.description + f" · {doc.recipient}", doc)
        for doc in labels:
            label_box.addItem(doc.description + f" · {doc.recipient}", doc)
        row = self.selected_row()
        if row:
            for box in [order_box, label_box]:
                for index in range(box.count()):
                    if box.itemData(index) in row.documents:
                        box.setCurrentIndex(index)
                        break
        layout.addRow("Pedido", order_box)
        layout.addRow("Etiqueta", label_box)
        for box, text in [(order_box, "Visualizar pedido"), (label_box, "Visualizar etiqueta")]:
            button = QPushButton(text)
            button.clicked.connect(lambda _, b=box: PreviewDialog(b.currentData(), dialog).exec())
            layout.addRow(button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        order, label = order_box.currentData(), label_box.currentData()
        dialog.deleteLater()
        if not accepted:
            return
        differences = divergent(order, label)
        message = "\n".join(differences) + "\n\n" if differences else ""
        message += f"Confirma o pareamento do pedido #{order.order_id} com a etiqueta #{label.order_id}?\nEsta escolha substitui pares anteriores que usam estes documentos."
        if QMessageBox.question(self, "Confirmar dados divergentes" if differences else "Confirmar pareamento", message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.batch.pair_manually(order.id, label.id, confirmed=True)
            self.refresh()

    def exclude(self):
        row = self.selected_row()
        if self.busy or not row:
            return
        ids = {d.id for d in row.documents}
        if row.status == Status.EXCLUDED:
            self.batch.excluded.difference_update(ids)
        else:
            self.batch.excluded.update(ids)
            self.batch.manual = [p for p in self.batch.manual if p.order.id not in ids and p.label.id not in ids]
        self.refresh()

    def remove_file(self):
        if self.busy:
            return
        doc = self.choose_document("Escolher arquivo para remover do lote")
        if doc and QMessageBox.question(self, "Remover do lote", "Remover todas as páginas deste arquivo do lote?\nO arquivo original será preservado.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.batch.remove_source(doc.source.id)
            self.refresh()

    def new_batch(self):
        if self.busy:
            return
        if self.batch.sources or self.batch.errors:
            if QMessageBox.question(self, "Novo lote", "Descartar a fila atual e iniciar um lote vazio?\nOs PDFs originais e arquivos gerados serão preservados.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
        self.batch.clear()
        self.details.clear()
        self.refresh()

    def configure(self):
        if self.busy:
            return
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings = dialog.result_settings
            self.settings.save(self.store)
            self.refresh()
        dialog.deleteLater()

    def generate(self):
        if self.busy:
            return
        pairs = self.batch.pairs()
        if not pairs:
            return
        invalid = [p for p in pairs if not p.order.items_verified or not p.order.items]
        if self.settings.mode == "picking" and invalid:
            QMessageBox.warning(self, "Revisão de produtos necessária", "O modo A exige produtos e quantidades confirmados.\nRevise os itens ou escolha o modo B (Documento original).\nPedidos: " + ", ".join(f"#{p.order.order_id}" for p in invalid))
            return
        pending = sum(r.pair is None and r.status != Status.EXCLUDED for r in self.batch.rows())
        warnings = export_warnings(pairs, self.settings)
        summary = f"{len(pairs)} pedido(s) confirmado(s).\n{pending} pendência(s) ficará(ão) fora do PDF.\nFormato: {self.settings.width_mm:g} × {self.settings.height_mm:g} mm.\nModo: {'Lista de separação' if self.settings.mode == 'picking' else 'Documento original'}.\nEtiqueta {'antes' if self.settings.page_order == 'label_first' else 'depois'} do documento."
        box = QMessageBox(QMessageBox.Icon.Warning if warnings else QMessageBox.Icon.Information, "Conferir resumo do lote", summary + (f"\n{len(warnings)} aviso(s) de escala; consulte os detalhes." if warnings else ""), QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel, self)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        box.setDetailedText("\n".join([f"Pedido #{p.order.order_id} — {p.label.carrier}" for p in pairs] + warnings))
        result = box.exec()
        box.deleteLater()
        if result != QMessageBox.StandardButton.Ok:
            return
        suggested = str(Path(self.settings.save_directory) / "Hilf Print - lote.pdf") if self.settings.save_directory else "Hilf Print - lote.pdf"
        name, _ = QFileDialog.getSaveFileName(self, "Salvar PDF do lote", suggested, "PDF (*.pdf)")
        if not name:
            return
        target = Path(name)
        if target.suffix.lower() != ".pdf":
            target = target.with_suffix(".pdf")
        if target.exists():
            QMessageBox.warning(self, "Escolha um novo nome", "O Hilf Print não substitui PDFs existentes. Escolha um nome diferente para preservar os arquivos anteriores.")
            return
        self.worker = ExportWorker(pairs, target, self.settings, set(self.batch.original_paths), self)
        self.worker.exported.connect(lambda report: QMessageBox.information(self, "PDF gerado", f"{report.pairs} pedido(s), {report.pages} página(s).\nPDF salvo no local escolhido.\nImprima em tamanho real (100%) e confira os códigos de barras."))
        self.worker.failed.connect(lambda message: QMessageBox.warning(self, "PDF não gerado", message))
        self.worker.finished.connect(self.finished)
        self.set_busy(True)
        self.worker.start()

    def closeEvent(self, event):
        if self.busy:
            self._close_pending = True
            if isinstance(self.worker, ImportWorker):
                self.worker.requestInterruption()
            self.statusBar().showMessage("Finalizando a operação antes de fechar…")
            event.ignore()
            return
        self.batch.clear()
        event.accept()
