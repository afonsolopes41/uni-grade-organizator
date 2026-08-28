# Organizador de Notas

Junta pautas em **PDF**, **Excel**, **CSV** ou **TXT** — cada uma com o seu
formato — numa única listagem de alunos, ficando para cada um a **melhor nota
entre 1.ª época, 2.ª época e época especial**, com a **nota mínima de cada
cadeira**.

Corre como um programa local: abre um servidor em `127.0.0.1`, mostra tudo numa
página web e produz um ficheiro Excel formatado. **Nada sai do computador.**

```
pautas (PDF / XLSX / CSV / TXT)
        │
        ├─ leitura      cada formato tem o seu leitor
        ├─ detecção     que coluna é o quê, que UC, que época
        ├─ perguntas    o que não dá para deduzir é perguntado
        ├─ consolidação junta os alunos, escolhe a melhor nota
        │
        ├──▶ página web   procurar, filtrar, ver o detalhe
        └──▶ Excel        Resumo · uma folha por UC · Detalhe · Avisos
```

## Como usar

**Com o executável** (não precisa de Python):

1. Duplo clique em `OrganizadorDeNotas.exe` (Windows) ou `OrganizadorDeNotas`
   (macOS/Linux). Abre-se uma janela de consola e o navegador.
2. Arraste as pautas para a página.
3. Responda às confirmações que aparecerem (a opção já marcada é o palpite da
   aplicação — um clique confirma-a).
4. Veja as notas e carregue em **Descarregar Excel**.
5. Para fechar: `Ctrl+C` na janela de consola.

**A partir do código:**

```bash
pip install -r requirements.txt
python run.py                    # abre o navegador sozinho
python run.py --port 9000 --no-browser
```

## Construir o executável

```bash
python build_exe.py              # sai em dist/
```

O PyInstaller **não** faz compilação cruzada: para obter um `.exe` de Windows é
preciso construir no Windows. O fluxo `.github/workflows/build-exe.yml` constrói
os três (Windows, macOS, Linux) no GitHub Actions — dispare-o à mão em
*Actions → Construir executáveis → Run workflow*, ou empurre uma etiqueta `v*`.
Cada executável é arrancado no fim da construção para confirmar que responde.

## O que a aplicação percebe sozinha

Cada pauta vem com o formato de quem a fez. A detecção não assume nenhum: lê a
tabela, olha para os cabeçalhos **e** para os valores, e atribui um nível de
confiança a cada conclusão.

| O que descobre | Como |
|---|---|
| Onde começa a tabela | Pontua cada linha inicial: cabeçalhos ganham pontos, números perdem |
| Colunas de um PDF sem grelha | Reconstrói-as pelas posições das palavras — as colunas de um PDF estão alinhadas mesmo sem linhas desenhadas |
| Nome e número de aluno | Cabeçalho (`Nome`, `Nº Aluno`, `Número`…) e, se não bastar, a forma dos valores |
| Notas | Números, mas também `RE`, `NA`, `FA`, `Aprovado`, `-`, `13,25`, `13.25`, `85%`, `15/20` |
| Épocas | `2.ª Época`, `Recurso`, `1E`, `Época Especial`; e blocos de colunas seguidas |
| Momentos de avaliação | Se `Teste 2` é o 2.º teste da 1.ª época ou o recurso — decidido pelos dados (ver abaixo) |
| Nota final vs. componente | `Avaliação Final` > `Nota Final` > `Total`; `Projeto`, `Ex 4a`, `Participação` são componentes |
| Unidade curricular | Título do documento, nome da folha, sigla no nome do ficheiro |
| Data do documento | O rodapé `2026/06/25` decide qual versão de uma pauta é a boa |

Três regras que evitam os enganos mais comuns:

- **`Ex 2` não é a 2.ª época.** Um número no cabeçalho só indica um momento de
  avaliação se o resto do cabeçalho for de nota (`Nota Final 2`, `Teste 2`),
  nunca num exercício.
