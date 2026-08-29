# Organizador de Notas

Junta pautas em **PDF**, **Excel**, **CSV** ou **TXT** — cada uma com o seu
formato — numa única listagem de alunos, ficando para cada um a **melhor nota
entre 1.ª época, 2.ª época e época especial**, com a **nota mínima de cada
cadeira**.

Corre como um programa local: abre um servidor em `127.0.0.1`, mostra tudo numa
página web e produz um ficheiro Excel formatado. **Nada sai do computador.**
Fala **português de Portugal** e **inglês**, e **lembra-se de tudo** entre
arranques.

```
pautas (PDF / XLSX / CSV / TXT)
        │
        ├─ leitura      cada formato tem o seu leitor
        ├─ detecção     onde está a NOTA FINAL, que UC, que época
        ├─ perguntas    o que não dá para deduzir é perguntado
        ├─ consolidação junta os alunos, escolhe a melhor nota
        │
        ├──▶ página web   procurar, filtrar, ver o detalhe
        └──▶ Excel        Resumo · Médias · uma folha por UC · Detalhe · Avisos
```

**Só interessa a nota final.** As colunas de testes, laboratórios, trabalhos e
participação servem para perceber a estrutura da pauta — para saber qual é a
coluna da nota final e a que época pertence — mas não entram no resultado. Uma
pauta que não traga nota final nenhuma não conta, e a aplicação diz porquê em
vez de a deixar cair em silêncio.

**E a nota final é inteira.** Se a pauta trouxer décimas, arredonda-se: 13,4 fica
**13**, 13,5 fica **14**. É essa nota que aparece na listagem, que decide a
aprovação, que entra nas médias e que vai para o Excel; a da pauta continua à
vista na dica da célula e no detalhe do aluno.

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
| Onde começa a tabela | As linhas de alunos estão todas alinhadas pelo mesmo x; títulos e legendas não |
| Colunas de um PDF | Tenta a grelha desenhada **e** a reconstrução por posições, e fica com a que produzir a tabela mais cheia |
| Cabeçalhos em várias linhas | `Test 1` numa linha e `30%` na de baixo são o mesmo cabeçalho |
| Nome e número de aluno | Cabeçalho (`Nome`, `Nº Aluno`, `Number`, `Name`…) e, se não bastar, a forma dos valores |
| Número e nome na mesma coluna | `122631 Ana Silva`, `Ana Silva - 122631`, `nº 122631/Ana Silva`: a coluna passa a ser o nome e o número sai de lá para fora |
| Número e nome colados num PDF | Quando estão a quatro pontos um do outro — menos do que separa duas colunas — separam-se na mesma: à esquerda números de aluno, à direita nomes (ver abaixo) |
| A via do exame | Uma coluna `Exame` preenchida **só** para quem tem a `Nota final` vazia é a outra via da mesma época, não um componente |
| Notas | Números, mas também `RE`, `NA`, `FA`, `f`, `m`, `d`, `RE m`, `Aprovado`, `-`, `13,25`, `13.25`, `85%`, `15/20` |
| Épocas | `2.ª Época`, `Recurso`, `1E`, `Época Especial`; e blocos de colunas seguidas |
| Momentos de avaliação | Se `Teste 2` é o 2.º teste da 1.ª época ou o recurso — decidido pelos dados (ver abaixo) |
| Qual é a nota final | `Avaliação Final` > `Nota Final` > `Total`; `Projeto`, `Ex 4a`, `Participação` ficam de fora |
| Unidade curricular | Pontua todos os pedaços do cabeçalho da página e fica com o melhor — a instituição, a legenda dos símbolos e as datas de revisão de nota ficam de fora |
| Código da cadeira | `03713 - SGR - Segurança e Gestão de Redes` — é o que junta a mesma cadeira em pautas de línguas diferentes |
| Semestre | `2º Semestre`, `2nd Semester`, `Semestre 2` |
| Pautas de um componente só | `Teste 1 (30%)` no título: a coluna «Nota» é a nota *desse teste*, não a da cadeira |
| Pautas em inglês | `Number`, `Name`, `Date`, `Grade`, `Test 1`, `Max1`, `1st Season`, `2nd Season`, `resit` |
| Data do documento | O rodapé `2026/06/25` decide qual versão de uma pauta é a boa |

Três regras que evitam os enganos mais comuns:

- **`Ex 2` não é a 2.ª época.** Um número no cabeçalho só indica um momento de
  avaliação se o resto do cabeçalho for de nota (`Nota Final 2`, `Teste 2`),
  nunca num exercício.
