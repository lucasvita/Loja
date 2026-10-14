# HILF PRINT

Aplicativo desktop **offline** para a Hilf Streetwear. Analisa apenas os PDFs adicionados pelo operador, pareia etiquetas com pedidos e gera um PDF térmico. Não acessa APIs, monitora pastas, consulta a internet nem restaura arquivos de sessões anteriores.

## Uso

1. Abra o Hilf Print e arraste os PDFs, ou use **Adicionar PDFs**.
2. Confira os contadores, a tabela e os arquivos associados. **Visualizar arquivo** abre uma prévia local do original.
3. Resolva pendências com **Revisar dados / itens** ou **Parear manualmente**. Números ou destinatários divergentes exigem confirmação explícita. PDFs duplicados não são escolhidos automaticamente.
4. Em **Configurações**, escolha formato, fontes e modo. Padrão: 100 × 150 mm, produto em 12 pt, **tamanho/variação e quantidade em 18 pt e negrito**. Fonte desses destaques é independente da fonte geral. A etiqueta preserva suas margens originais; margem adicional padrão é zero, para evitar redução desnecessária dos códigos.
5. Clique em **Gerar PDF**, confira o resumo e escolha **um nome novo** para salvar. Por segurança, nenhum PDF existente é substituído, inclusive de sessões anteriores.
6. Imprima o PDF em tamanho real / **100%**, sem “ajustar à página” no driver. Faça a primeira impressão de conferência na térmica, com leitura dos códigos pelo seu scanner.
7. **Novo lote** descarta integralmente a fila. Fechar também descarta o lote. Somente preferências de impressão são persistidas.

**Modo A (padrão):** etiqueta original, seguida da lista de separação com produtos, variações, quantidades, SKU e total de peças. O conteúdo continua em outras páginas quando necessário, sem cortes ou redução automática da fonte.

**Modo B:** etiqueta original, seguida de todas as páginas do pedido original, ajustadas proporcionalmente. Documentos A4 podem ficar pequenos em papel térmico; use A para separar peças.

A lista de separação **não é uma declaração de conteúdo postal oficial**. O aplicativo não gera nem valida uma declaração formal; remetente/destinatário completos, CPF/CNPJ, valores e assinatura precisam atender aos requisitos postais. O documento de origem é preservado pelo modo B, sem certificação de validade.

## Desenvolvimento — Windows 10/11 x64

Instale Python 3.12 x64. No PowerShell, na pasta do projeto:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m hilf_print
```

Também pode abrir `scripts\run-windows.bat` depois de instalar as dependências. O aplicativo não exige internet após a instalação.

## Executável Windows portátil

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-windows.ps1
```

O script executa os testes antes da compilação e gera:

- `dist\HilfPrint\HilfPrint.exe`
- `dist\HilfPrint-Windows.zip`

Copie **a pasta inteira**, incluindo `_internal`; o `.exe` sozinho não é suficiente. Não exige Python na máquina de destino. As preferências e o log ficam no perfil local do usuário; o aplicativo/pasta de distribuição é portátil, sem instalador obrigatório.

PyInstaller compila para o sistema em que é executado. **O ambiente de desenvolvimento desta entrega é Linux. Um build Linux não valida nem produz um `.exe` Windows.** A compilação e a abertura no Windows, o arraste pelo Explorer e a impressão física ainda precisam ser validados no Windows. A prévia usa QtPdf, sem navegador incorporado.

