# Validação da entrega — 14/10/2026

## Executado neste ambiente Linux, Python 3.12.14

- **47 testes automatizados passaram**, sem falhas e sem testes ignorados. Incluem lote embaralhado com **120 PDFs**, leitura/classificação, Loggi e Correios, produtos/variações/quantidades, pendências, destinatários divergentes, duplicidades, multipágina, corrupção, impressão térmica, paginação, proteção dos originais, revisão, arraste simulado, processamento em segundo plano, preferências sem restauração e limpeza do lote/prévia.
- Instalação repetida pelo script salvo, com os mesmos 47 testes aprovados. `pip check`: nenhuma dependência inconsistente.
- Interface aberta e conferida visualmente por captura em **Qt offscreen**. Prévia QtPdf abriu PDF local. Eventos de arraste de vários PDFs foram exercitados automaticamente, com espera do processamento em segundo plano.
- Build **Linux** pelo `HilfPrint.spec` e abertura do aplicativo empacotado via `--smoke-test` concluídos com código 0. Isso verifica o empacotamento neste sistema, não um executável Windows.

## Sete PDFs reais enviados pelo usuário

Os seis arquivos de origem foram validados juntos; o PDF já organizado foi testado separadamente e em conjunto com eles.

| Conferência | Resultado |
|---|---|
| Pedidos nos arquivos de origem | 67 |
| Etiquetas nos arquivos de origem | 66 |
| Pares automáticos confirmados | **66** |
| Pedido sem etiqueta | **um pedido**, excluído dos PDFs finais |
| Produtos conferidos nos documentos de origem | **126**, comparados às colunas de quantidade/preço e subtotais |
| PDF já organizado | **66 pares**, com **125 produtos** |
| Todos os arquivos juntos | **66 duplicidades bloqueadas**, mais um pedido sem etiqueta; nenhum par liberado automaticamente |
| Modo A — etiqueta + separação | **66 pedidos, 141 páginas**; nove páginas adicionais de separação para evitar cortes |
| Modo B — etiqueta + original | **66 pedidos, 132 páginas** |
| Tamanho das páginas | **100 × 150 mm** em todos os pedidos exportados |
| Destaques | Tamanho/variação e quantidade em **18 pt e negrito**; produto em **12 pt** |
| Originais | Hashes antes/depois idênticos; nenhum arquivo modificado |
| Imagens das etiquetas | Digests dos pixels originais e exportados idênticos |
| Associação e sequência | Conferida para **cada pedido**, em ambos os modos |
| Códigos de barras | **166 códigos por PDF final**, decodificados e iguais aos originais na referência de **600 dpi** |
| Rastreios a 203 dpi | Conferidos e lidos em **todas as 66 etiquetas** após exportação |

As imagens dos códigos originais são reutilizadas; o aplicativo não desenha novos códigos nem rasteriza as etiquetas. Textos de separação são vetoriais. Números de pedidos foram identificados em campos explícitos, nunca em CEP/CPF ou no nome dos arquivos.

Os PDFs reais expuseram variações que foram corrigidas e cobertas por regressões: marca Correios somente em imagem, destinatário Loggi com sobrenome quebrado em duas linhas, coluna `Nome`, e campos `Tamanho de calça`, `Calças`, `Tamanho de camisa/camiseta` e `Tamanho juvenil-infantil`.

## Limites da leitura óptica e verificações ainda pendentes

**Preservação do arquivo e aprovação física são verificações diferentes.** A comparação em 600 dpi confirmou todos os 166 códigos; todos os rastreios foram lidos a 203 dpi. Entretanto, a decodificação de alguns códigos varia conforme a resolução e a interpolação de imagens do PDF original. O relatório JSON registra os casos de diferença em 300 dpi e os códigos auxiliares não lidos em 203 dpi. Em particular, o rastreio do pedido **de um pedido não foi decodificado a 300 dpi** neste renderizador; foi lido a 203 e 600 dpi, com a imagem original preservada. Esse caso precisa de conferência no scanner físico. Não substituímos essa verificação por um resultado fictício nem afirmamos leitura universal em todas as resoluções.

Antes da expedição real, ainda é necessário:

1. Compilar e abrir o aplicativo no **Windows**. Script PowerShell e workflow manual de GitHub Actions foram preparados; nenhum `.exe` Windows foi gerado ou testado aqui.
2. Validar arraste pelo Explorer e abertura da prévia no Windows.
3. Imprimir uma amostra em tamanho real (100%) na térmica usada pela empresa e ler os rastreios e códigos auxiliares com o scanner utilizado na operação. Ajuste adicional do driver pode reduzir os códigos.
4. Conferir novos layouts de PDFs antes de tratá-los como suportados. PDFs sem texto não possuem OCR; ficam pendentes para revisão.

Os testes existentes reduziram os riscos observáveis; não constituem uma promessa de ausência absoluta de erros. Casos ambíguos, incompletos e duplicados ficam visíveis e bloqueados conforme as regras do lote.

## Repetição dos testes

Consulte `README.md`. Os testes sintéticos não dependem de dados reais. Para os sete exemplos, `scripts/validate_samples.py` recebe explicitamente os caminhos fornecidos e gera PDFs e `real-validation.json` em uma pasta nova. Nenhum PDF de cliente foi incluído no projeto ou no pacote de código-fonte.
