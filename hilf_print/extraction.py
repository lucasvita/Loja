from __future__ import annotations

import re
from .classification import normalize
from .models import Item


NAME_KEYS = r"(?:nome\s+do\s+(?:cliente|destinat[aá]rio)|destinat[aá]rio|cliente|comprador)"


def recipient(text: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(rf"^[ \t]*{NAME_KEYS}[ \t]*[:\-]?[ \t]*([^\n]*)$", line, re.I)
        if not match:
            continue
        value = match.group(1).strip()
        next_index = index + 1
        while not value and next_index < len(lines):
            value = lines[next_index].strip()
            next_index += 1
        if not value or re.search(r"^(?:cpf|cnpj|endereco|endere[çc]o|cep|pedido)\b", normalize(value)):
            continue
        # Some Loggi labels wrap the final surname onto its own line. Continue only
        # name-shaped lines; address prefixes, punctuation and numbers terminate it.
        for following in lines[next_index:next_index + 3]:
            candidate = following.strip()
            normalized = normalize(candidate)
            if not candidate or not re.fullmatch(r"[^\W\d_]+(?:[ \-'][^\W\d_]+){0,3}", candidate, re.UNICODE):
                break
            if re.match(r"(?:rua|r|avenida|av|rodovia|estrada|alameda|travessa|praca|quadra|sitio|fazenda|condominio|bairro|centro|cep|remetente|produto|calcas|destinatario|cpf|cnpj|cliente|telefone|dados)\b", normalized):
                break
            value += " " + candidate
        return value
    return ""


def _quantity(value: str) -> int | None:
    m = re.fullmatch(r"\s*(\d{1,5})(?:[,.]0+)?(?:\s*(?:un|unidades?|pe[çc]as?))?\s*", value, re.I)
    return int(m.group(1)) if m and int(m.group(1)) > 0 else None


def _column(header: str) -> str:
    name = normalize(header)
    if name in {"produto", "produtos", "descricao", "descricao do produto", "item", "nome"}:
        return "name"
    if name in {"quantidade", "qtd", "qtde", "quant"}:
        return "quantity"
    if name in {"variacao", "variacoes", "tamanho", "opcoes"}:
        return "variation"
    if name in {"sku", "codigo", "codigo sku"}:
        return "sku"
    return ""


def table_items(rows: list[list[str | None]]) -> tuple[list[Item], bool]:
    result: list[Item] = []
    columns: dict[str, int] = {}
    valid = True
    for row in rows:
        aliases = {_column(str(cell or "")): i for i, cell in enumerate(row) if _column(str(cell or ""))}
        if "name" in aliases and "quantity" in aliases:
            columns = aliases
            continue
        if not columns or not any(str(c or "").strip() for c in row):
            continue
        def get(key: str) -> str:
            i = columns.get(key)
            return str(row[i] or "").strip() if i is not None and i < len(row) else ""
        name = get("name")
        if normalize(name).startswith(("total", "frete", "subtotal", "desconto")):
            continue
        qty = _quantity(get("quantity"))
        if not name or qty is None:
            valid = False
            continue
        name_lines = name.splitlines()
        product_lines, variations = [], []
        for line in name_lines:
            if re.match(r"\s*Disponibilidade\s*:", line, re.I):
                continue
            match = re.match(r"\s*(?:cal[çc]as|tamanho[^:]*|varia[çc][aã]o|cor|camisetas?|bermudas?)\s*:\s*(.+)", line, re.I)
            if match:
                variations.append(match.group(1).strip())
            else:
                product_lines.append(line.strip())
        variation = " / ".join(filter(None, [get("variation"), *variations]))
        product = " ".join(product_lines).strip()
        if not product:
            valid = False
            continue
        result.append(Item(product, qty, variation, get("sku")))
    return result, bool(result) and valid


def extract_items(text: str, tables: list[list[list[str | None]]] | None = None) -> tuple[list[Item], bool, list[str]]:
    if tables:
        collected: list[Item] = []
        verified = True
        for rows in tables:
            parsed, ok = table_items(rows)
            if parsed:
                collected.extend(parsed)
                verified &= ok
        if collected:
            return collected, verified, [] if verified else ["Tabela de produtos contém linhas incompletas."]
    # Exporters with pipe/tab-delimited text are handled without relying on filenames.
    lines = text.splitlines()
    rows = [re.split(r"\s*\|\s*|\t", line.strip()) for line in lines if "|" in line or "\t" in line]
    if rows:
        parsed, ok = table_items(rows)
        if parsed:
            return parsed, ok, [] if ok else ["Tabela de produtos contém linhas incompletas."]
    # Explicit item blocks, e.g. Produto: CALÇA ... / Tamanho: 38 / Quantidade: 2.
    starts = list(re.finditer(r"^\s*(?:produto|descri[çc][aã]o(?:\s+do\s+produto)?)\s*:\s*(.+)$", text, re.I | re.M))
    result = []
    complete = True
    for index, start in enumerate(starts):
        block = text[start.end():starts[index + 1].start() if index + 1 < len(starts) else len(text)]
        qm = re.search(r"^\s*(?:quantidade|qtd\.?|qtde\.?)\s*:\s*([^\n]+)", block, re.I | re.M)
        qty = _quantity(qm.group(1)) if qm else None
        if qty is None:
            complete = False
            continue
        variations = re.findall(r"^\s*(?:tamanho|varia[çc][aã]o|cor)\s*:\s*([^\n]+)", block, re.I | re.M)
        sku = re.search(r"^\s*SKU\s*:\s*([^\n]+)", block, re.I | re.M)
        result.append(Item(start.group(1).strip(), qty, " / ".join(variations), sku.group(1).strip() if sku else ""))
    if result:
        # A stated total, when present, must agree with extracted quantities.
        total = re.search(r"total\s+(?:de\s+)?(?:pe[çc]as|itens)\s*:\s*(\d+)", text, re.I)
        if total and int(total.group(1)) != sum(i.quantity for i in result):
            complete = False
        return result, complete, [] if complete else ["Produtos incompletos ou total de peças divergente."]
    return [], False, ["Produtos/quantidades não extraídos com segurança. Use o documento original ou revise os itens."]


def page_recipient(page, text: str) -> str:
    """Extract the shipping recipient, not the billing customer's name."""
    words = page.get_text("words")
    for word in words:
        if normalize(word[4]) == "destinatario" and word[0] >= page.rect.width * 0.45 and word[1] < page.rect.height * 0.3:
            # Loja Integrada has sender and recipient side by side. Geometry avoids mixing them.
            candidates = [w for w in words if w[0] >= page.rect.width * 0.49 and w[1] > word[3] and w[1] < word[3] + 45]
            if candidates:
                first_y = min(w[1] for w in candidates)
                line = sorted([w for w in candidates if abs(w[1] - first_y) < 3], key=lambda w: w[0])
                return " ".join(w[4] for w in line).strip()
    return recipient(text)