## Desenvolvimento e testes — Linux

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/python -m hilf_print  # precisa de sessão gráfica
QT_QPA_PLATFORM=offscreen .venv/bin/python -m hilf_print --smoke-test
```

Os testes usam PDFs sintéticos e Qt em modo offscreen: pareamento, Loggi/Correios, nomes aleatórios, upload embaralhado com 120 PDFs, duplicidades, pendências, nomes divergentes, multipágina, arquivos corrompidos, impressão térmica, vetores, destaque das fontes, proteção dos originais, interface, arraste, revisão, limpeza e isolamento de sessões.

Validação adicional dos exemplos reais, **somente com caminhos explicitamente informados**, usando dependências exclusivas de QA:

```bash
.venv/bin/python -m pip install -r requirements-qa.txt
.venv/bin/python scripts/validate_samples.py \
  --inputs pedido1.pdf pedido2.pdf etiquetas1.pdf etiquetas2.pdf \
  --combined lote-ja-organizado.pdf \
  --output-dir resultados-novos
```

`--combined` é opcional. Use uma pasta nova de saída. O verificador compara produtos/quantidades com as colunas de preço, verifica subtotais, sequência e formato das páginas, limites de texto, imagens originais e códigos por decodificação óptica. A referência de preservação usa 600 dpi; rastreios são conferidos também a 203 dpi. Variações de decodificação de códigos auxiliares em outras resoluções são registradas, não escondidas. O código e os testes não incluem PDFs reais nem dados pessoais da empresa.

## Regras de segurança e limites

- Pareamento por **número explícito de pedido**, sem usar nome do arquivo ou ordem de upload. Nome de entrega normalizado é a validação secundária; nomes divergentes bloqueiam o pareamento automático. Nome ausente é sinalizado, e a chave continua sendo o número explícito.
- PDFs idênticos por conteúdo são ignorados e contados. Dois pedidos/etiquetas do mesmo número bloqueiam a exportação até revisão. Resolver manualmente uma cópia não libera outra cópia automaticamente.
- Uma página com vários números de pedido é bloqueada; separe essa página por pedido fora do aplicativo. Páginas de pedidos diferentes no mesmo PDF são tratadas separadamente.
- Continuação de pedido exige número repetido, páginas consecutivas e numeração explícita (`Página 1 de 2`, `Página 2 de 2`). Sem prova de continuação, são pendências/duplicidades. Páginas sem número não são anexadas por adivinhação.
- Reconhecimento Loja Integrada: tabela `Código / Nome / Valor unitário / Qtd. / Valor total`, variações de tamanho de calça, camisa/camiseta e juvenil-infantil; também há suporte a blocos explícitos `Produto / Tamanho / Quantidade` e tabelas delimitadas. Um layout novo deve ser conferido. Se produtos/quantidades não forem extraídos com segurança, A é bloqueado; revise os itens ou use B.
- Não há OCR. PDFs digitalizados/imagens ou protegidos por senha ficam pendentes; uma revisão manual conferida no original é possível para páginas sem identificação, exceto páginas com vários pedidos.
- Importação e exportação em segundo plano; uma operação por vez. PDFs são mantidos como bytes, sem renderizar todo o lote em imagens. Prévia é feita sob demanda. Limites: 128 MiB por arquivo e 512 MiB por lote; divida arquivos maiores.
- Nenhum original é modificado/apagado; o lote trabalha com uma cópia em memória e a saída não substitui arquivos existentes. Um erro em um PDF não interrompe os seguintes.
- Logs locais rotativos guardam códigos de eventos, sem nomes, endereços, caminhos ou conteúdo de PDFs. A interface mostra erros referentes aos arquivos que o operador selecionou.
- O aplicativo não garante legibilidade física de uma impressora desconhecida: resolução, aquecimento, papel, driver e qualidade dos códigos no PDF original influenciam a impressão. Confirme o primeiro lote na impressora antes de expedir.

## Organização

`models.py` — dados do lote; `pdf_reader.py` — leitura; `classification.py` — tipos/números; `extraction.py` — destinatários/produtos; `matching.py` — pareamento e sessão; `validation.py` — divergências; `pdf_writer.py` — exportação; `configuration.py` — preferências; `ui.py` / `dialogs.py` — interface; `workers.py` — processamento; `tests/` — testes; `scripts/` e `HilfPrint.spec` — execução, QA e compilação.