- **`Teste 2` também não é, por si só, a 2.ª época.** Ver a secção seguinte.
- **Se o ficheiro já diz a época, as colunas não a contradizem.** Numa pauta de
  1.ª época, `Exame 1` e `Exame 2` são duas provas dessa época, não duas épocas.

## Modalidades de avaliação

Em muitas cadeiras a 1.ª época faz-se por **dois testes ou frequências**. O 2.º
teste é **no mesmo dia do exame de 1.ª época**: quem correu mal no 1.º teste, ou
não o pôde fazer, vai a exame em vez de fazer o 2.º teste. São duas vias para a
mesma época, e cada aluno faz uma. Só quem chumba nessa época é que vai à **2.ª
época**, que é sempre exame — tal como a **época especial**.

Daqui vem a ambiguidade central de qualquer pauta: uma coluna `Teste 2` tanto
pode ser o 2.º teste da 1.ª época como o exame de recurso. **O cabeçalho não
chega para decidir, por isso decide-se pelos dados:**

| O que os dados mostram | Leitura |
|---|---|
| Só têm nota lá os alunos que não passaram no 1.º momento | Recurso → **2.ª época** |
| Tem nota lá a turma quase toda, aprovados incluídos | 2.º teste → **mesma época** |

A conclusão aparece sempre como pergunta, com a evidência à vista — *«12 de 58
alunos têm nota em Avaliação Final 2, e 11 desses não tinham passado no momento
anterior»* — e a resposta pré-seleccionada. Quem conhece a cadeira confirma ou
corrige num clique.

**Duas vias na mesma época** (avaliação contínua e exame) são reconhecidas pelo
preenchimento: colunas de nota final preenchidas para *alunos diferentes* são
vias alternativas e contam as duas — cada aluno fica com a da via que fez.
Colunas preenchidas para os *mesmos* alunos (`Nota Final` e `Avaliação Final`)
são a mesma nota escrita de duas maneiras, e só uma conta.

### Quando não dá para deduzir, pergunta

O que fica por decidir vira uma pergunta na página, com o palpite já marcado:

- **Este segundo momento é a mesma época ou o recurso?** — com a evidência dos
  dados. É a pergunta que mais muda o resultado.
- **Qual é a unidade curricular?** — quando o ficheiro não a identifica
  (`Notas_da_primeira_epoca.xlsx` não diz de que cadeira é).
- **A que época correspondem estas notas?** — com a saída «não é uma época, é só
  um componente».
- **Qual coluna é a nota final?** — quando há `Nota Final` *e* `Avaliação Final`.
  Só se pergunta quando as candidatas estão renhidas: entre `Nota Final` e
  `Nota Trabalho` não há dúvida nenhuma.
- **Que escala?** — se a nota mais alta for 10, tanto pode ser 0-20 como 0-10.

Em **Ajustes avançados** vê-se cada coluna de cada ficheiro, com o papel, a
época, o tipo, exemplos de valores e a confiança da detecção — e muda-se
qualquer uma à mão.

## Como escolhe a melhor nota

**Dentro de uma época**, se houver duas vias (contínua e exame), fica a que o
aluno fez — a melhor, nos casos raros em que tenha as duas.

**Entre épocas**:

1. Um valor numérico ganha sempre a um estado.
2. Entre estados: `Aprovado` > `Reprovado` > `Faltou` > `Desistiu` > `Não admitido`.
3. Empate numérico → fica a época mais cedo.

Quem só foi à 1.ª época fica com essa; quem foi à 2.ª fica com a melhor das
duas. `RE` na 1.ª e `14` na 2.ª dá **14**.

## Nota mínima por cadeira

A nota mínima para passar **depende de cada cadeira**. Na página há um campo por
UC, logo por baixo das estatísticas: mexer nele recalcula aprovações,
reprovações e as cores da tabela na hora. As UCs sem valor próprio usam o de
omissão (9,5), que se muda nos ajustes avançados.