- **`Teste 2` também não é, por si só, a 2.ª época.** Ver a secção seguinte.
- **Se o ficheiro já diz a época, as colunas não a contradizem.** Numa pauta de
  1.ª época, `Exame 1` e `Exame 2` são duas provas dessa época, não duas épocas.

### Colunas que se partem sozinhas

Numa coluna com valores alinhados à direita, um `f` estreito e um `10.0` largo
não chegam a sobrepor-se em x, e a coluna parte-se em duas — metade dos alunos
numa, metade na outra. São precisos dois sinais para desfazer a separação: uma
palavra do cabeçalho (`Test`) passa por cima das duas metades, **e** quase
nenhum aluno tem valor nas duas ao mesmo tempo.

O segundo sinal é o que impede juntar colunas a sério: `Nota Final` e
`Avaliação Final` estão ambas preenchidas na mesma linha, por isso ficam
separadas mesmo com uma palavra larga do cabeçalho por cima. E o «quase» abre
espaço para notas compostas como `RE m`, que ocupam a coluna e um bocadinho da
seguinte, mas só em meia dúzia de linhas.

A palavra do cabeçalho tem ainda de **chegar aos valores das duas metades**.
Cruzar o vazio entre elas não basta: numa pauta com `… Nota final | Exame`, a
etiqueta «Exame» começa muito à esquerda dos seus próprios números e passa por
cima do vazio que a separa da coluna anterior — mas nem toca nos valores dela, e
por isso não as junta.

### Colunas que se colam sozinhas

O inverso acontece quando o número de aluno fica a quatro pontos do nome: menos
do que separa duas colunas, e a reconstrução junta-os. Aqui há um sinal mais
forte do que a distância — à esquerda estão números de aluno, à direita nomes de
pessoa, e o corte é sempre no mesmo sítio. Confirmado em três quartos das linhas,
faz-se o corte.

### Etiquetas longe dos seus valores

Numa coluna de números alinhados à direita, a etiqueta do cabeçalho começa muito
antes deles: «Teste intercalar» arranca 60 pontos à esquerda dos `10,25` que
encima. Por isso as etiquetas não se distribuem pelos limites das colunas mas
pela **sobreposição com os valores** de cada uma, e só quando não há sobreposição
nenhuma é que vale a proximidade. Uma etiqueta de uma coluna que não tem uma
única nota — «Exame recurso», numa pauta onde ninguém foi a recurso — fica de
fora em vez de ir roubar o nome à coluna do lado.

## A mesma cadeira com dois nomes

A pauta do teste vem em português e a da época em inglês. «Segurança e Gestão de
Redes» e «Network Security and Management» não se parecem em nada — mas as duas
trazem o código `03713`, e é por aí que se juntam.

Quando duas pautas do mesmo código lhe dão nomes diferentes, a aplicação
pergunta qual usar, com a opção de dizer que afinal **são cadeiras diferentes**.
Sem código, a junção é pelo nome normalizado, como sempre foi.

## Pautas que são só um componente

Uma pauta intitulada `Teste 1 (30%)` tem uma coluna «Nota» que é a nota *desse
teste*, não a nota final da cadeira. Tratá-la como nota final punha-a a competir
com a pauta da época — e, sendo a mais recente, ganhava a errada.

O peso no título (`30%`) é o sinal: abaixo de 100%, a pauta é de um componente.
A coluna passa a chamar-se `Teste 1 (30%)`, a pauta fica **sem nota final** e,
como só a nota final conta, não entra no resultado. Fica um aviso a dizer
exactamente isso — e, se for mesmo para usar, marca-se a coluna como nota final
nos ajustes avançados.

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

O mesmo preenchimento promove a coluna do **exame**: numa pauta
`Teste intercalar | 2.º teste | Labs | Nota final | Exame`, a coluna `Exame`
tem nota exactamente para quem tem a `Nota final` vazia. Não é um componente —
é a outra via, e sem isso quem foi a exame ficava sem nota nenhuma. Um `Exame 1`
que toda a gente tem, ao lado de uma `Nota Final` que toda a gente também tem,
continua a ser um componente dela.

### Quando não dá para deduzir, pergunta

O que fica por decidir vira uma pergunta na página, com o palpite já marcado:

- **Este segundo momento é a mesma época ou o recurso?** — com a evidência dos
  dados. É a pergunta que mais muda o resultado.
- **Estas duas pautas são a mesma cadeira?** — quando partilham o código mas
  dão-lhe nomes diferentes.
- **Qual é a unidade curricular?** — quando o ficheiro não a identifica
  (`Notas_da_primeira_epoca.xlsx` não diz de que cadeira é).
- **A que época correspondem estas notas?** — com a saída «não é uma época, é só
  um componente».
