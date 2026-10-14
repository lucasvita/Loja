from __future__ import annotations
import time
from pathlib import Path
import pytest
from PySide6.QtCore import QMimeData, QPointF, QSettings, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QMessageBox
from hilf_print.dialogs import PreviewDialog, ReviewDialog, SettingsDialog
from hilf_print.ui import MainWindow
from conftest import label_text, order_text


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path):
    store = QSettings(str(tmp_path / "preferences.ini"), QSettings.Format.IniFormat)
    w = MainWindow(store)
    w.show()
    app.processEvents()
    yield w
    w.close()
    app.processEvents()


def wait_worker(app, window):
    deadline = time.monotonic() + 15
    while window.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    app.processEvents()
    assert not window.busy


def test_drag_multiple_pdfs_background_and_clear(app, window, pdf_factory, monkeypatch):
    paths = [pdf_factory("abc.pdf", [order_text()]), pdf_factory("xyz.pdf", [label_text()])]
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    enter = QDragEnterEvent(window.rect().center(), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.dragEnterEvent(enter)
    assert enter.isAccepted()
    drop = QDropEvent(QPointF(window.rect().center()), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.dropEvent(drop)
    assert window.busy
    assert not window.clear_button.isEnabled()
    wait_worker(app, window)
    assert len(window.batch.pairs()) == 1
    assert window.generate_button.isEnabled()
    window.table.selectRow(0)
    app.processEvents()
    assert "abc.pdf" in window.details.toPlainText()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window.new_batch()
    assert not window.batch.sources
    assert window.table.rowCount() == 0
    assert not window.generate_button.isEnabled()


def test_corrupt_file_does_not_stop_import(app, window, pdf_factory, tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"broken")
    window.import_paths([bad, pdf_factory("good.pdf", [order_text()])])
    wait_worker(app, window)
    assert len(window.batch.sources) == 1
    assert len(window.batch.errors) == 1
    assert "Erros: 1" in window.counter.text()


def test_preferences_only_no_restoration(app, window, matched_batch):
    batch = matched_batch()
    window.batch = batch
    window.settings.emphasis_size = 24
    window.settings.save(window.store)
    new = MainWindow(window.store)
    assert new.settings.emphasis_size == 24
    assert not new.batch.sources and not new.batch.documents
    new.close()


def test_preview_and_settings_dialog(app, window, matched_batch):
    doc = matched_batch().pairs()[0].order
    dialog = PreviewDialog(doc, window)
    dialog.show()
    app.processEvents()
    assert dialog.pdf.pageCount() == 1
    assert dialog.view.pageNavigator().currentPage() == 0
    dialog.close()
    config = SettingsDialog(window.settings, window)
    assert config.numbers["emphasis_size"].value() == 18
    assert config.numbers["font_size"].value() == 12
    config.close()


def test_review_requires_valid_items_and_explicit_confirmation(app, window, matched_batch, monkeypatch):
    doc = matched_batch().pairs()[0].order
    dialog = ReviewDialog(doc, window)
    dialog.items.item(0, 2).setText("5")
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    dialog.commit()
    assert doc.items[0].quantity == 1
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    dialog.commit()
    assert doc.items[0].quantity == 5 and doc.items_verified
    dialog.close()


def test_preview_releases_pdf_bytes_on_close(app, window, matched_batch):
    doc = matched_batch().pairs()[0].order
    dialog = PreviewDialog(doc, window)
    assert dialog.buffer.size() > 0
    dialog.reject()
    assert dialog.buffer.size() == 0
    assert dialog.pdf.pageCount() == 0