No Excel, cada folha de UC tem a sua nota mínima numa célula amarela editável, e
o Resumo espelha-as todas. As colunas «Estado» e «Aprovadas» seguem a mínima da
UC respectiva, não um valor global.

## Como junta o mesmo aluno entre ficheiros

Duas linhas são a mesma pessoa se tiverem o **mesmo número** *ou* o **mesmo nome
normalizado** (sem acentos, sem maiúsculas, sem pontuação). Basta uma das duas,
o que resolve o caso real de um número mal escrito — `122651` e `1122651`
aparecem juntos, com um aviso a dizer que os números não batem certo.

Nomes muito parecidos que **não** foram juntos aparecem como sugestão, para
confirmação humana. A junção por nome pode ser desligada.

Quando dois ficheiros dão notas diferentes para o mesmo aluno, na mesma UC e na
mesma época:

- se **ambos** os documentos trazem data impressa, ganha o mais recente;
- caso contrário, ganha o ficheiro carregado por último.

Em qualquer dos casos fica registado um conflito, visível na página e na folha
**Avisos**, dizendo que valores havia e qual foi usado.

## O Excel

| Folha | O que traz |
|---|---|
| **Resumo** | Notas mínimas de todas as UCs, um aluno por linha, uma coluna por UC, média e nº de aprovações; gráfico da distribuição por escalão |
| **Uma por UC** | Nota mínima editável, as três épocas lado a lado, melhor nota, época da melhor, estado, origem, e os componentes (agrupados — dá para recolher) |
| **Detalhe** | Uma linha por nota e por componente, com o ficheiro de onde veio |
| **Avisos** | Conflitos e coisas a confirmar |

As células calculadas — melhor nota, arredondamento, estado, média, contagens,
distribuição — são **fórmulas**, não valores fixos: corrigir uma nota numa folha
de UC actualiza o resumo, e mudar a nota mínima de uma UC muda os estados dessa
UC e as contagens do resumo.

Só usa funções anteriores ao Excel 2007 (`INDEX`, `MATCH`, `COUNTIFS`,
`IFERROR`…), para abrir em qualquer versão e no LibreOffice.

Na página é possível seleccionar alunos (ou filtrar por UC) e exportar só esses.

## Estrutura

```
gradeorg/
  normalize.py     texto, nomes, números, notas e estados
  models.py        estruturas partilhadas
  parsers/
    pdf.py         pdfplumber + reconstrução de colunas por posição
    excel_in.py    openpyxl
    text.py        CSV, TSV e texto alinhado por espaços
  detect.py        cabeçalho, papéis das colunas, UC, época, perguntas
  consolidate.py   junção de alunos, conflitos, melhor nota
  excel.py         geração do livro formatado
  session.py       estado da sessão
  app.py           API JSON + página
  server.py        arranque e abertura do navegador
  web/             index.html · style.css · app.js
tests/             168 testes
```

## Testes

```bash
pip install pytest
python -m pytest tests -q
```

Cobrem a leitura de notas em todos os formatos encontrados, a detecção de
colunas e épocas (incluindo os casos que enganam), as modalidades de avaliação
(2.º teste contra recurso, duas vias na mesma época, nota mínima por cadeira), a
junção de alunos, a escolha da melhor nota, os conflitos entre versões, o Excel
gerado (valores, fórmulas e o conjunto de funções seguras) e o percurso completo
pela API.

## Formatos aceites

`.pdf` · `.xlsx` `.xlsm` `.xltx` · `.csv` `.tsv` · `.txt`

PDFs digitalizados (imagem, sem texto) não são lidos — precisam de OCR primeiro.
A aplicação diz isso em vez de devolver uma lista vazia.

## Privacidade

As pautas ficam num directório temporário durante a sessão e são apagadas ao
limpar. O servidor só aceita ligações de `127.0.0.1` e não faz pedidos para fora.