- **Qual coluna é a nota final?** — quando há `Nota Final` *e* `Avaliação Final`.
  Só se pergunta quando as candidatas estão renhidas: entre `Nota Final` e
  `Nota Trabalho` não há dúvida nenhuma.
- **Que escala?** — se a nota mais alta for 10, tanto pode ser 0-20 como 0-10.

Cada pergunta tem um botão **Abrir o documento**: a pauta abre num separador ao
lado, para se poder responder a olhar para ela em vez de a ir procurar.

Em **Ajustes avançados** vê-se cada coluna de cada ficheiro — se é o nome, o
número, a **nota final** ou nada disso, a época, exemplos de valores e a
confiança da detecção — e muda-se qualquer uma à mão. Como só a nota final
conta, não há mais nada para escolher.

Conferida uma pauta, o botão **✓ Confirmado** arruma-a: sai da lista e fica
contada numa linha discreta («3 pautas já conferidas — mostrar»). Com uma dúzia
de ficheiros carregados, é a diferença entre uma lista utilizável e uma parede
de tabelas. Voltar a abrir é um clique.

## Como escolhe a melhor nota

**Dentro de uma época**, se houver duas vias (contínua e exame), fica a que o
aluno fez — a melhor, nos casos raros em que tenha as duas.

**Entre épocas**:

1. Um valor numérico ganha sempre a um estado.
2. Entre estados: `Aprovado` > `Reprovado` > `Faltou` > `Desistiu` > `Não admitido`.
3. Empate numérico → fica a época mais cedo.

Quem só foi à 1.ª época fica com essa; quem foi à 2.ª fica com a melhor das
duas. `RE` na 1.ª e `14` na 2.ª dá **14**.

## Gerir as unidades curriculares

A tabela **Unidades curriculares** é o painel de controlo das cadeiras:

- **Criar uma cadeira à mão** (**+ Nova cadeira**), mesmo antes de ter pautas
  dela. Fica na lista com «sem pautas ainda», já a contar para o plano de
  estudos, e recebe as pautas quando elas chegarem.
- **Apontar um ficheiro a uma cadeira**: no passo *Ficheiros*, cada pauta tem um
  selector de cadeira. Escolhida uma, todas as tabelas desse ficheiro passam a
  ser dela; em branco, volta a valer o que a detecção diz.
- **Mudar o nome** a qualquer momento — escreve-se por cima e carrega-se Enter.
  O nome novo leva consigo a nota mínima, o ano, o semestre e os ECTS, e fica
  guardado; nenhuma pauta precisa de ter esse nome escrito.
- **Apagar** uma cadeira (✕). Sai das notas, das médias e do Excel, mas o
  ficheiro fica: aparece na linha «Apagadas», com **repor** ao lado.
- **Ver de que ficheiro vem** cada cadeira — a coluna «Ficheiros» mostra todas
  as pautas que lhe deram origem (a do teste e a da época, a versão portuguesa e
  a inglesa).

## Cadeiras de um curso e cadeiras comuns

Há cadeiras que são de vários cursos e cadeiras que são só de um. Quem é de
outro curso nunca vai ter nota nas segundas — e **isso não é uma falha dele**.

O campo **Curso** de cada UC resolve isto. Em branco, a cadeira é comum a vários
cursos; preenchido (`LEI`, `IGE`…), é exclusiva desse curso. A partir daí:

- o **curso de cada aluno** deduz-se das cadeiras exclusivas em que tem nota;
- o **plano dele** são as comuns mais as do curso dele;
- a **cobertura** aparece no detalhe: *«Tem nota em 8 das 11 cadeiras do plano»*,
  com a lista do que falta.

Quem não tem nenhuma cadeira exclusiva fica com o plano das comuns e não é
penalizado pelas que nunca podia ter feito. Se nenhum curso estiver preenchido,
o plano é simplesmente o conjunto de todas as cadeiras carregadas.

## Idioma

O botão **PT / EN** no topo troca a língua de tudo o que se lê: a página, as
perguntas, as razões da detecção, os avisos, os conflitos, os estados das notas
(`Reprovado` / `Failed`), os nomes das épocas (`2.ª Época` / `2nd Season`) e
**também o Excel** — folhas, cabeçalhos e textos. A escolha fica guardada.

## Memória

A aplicação lembra-se do que se estava a fazer. Fecha-se e volta a abrir-se com
tudo como ficou: os ficheiros carregados, as respostas às perguntas, os ajustes
de colunas, os nomes das cadeiras, o plano de estudos, as notas mínimas e a
língua.

Fica tudo numa pasta do utilizador — `%APPDATA%\OrganizadorDeNotas` no Windows,
`~/Library/Application Support/OrganizadorDeNotas` no macOS,
`~/.local/share/organizador-de-notas` no Linux:

```
sessao.json   respostas, definições e lista de ficheiros
ficheiros/    cópia das pautas carregadas
tabelas/      as tabelas já extraídas, para o arranque ser imediato
```

Só o botão **Apagar tudo** limpa (com confirmação). Se o estado guardado estiver
estragado, a aplicação arranca vazia em vez de rebentar.

## Semestres, anos e médias

Na página, a tabela **Unidades curriculares** pede o **ano** e o **semestre** de
cada cadeira, e opcionalmente os **ECTS**. O semestre vem já preenchido quando a
pauta o diz — só é preciso escrever o que falta.

Com isso saem, por aluno:

- a **média de cada semestre**,
- a **média de cada ano**,
- a **média final de curso**, com o arredondamento.

Contam as cadeiras **aprovadas** com nota numérica — é o que vai para o diploma.
Se os ECTS estiverem preenchidos em todas, as médias são **ponderadas por eles**;
se faltar algum, é a média simples, e a página diz qual foi usada. Uma cadeira
sem ano ou semestre entra na média final mas fica de fora das parciais, e é
listada para se saber porquê.

No Excel isto é a folha **Médias**, e é toda em fórmulas: cada cadeira tem duas
colunas de apoio — quanto contribui e quanto pesa — e as médias são a divisão de
uma soma pela outra. Corrigir uma nota na folha da UC atravessa o Resumo e chega
às médias.

Na listagem, as cadeiras aparecem **agrupadas por ano e semestre**, com uma
faixa por cima de cada grupo, e por **ordem alfabética dentro de cada um** (com
os acentos onde devem estar: «Álgebra» antes de «Análise»). As que ainda não têm
ano nem semestre ficam num grupo à parte, no fim. O Excel segue a mesma ordem e
escreve o ano e o semestre por baixo do nome de cada UC no Resumo.

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
| **Resumo** | Notas mínimas de todas as UCs, um aluno por linha, uma coluna por UC (com o ano e o semestre por baixo do nome), média e nº de aprovações; gráfico da distribuição por escalão |
| **Médias** | Médias por semestre, por ano e de curso, com as colunas de apoio agrupadas (podem ser recolhidas) |
| **Uma por UC** | Nota mínima editável, as três épocas lado a lado, melhor nota, época da melhor, estado e origem; o subtítulo diz de que ficheiros veio |
| **Detalhe** | Uma linha por nota, com o ficheiro de onde veio |
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
  consolidate.py   junção de alunos, conflitos, melhor nota, médias
  excel.py         geração do livro formatado
  i18n.py          textos em português e inglês (servidor e Excel)
  storage.py       memória em disco entre arranques
  session.py       estado da sessão
  app.py           API JSON + página
  server.py        arranque e abertura do navegador
  web/             index.html · style.css · app.js · i18n.js
tests/             300 testes
```

## Testes

```bash
pip install pytest
python -m pytest tests -q
```

Cobrem a reconstrução de colunas a partir das posições das palavras (com
geometria fabricada, sem depender de nenhum PDF em disco), a leitura de notas em
todos os formatos encontrados, as pautas em inglês, a detecção de colunas e
épocas (incluindo os casos que enganam), as modalidades de avaliação
(2.º teste contra recurso, duas vias na mesma época, pautas de um componente só,
nota mínima por cadeira), a identidade das cadeiras pelo código, as médias por
semestre, ano e curso, a gestão das cadeiras (criar, mudar o nome, apagar,
repor, apontar ficheiros, origem), as cadeiras de um curso contra as comuns, o
arredondamento da nota final, a ordem por ano e semestre, o número e o nome na
mesma coluna em dez formatos diferentes, a memória entre arranques, as duas
línguas (incluindo a garantia de que nenhuma chave fica por traduzir), a via do
exame reconhecida pelo preenchimento, a junção de alunos, a escolha da melhor
nota, os conflitos entre versões, o Excel gerado (valores, fórmulas e o conjunto
de funções seguras) e o percurso completo pela API.

## Formatos aceites

`.pdf` · `.xlsx` `.xlsm` `.xltx` · `.csv` `.tsv` · `.txt`

PDFs digitalizados (imagem, sem texto) não são lidos — precisam de OCR primeiro.
A aplicação diz isso em vez de devolver uma lista vazia.

## Privacidade

As pautas ficam guardadas **no computador de quem as carrega** (ver
*[Memória](#memória)*), para a aplicação poder continuar de onde ficou, e
desaparecem com **Apagar tudo**. O servidor só aceita ligações de `127.0.0.1` e
não faz pedidos para fora — nem para fontes, nem para nada.
