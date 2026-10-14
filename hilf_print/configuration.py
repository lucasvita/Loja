from __future__ import annotations
from dataclasses import dataclass, fields
from typing import Any


@dataclass
class Settings:
    width_mm: float = 100.0
    height_mm: float = 150.0
    font_size: float = 12.0
    emphasis_size: float = 18.0
    margin_mm: float = 4.0
    label_margin_mm: float = 0.0
    mode: str = "picking"
    page_order: str = "label_first"
    sort_by: str = "order"
    save_directory: str = ""

    def validate(self) -> None:
        if not (70 <= self.width_mm <= 210 and 100 <= self.height_mm <= 297):
            raise ValueError("Formato deve ter largura de 70–210 mm e altura de 100–297 mm.")
        if not 9 <= self.font_size <= 22:
            raise ValueError("Fonte deve estar entre 9 e 22 pontos.")
        if not 12 <= self.emphasis_size <= 28:
            raise ValueError("Fonte de tamanho e quantidade deve estar entre 12 e 28 pontos.")
        if not 2 <= self.margin_mm <= 12:
            raise ValueError("Margem deve estar entre 2 e 12 mm.")
        if not 0 <= self.label_margin_mm <= 12:
            raise ValueError("Margem adicional de etiqueta deve estar entre 0 e 12 mm.")
        if self.mode not in {"picking", "original"} or self.page_order not in {"label_first", "order_first"} or self.sort_by not in {"order", "carrier"}:
            raise ValueError("Opção de impressão inválida.")

    @classmethod
    def load(cls, store: Any) -> Settings:
        defaults = cls()
        values = {}
        for f in fields(cls):
            default = getattr(defaults, f.name)
            try:
                values[f.name] = type(default)(store.value(f.name, default))
            except (ValueError, TypeError):
                values[f.name] = default
        result = cls(**values)
        try:
            result.validate()
            return result
        except ValueError:
            return defaults

    def save(self, store: Any) -> None:
        self.validate()
        for f in fields(self):
            store.setValue(f.name, getattr(self, f.name))
        store.sync()
