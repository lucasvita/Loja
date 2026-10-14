from __future__ import annotations

import logging
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from .pdf_reader import read_pdf
from .pdf_writer import export_pdf

log = logging.getLogger("hilf_print")


class ImportWorker(QThread):
    imported = Signal(object, object)
    failed = Signal(str)
    progress = Signal(int, int)

    def __init__(self, paths: list[Path], remaining_bytes: int, digests: set[str], parent=None):
        super().__init__(parent)
        self.paths = paths
        self.remaining_bytes = remaining_bytes
        self.digests = set(digests)

    def run(self) -> None:
        for index, path in enumerate(self.paths, 1):
            if self.isInterruptionRequested():
                break
            try:
                source, documents = read_pdf(path)
                if source.digest not in self.digests:
                    if len(source.data) > self.remaining_bytes:
                        raise ValueError("Lote excede 512 MiB; divida em lotes menores.")
                    self.remaining_bytes -= len(source.data)
                    self.digests.add(source.digest)
                self.imported.emit(source, documents)
            except Exception as exc:
                log.warning("import_failed", extra={"error_type": type(exc).__name__})
                # Only this explicit UI error contains the user's selected filename.
                message = str(exc) if isinstance(exc, ValueError) else "Falha inesperada ao ler o PDF."
                self.failed.emit(f"{path.name}: {message}")
            self.progress.emit(index, len(self.paths))


class ExportWorker(QThread):
    exported = Signal(object)
    failed = Signal(str)

    def __init__(self, pairs, target, settings, original_paths, parent=None):
        super().__init__(parent)
        self.pairs, self.target, self.settings, self.original_paths = pairs, target, settings, original_paths

    def run(self) -> None:
        try:
            self.exported.emit(export_pdf(self.pairs, self.target, self.settings, self.original_paths))
        except Exception as exc:
            log.warning("export_failed", extra={"error_type": type(exc).__name__})
            self.failed.emit(str(exc) if isinstance(exc, (ValueError, OSError)) else "Falha ao gerar o PDF; nenhum arquivo parcial foi salvo.")
