"""Traducoes.

A aplicacao fala portugues de Portugal e ingles. A lingua e uma definicao da
sessao, por isso tudo o que o servidor manda para a interface -- perguntas,
avisos, razoes da deteccao -- tem de poder sair nas duas.

Para isso as mensagens nao sao escritas como texto: sao um :class:`Msg`, ou
seja uma chave mais os parametros. So a interface (ou o Excel) e que decide a
lingua, no momento de serializar. ``Msg`` comporta-se como a string portuguesa
quando alguem a usa directamente, para nao obrigar a mudar tudo o que ja existe.
"""

from __future__ import annotations

DEFAULT_LANGUAGE = "pt"
LANGUAGES = ("pt", "en")

LANGUAGE_NAMES = {"pt": "Português", "en": "English"}


def normalize_language(value) -> str:
    """Aceita ``pt``, ``pt-PT``, ``en_GB``... e devolve ``pt`` ou ``en``."""
    text = str(value or "").strip().lower().replace("_", "-")
    if not text:
        return DEFAULT_LANGUAGE
    base = text.split("-")[0]
    return base if base in LANGUAGES else DEFAULT_LANGUAGE


CATALOG = {
    "pt": {
        # -- epocas e vias ------------------------------------------------
        "epoca.epoca1": "1.ª Época",
        "epoca.epoca2": "2.ª Época",
        "epoca.especial": "Época Especial",
        "epoca.unknown": "época desconhecida",
        "epoca.short.epoca1": "1.ª",
        "epoca.short.epoca2": "2.ª",
        "epoca.short.especial": "esp.",
        "route.continua": "Avaliação contínua",
        "route.exame": "Exame",

        # -- onde foi encontrado ------------------------------------------
        "text.two_sentences": "{first} {second}",
        "status.APROVADO": "Aprovado",
        "status.REPROVADO": "Reprovado",
        "status.FALTOU": "Faltou",
        "status.DESISTIU": "Desistiu",
        "status.NAO_ADMITIDO": "Não admitido",
        "status.SEM_NOTA": "—",
        "location.page": "página {n}",
        "location.pages": "páginas {n}",
        "location.sheet": "folha «{name}»",
        "location.text": "texto",
        "where.filename": "nome do ficheiro",
        "where.sheet": "nome da folha",
        "where.title": "título do documento",

        # -- razoes da classificacao das colunas --------------------------
        "reason.empty_column": "coluna vazia",
        "reason.header_not_grade": "cabeçalho «{header}» não é uma nota",
        "reason.header_name": "cabeçalho indica nome",
        "reason.id_and_name": "o número e o nome vêm na mesma coluna",
        "reason.header_id": "cabeçalho indica número de aluno",
        "reason.values_names": "os valores parecem nomes de pessoas",
        "reason.values_ids": "os valores parecem números de aluno",
        "reason.not_recognised": "não parece nome, número nem nota",
        "reason.epoca_grade": "«{header}» é a nota da época",
        "reason.header_final": "cabeçalho «{header}» indica nota final",
        "reason.header_component": "cabeçalho «{header}» indica componente",
        "reason.other_name_column": "outra coluna foi escolhida como nome",
        "reason.name_by_text": "coluna com mais texto parecido com nomes",
        "reason.other_id_column": "outra coluna foi escolhida como número de aluno",
        "reason.shared_component": "componente comum a todas as épocas",
        "reason.exam_route":
            "coluna do exame, preenchida só para quem não tem nota final",
        "reason.last_of_block": "última coluna do bloco (palpite)",
        "reason.other_final_chosen": "«{header}» foi escolhida como nota final",
        "reason.alt_route": "{reason} (via alternativa desta época)",
        "reason.component_pauta": "a pauta é de «{label}» ({weight}%), não da nota final",
        "reason.user_component": "marcado como componente pelo utilizador",
        "reason.user_epoca": "época definida pelo utilizador",
        "reason.user_moment": "momento definido pelo utilizador",
        "reason.user_final": "nota final definida pelo utilizador",
        "reason.user_defined": "definido pelo utilizador",

        # -- palpites ------------------------------------------------------
        "guess.code_in_document": "código no documento: «{text}»",
        "guess.acronym_in_document": "sigla no documento: «{text}»",
        "guess.acronym_in_filename": "sigla no nome do ficheiro: «{text}»",
        "guess.document_header": "cabeçalho do documento: «{text}»",
        "guess.document_title": "título do documento: «{text}»",
        "guess.sheet_name": "nome da folha: «{text}»",
        "guess.document_text": "texto do documento: «{text}»",
        "guess.filename": "nome do ficheiro: «{text}»",
        "guess.subject_unknown": "não foi possível identificar a UC",
        "guess.found_in": "encontrado em «{text}»",
        "guess.epoca_found": "{where}: «{text}»",
        "guess.user_defined": "definido pelo utilizador",

        # -- notas sobre a fonte -------------------------------------------
        "note.epoca_from_file": "Época sugerida pelo ficheiro: {reason}",
        "note.component_pauta":
            "Esta pauta é só «{label}» ({weight}% da nota), por isso não traz "
            "nota final. Só entra nas notas se marcar uma coluna como nota final.",

        # -- o que os dados dizem sobre um 2.º momento ----------------------
        "evidence.nobody":
            "Ninguém tem nota em «{header}» — não dá para perceber pelos dados "
            "o que esta coluna é.",
        "evidence.counts": "{filled} de {total} alunos têm nota em «{header}».",
        "evidence.counts_with_first":
            "{filled} de {total} alunos têm nota em «{header}», e {failed} desses "
            "não tinham passado no momento anterior.",
        "evidence.only_failed": "Só lá vão os que chumbaram: parece 2.ª época.",
        "evidence.almost_all":
            "Vai lá a turma quase toda: parece o 2.º teste da mesma época.",
        "evidence.most_failed": "A maioria tinha chumbado: parece 2.ª época.",
        "evidence.inconclusive": "Os dados não são conclusivos.",

        # -- perguntas ------------------------------------------------------
        "question.subject.title": "Qual é a unidade curricular de «{label}»?",
        "question.subject.detail": "Não há nada no ficheiro que identifique a UC.",
        "question.final.title": "Qual é a coluna com a nota final em «{label}»?",
        "question.final.detail":
            "Nenhuma coluna se identificou claramente como nota final.",
        "question.final_epoca.title":
            "Em «{label}», qual coluna conta como nota final da {epoca}?",
        "question.final_epoca.title_plain":
            "Em «{label}», qual coluna conta como nota final?",
        "question.final_epoca.detail": "Há mais do que uma coluna com ar de nota final.",
        "question.epoca.title": "A que época correspondem as notas de «{label}»?",
        "question.epoca.detail": "Colunas sem época identificada: {columns}",
        "question.epoca.option_ignore": "Não é uma época — não usar esta coluna",
        "question.epoca.hint_ignore": "A coluna deixa de contar para as notas.",
        "question.scale.title": "«{header}» em «{label}» está em que escala?",
        "question.scale.detail":
            "O valor mais alto é {max}, o que tanto pode ser uma escala 0-20 "
            "como 0-10.",
        "question.moment.title":
            "Em «{label}», {headers} é um segundo momento de avaliação. É o "
            "{moment}.º teste da mesma época ou é outra época?",
        "question.moment.detail":
            "{evidence} O {moment}.º teste conta para a mesma época; um exame de "
            "recurso é a época seguinte.",
        "question.moment.same": "{moment}.º teste da {epoca}",
        "question.moment.same_hint": "avaliação contínua — faz-se no mesmo dia do exame",
        "question.moment.other": "{epoca} (exame)",
        "question.moment.other_hint": "quem chumbou na época anterior vai a este exame",
        "question.merge.title": "{names} são a mesma cadeira?",
        "question.merge.detail_code":
            "Têm o mesmo código ({code}) mas as pautas dão-lhes nomes diferentes: "
            "{files}.",
        "question.merge.detail_similar":
            "Parecem a mesma cadeira mas as pautas dão-lhes nomes diferentes: {files}.",
        "question.merge.yes": "Sim — usar «{name}»",
        "question.merge.split": "Não, são cadeiras diferentes",
        "question.merge.split_hint": "cada pauta fica com o seu nome",

        # -- avisos e conflitos ---------------------------------------------
        "conflict.type.numero": "número",
        "conflict.type.nota": "nota",
        "conflict.type.linha_repetida": "linha repetida",
        "warning.type.nome": "nome",
        "warning.type.possivel_duplicado": "possível duplicado",
        "warning.type.cadeiras_juntadas": "cadeiras juntadas",
        "warning.type.pauta_sem_nota_final": "pauta sem nota final",
        "warning.type.plano_incompleto": "plano incompleto",
        "conflict.numero.detail":
            "O mesmo aluno aparece com números diferentes: {ids}.",
        "warning.nome.detail":
            "Nome escrito de maneiras diferentes: {names}. Usado: «{chosen}».",
        "conflict.repeated_row.detail":
            "O aluno aparece mais do que uma vez em «{column}» ({source}) com "
            "valores diferentes: {values}",
        "conflict.grade.detail": "Valores diferentes em ficheiros diferentes: {values}",
        "conflict.grade.chosen": "{value} ({source}) — {reason}",
        "reason.newest_document": "documento mais recente",
        "reason.latest_file": "ficheiro carregado mais tarde",
        "warning.similar_names.detail":
            "«{left}» e «{right}» têm nomes muito parecidos (semelhança "
            "{similarity}) mas ficaram como alunos diferentes. Confirme se é a "
            "mesma pessoa.",
        "warning.merged.detail_code":
            "As pautas {files} têm o mesmo código ({code}) mas dão-lhe nomes "
            "diferentes: {names}. Foram tratadas como uma só, com o nome «{chosen}».",
        "warning.merged.detail_similar":
            "As pautas {files} parecem ser da mesma cadeira mas dão-lhe nomes "
            "diferentes: {names}. Foram tratadas como uma só, com o nome «{chosen}».",
        "warning.no_final.detail":
            "«{label}» não tem nenhuma coluna marcada como nota final, por isso "
            "não entra nas notas. {why}Se quiser usá-la, abra os ajustes avançados "
            "e marque a coluna certa como nota final.",
        "warning.no_final.component": "A pauta é só de «{label}» ({weight}%). ",
        "warning.coverage.detail":
            "Tem nota em {have} das {total} cadeiras do plano. As médias são só "
            "sobre o que existe — faltam: {missing}.",

        # -- Excel -----------------------------------------------------------
        "api.no_files": "Não veio nenhum ficheiro.",
        "api.unsupported_format":
            "Formato «{ext}» não suportado. Aceita PDF, XLSX, CSV e TXT.",
        "api.read_failed": "Não foi possível ler o ficheiro: {error}",
        "api.no_table":
            "Não foi encontrada nenhuma tabela de notas em «{name}». Se for um PDF "
            "digitalizado (imagem), tem de passar por OCR primeiro.",
        "api.nothing_loaded": "Ainda não foi carregado nenhum ficheiro.",
        "api.too_large": "Ficheiro demasiado grande (limite de 64 MB).",
        "api.internal_error": "Erro interno: {error}",
        "api.unknown_action": "Acção desconhecida: «{action}».",
        "xl.sheet.summary": "Resumo",
        "xl.sheet.averages": "Médias",
        "xl.sheet.detail": "Detalhe",
        "xl.sheet.notices": "Avisos",
        "xl.summary.title": "Notas consolidadas — resumo por aluno",
        "xl.summary.subtitle": "Gerado em {stamp} · Ficheiros: {files}",
        "xl.summary.pass_row": "Nota mínima por cadeira",
        "xl.summary.uc_average": "Média da UC",
        "xl.summary.uc_approved": "Aprovados",
        "xl.summary.pass_hint": "editam-se na folha de cada UC (célula amarela)",
        "xl.col.student_id": "Nº Aluno",
        "xl.col.name": "Nome",
        "xl.col.average": "Média",
        "xl.col.approved": "Aprovadas",
        "xl.col.subjects": "UCs",
        "xl.col.best": "Melhor Nota",
        "xl.col.final": "Nota Final",
        "xl.col.best_epoca": "Época da melhor",
        "xl.col.state": "Estado",
        "xl.col.best_source": "Origem da melhor nota",
        "xl.col.subject": "Unidade Curricular",
        "xl.col.epoca": "Época",
        "xl.col.kind": "Tipo",
        "xl.col.item": "Item",
        "xl.col.value": "Valor",
        "xl.col.source": "Origem",
        "xl.col.severity": "Gravidade",
        "xl.col.type": "Tipo",
        "xl.col.description": "Descrição",
        "xl.col.chosen": "Valor escolhido",
        "xl.col.band": "Escalão",
        "xl.col.rounded": "Arredondada",
        "xl.col.ects": "ECTS",
        "xl.col.course": "Curso",
        "xl.col.files": "Ficheiros",
        "xl.distribution.title": "Distribuição das melhores notas",
        "xl.distribution.chart": "Melhores notas por escalão",
        "xl.distribution.students": "Alunos",
        "xl.subject.pass_mark": "Nota mínima de aprovação",
        "xl.subject.pass_hint": "↖ editável — a coluna «Estado» recalcula.",
        "xl.subject.sources": "Ficheiros: {files}",
        "xl.subject.subtitle": "{count} aluno(s) · melhor de 1.ª, 2.ª e época especial · gerado em {stamp}",
        "xl.state.approved": "Aprovado",
        "xl.state.failed": "Reprovado",
        "xl.state.pending": "—",
        "xl.averages.title": "Médias por semestre, por ano e de curso",
        "xl.averages.subtitle":
            "Contam as cadeiras aprovadas · os ECTS em branco valem 1 · gerado em {stamp}",
        "xl.averages.semester": "{year}.º ano · {semester}.º sem.",
        "group.year": "{year}.º ano",
        "group.semester": "{semester}.º semestre",
        "group.none": "Sem ano nem semestre",
        "xl.averages.year": "Média do {year}.º ano",
        "xl.averages.final": "Média de curso",
        "xl.detail.title": "Detalhe de todas as notas",
        "xl.detail.subtitle": "Uma linha por nota, com a origem · gerado em {stamp}",
        "xl.detail.final": "Nota final",
        "xl.notices.title": "Avisos e conflitos",
        "xl.notices.subtitle": "{count} pontos a confirmar · gerado em {stamp}",
        "xl.notices.none": "Sem conflitos: todos os ficheiros foram lidos sem ambiguidades.",
        "xl.notices.conflict": "Conflito",
        "xl.notices.info": "Informação",
    },

    "en": {
        "epoca.epoca1": "1st Season",
        "epoca.epoca2": "2nd Season",
        "epoca.especial": "Special Season",
        "epoca.unknown": "unknown season",
        "epoca.short.epoca1": "1st",
        "epoca.short.epoca2": "2nd",
        "epoca.short.especial": "spec.",
        "route.continua": "Continuous assessment",
        "route.exame": "Exam",

        "text.two_sentences": "{first} {second}",
        "status.APROVADO": "Passed",
        "status.REPROVADO": "Failed",
        "status.FALTOU": "Absent",
        "status.DESISTIU": "Withdrew",
        "status.NAO_ADMITIDO": "Not admitted",
        "status.SEM_NOTA": "—",
        "location.page": "page {n}",
        "location.pages": "pages {n}",
        "location.sheet": "sheet «{name}»",
        "location.text": "text",
        "where.filename": "file name",
        "where.sheet": "sheet name",
        "where.title": "document title",

        "reason.empty_column": "empty column",
        "reason.header_not_grade": "heading «{header}» is not a grade",
        "reason.header_name": "heading says it is a name",
        "reason.id_and_name": "the number and the name share one column",
        "reason.header_id": "heading says it is a student number",
        "reason.values_names": "the values look like people's names",
        "reason.values_ids": "the values look like student numbers",
        "reason.not_recognised": "does not look like a name, a number or a grade",
        "reason.epoca_grade": "«{header}» is the grade for this season",
        "reason.header_final": "heading «{header}» says it is the final grade",
        "reason.header_component": "heading «{header}» says it is a component",
        "reason.other_name_column": "another column was picked as the name",
        "reason.name_by_text": "the column with the most name-like text",
        "reason.other_id_column": "another column was picked as the student number",
        "reason.shared_component": "component shared by every season",
        "reason.exam_route":
            "the exam column, filled only for those with no final grade",
        "reason.last_of_block": "last column of the block (a guess)",
        "reason.other_final_chosen": "«{header}» was picked as the final grade",
        "reason.alt_route": "{reason} (alternative route for this season)",
        "reason.component_pauta":
            "this sheet is about «{label}» ({weight}%), not the final grade",
        "reason.user_component": "marked as a component by you",
        "reason.user_epoca": "season set by you",
        "reason.user_moment": "assessment moment set by you",
        "reason.user_final": "final grade set by you",
        "reason.user_defined": "set by you",

        "guess.code_in_document": "course code in the document: «{text}»",
        "guess.acronym_in_document": "acronym in the document: «{text}»",
        "guess.acronym_in_filename": "acronym in the file name: «{text}»",
        "guess.document_header": "document heading: «{text}»",
        "guess.document_title": "document title: «{text}»",
        "guess.sheet_name": "sheet name: «{text}»",
        "guess.document_text": "text in the document: «{text}»",
        "guess.filename": "file name: «{text}»",
        "guess.subject_unknown": "the course could not be identified",
        "guess.found_in": "found in «{text}»",
        "guess.epoca_found": "{where}: «{text}»",
        "guess.user_defined": "set by you",

        "note.epoca_from_file": "Season suggested by the file: {reason}",
        "note.component_pauta":
            "This sheet only covers «{label}» ({weight}% of the grade), so it "
            "carries no final grade. It only counts if you mark a column as the "
            "final grade.",

        "evidence.nobody":
            "Nobody has a grade in «{header}» — the data cannot tell us what this "
            "column is.",
        "evidence.counts": "{filled} of {total} students have a grade in «{header}».",
        "evidence.counts_with_first":
            "{filled} of {total} students have a grade in «{header}», and {failed} "
            "of those had not passed the earlier moment.",
        "evidence.only_failed":
            "Only the students who failed are there: looks like a resit.",
        "evidence.almost_all":
            "Almost the whole class is there: looks like the 2nd test of the same season.",
        "evidence.most_failed": "Most of them had failed: looks like a resit.",
        "evidence.inconclusive": "The data is not conclusive.",

        "question.subject.title": "Which course does «{label}» belong to?",
        "question.subject.detail": "Nothing in the file identifies the course.",
        "question.final.title": "Which column holds the final grade in «{label}»?",
        "question.final.detail": "No column clearly looked like a final grade.",
        "question.final_epoca.title":
            "In «{label}», which column counts as the final grade for the {epoca}?",
        "question.final_epoca.title_plain":
            "In «{label}», which column counts as the final grade?",
        "question.final_epoca.detail": "More than one column looks like a final grade.",
        "question.epoca.title": "Which season do the grades in «{label}» belong to?",
        "question.epoca.detail": "Columns with no season identified: {columns}",
        "question.epoca.option_ignore": "It is not a season — do not use this column",
        "question.epoca.hint_ignore": "The column stops counting towards the grades.",
        "question.scale.title": "Which scale is «{header}» in «{label}» using?",
        "question.scale.detail":
            "The highest value is {max}, which fits both a 0-20 and a 0-10 scale.",
        "question.moment.title":
            "In «{label}», {headers} is a second assessment moment. Is it test "
            "number {moment} of the same season, or another season?",
        "question.moment.detail":
            "{evidence} Test number {moment} counts towards the same season; a "
            "resit exam is the next season.",
        "question.moment.same": "Test {moment} of the {epoca}",
        "question.moment.same_hint":
            "continuous assessment — sat on the same day as the exam",
        "question.moment.other": "{epoca} (exam)",
        "question.moment.other_hint":
            "students who failed the previous season sit this exam",
        "question.merge.title": "Are {names} the same course?",
        "question.merge.detail_code":
            "They share the same code ({code}) but the sheets give them different "
            "names: {files}.",
        "question.merge.detail_similar":
            "They look like the same course but the sheets give them different "
            "names: {files}.",
        "question.merge.yes": "Yes — use «{name}»",
        "question.merge.split": "No, they are different courses",
        "question.merge.split_hint": "each sheet keeps its own name",

        "conflict.type.numero": "student number",
        "conflict.type.nota": "grade",
        "conflict.type.linha_repetida": "repeated row",
        "warning.type.nome": "name",
        "warning.type.possivel_duplicado": "possible duplicate",
        "warning.type.cadeiras_juntadas": "courses merged",
        "warning.type.pauta_sem_nota_final": "sheet without a final grade",
        "warning.type.plano_incompleto": "incomplete study plan",
        "conflict.numero.detail":
            "The same student shows up with different numbers: {ids}.",
        "warning.nome.detail":
            "The name is spelled in different ways: {names}. Used: «{chosen}».",
        "conflict.repeated_row.detail":
            "The student shows up more than once in «{column}» ({source}) with "
            "different values: {values}",
        "conflict.grade.detail": "Different values in different files: {values}",
        "conflict.grade.chosen": "{value} ({source}) — {reason}",
        "reason.newest_document": "the most recent document",
        "reason.latest_file": "the file added last",
        "warning.similar_names.detail":
            "«{left}» and «{right}» have very similar names ({similarity} alike) but "
            "were kept as different students. Please check whether it is the same "
            "person.",
        "warning.merged.detail_code":
            "The sheets {files} share the same code ({code}) but give it different "
            "names: {names}. They were treated as one, under the name «{chosen}».",
        "warning.merged.detail_similar":
            "The sheets {files} look like the same course but give it different "
            "names: {names}. They were treated as one, under the name «{chosen}».",
        "warning.no_final.detail":
            "«{label}» has no column marked as the final grade, so it does not "
            "count. {why}To use it, open the advanced settings and mark the right "
            "column as the final grade.",
        "warning.no_final.component": "The sheet only covers «{label}» ({weight}%). ",
        "warning.coverage.detail":
            "Has grades in {have} of the {total} courses in the plan. The averages "
            "only cover what exists — missing: {missing}.",

        "api.no_files": "No file came through.",
        "api.unsupported_format":
            "«{ext}» files are not supported. PDF, XLSX, CSV and TXT are.",
        "api.read_failed": "The file could not be read: {error}",
        "api.no_table":
            "No grade table was found in «{name}». If it is a scanned PDF (an "
            "image), it has to go through OCR first.",
        "api.nothing_loaded": "No file has been loaded yet.",
        "api.too_large": "File too large (the limit is 64 MB).",
        "api.internal_error": "Internal error: {error}",
        "api.unknown_action": "Unknown action: «{action}».",
        "xl.sheet.summary": "Summary",
        "xl.sheet.averages": "Averages",
        "xl.sheet.detail": "Detail",
        "xl.sheet.notices": "Notices",
        "xl.summary.title": "Consolidated grades — one row per student",
        "xl.summary.subtitle": "Generated on {stamp} · Files: {files}",
        "xl.summary.pass_row": "Pass mark per course",
        "xl.summary.uc_average": "Course average",
        "xl.summary.uc_approved": "Passed",
        "xl.summary.pass_hint": "edit them on each course sheet (yellow cell)",
        "xl.col.student_id": "Student nr.",
        "xl.col.name": "Name",
        "xl.col.average": "Average",
        "xl.col.approved": "Passed",
        "xl.col.subjects": "Courses",
        "xl.col.best": "Best grade",
        "xl.col.final": "Final grade",
        "xl.col.best_epoca": "Season of the best",
        "xl.col.state": "Status",
        "xl.col.best_source": "Source of the best grade",
        "xl.col.subject": "Course",
        "xl.col.epoca": "Season",
        "xl.col.kind": "Kind",
        "xl.col.item": "Item",
        "xl.col.value": "Value",
        "xl.col.source": "Source",
        "xl.col.severity": "Severity",
        "xl.col.type": "Type",
        "xl.col.description": "Description",
        "xl.col.chosen": "Value used",
        "xl.col.band": "Band",
        "xl.col.rounded": "Rounded",
        "xl.col.ects": "ECTS",
        "xl.col.course": "Degree",
        "xl.col.files": "Files",
        "xl.distribution.title": "Distribution of the best grades",
        "xl.distribution.chart": "Best grades per band",
        "xl.distribution.students": "Students",
        "xl.subject.pass_mark": "Pass mark",
        "xl.subject.pass_hint": "↖ editable — the «Status» column recalculates.",
        "xl.subject.sources": "Files: {files}",
        "xl.subject.subtitle": "{count} student(s) · best of the three seasons · generated on {stamp}",
        "xl.state.approved": "Passed",
        "xl.state.failed": "Failed",
        "xl.state.pending": "—",
        "xl.averages.title": "Averages per semester, per year and for the degree",
        "xl.averages.subtitle":
            "Only passed courses count · blank ECTS count as 1 · generated on {stamp}",
        "xl.averages.semester": "Year {year} · semester {semester}",
        "group.year": "Year {year}",
        "group.semester": "Semester {semester}",
        "group.none": "No year or semester",
        "xl.averages.year": "Year {year} average",
        "xl.averages.final": "Degree average",
        "xl.detail.title": "Every grade, one per row",
        "xl.detail.subtitle": "One row per grade, with its source · generated on {stamp}",
        "xl.detail.final": "Final grade",
        "xl.notices.title": "Notices and conflicts",
        "xl.notices.subtitle": "{count} things to check · generated on {stamp}",
        "xl.notices.none": "No conflicts: every file was read without ambiguities.",
        "xl.notices.conflict": "Conflict",
        "xl.notices.info": "Information",
    },
}


def tr(key: str, lang: str = DEFAULT_LANGUAGE, **params) -> str:
    """Texto da chave na lingua pedida. Sem traducao, fica o portugues."""
    table = CATALOG.get(normalize_language(lang)) or CATALOG[DEFAULT_LANGUAGE]
    template = table.get(key)
    if template is None:
        template = CATALOG[DEFAULT_LANGUAGE].get(key)
    if template is None:
        return key
    if not params:
        return template
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        return template


class Msg:
    """Mensagem por traduzir: chave mais parametros.

    Passa por string em portugues sempre que alguem a trata como tal, para que
    o codigo (e os testes) que so quer ler o texto continue a funcionar.
    """

    __slots__ = ("key", "params")

    def __init__(self, key: str, **params):
        self.key = key
        self.params = params

    def render(self, lang: str = DEFAULT_LANGUAGE) -> str:
        rendered = {k: (v.render(lang) if isinstance(v, Msg) else v)
                    for k, v in self.params.items()}
        return tr(self.key, lang, **rendered)

    def __str__(self) -> str:
        return self.render()

    def __repr__(self) -> str:
        return f"Msg({self.key!r})"

    def __eq__(self, other) -> bool:
        if isinstance(other, Msg):
            return self.key == other.key and self.params == other.params
        if isinstance(other, str):
            return str(self) == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.key)

    def __bool__(self) -> bool:
        return bool(str(self))

    def __len__(self) -> int:
        return len(str(self))

    def __contains__(self, item) -> bool:
        return item in str(self)

    def __add__(self, other) -> str:
        return str(self) + str(other)

    def __radd__(self, other) -> str:
        return str(other) + str(self)

    def __getitem__(self, item):
        return str(self)[item]


def render(value, lang: str = DEFAULT_LANGUAGE):
    """Devolve texto traduzido, deixando passar o que nao e mensagem."""
    if isinstance(value, Msg):
        return value.render(lang)
    if isinstance(value, list):
        return [render(item, lang) for item in value]
    return value


def group_label(year, semester, lang: str = DEFAULT_LANGUAGE) -> str:
    """«3.º ano · 2.º sem.», «3.º ano», «Sem ano nem semestre»."""
    if year is not None and semester is not None:
        return tr("xl.averages.semester", lang, year=year, semester=semester)
    if year is not None:
        return tr("group.year", lang, year=year)
    if semester is not None:
        return tr("group.semester", lang, semester=semester)
    return tr("group.none", lang)


def location_label(token, lang: str = DEFAULT_LANGUAGE) -> str:
    """Onde e que a tabela estava: «página 2», «folha «Pautas»», «texto».

    Os parsers guardam um sinal neutro (``page:2``) para o texto poder sair em
    qualquer lingua -- e para o que ja estava gravado em disco continuar a ler-se.
    """
    text = str(token or "")
    if text.startswith("page:"):
        pages = text[len("page:"):]
        key = "location.pages" if "," in pages else "location.page"
        return tr(key, lang, n=pages.replace(",", ", "))
    if text.startswith("sheet:"):
        return tr("location.sheet", lang, name=text[len("sheet:"):])
    if text == "text":
        return tr("location.text", lang)
    return text


def status_label(status, lang: str = DEFAULT_LANGUAGE) -> str:
    return tr(f"status.{status}", lang) if status else "—"


def notice_type(value, lang: str = DEFAULT_LANGUAGE) -> str:
    """Traduz o tipo de um aviso ou conflito ("linha repetida", ...)."""
    slug = str(value or "").strip().lower().replace(" ", "_")
    for prefix in ("conflict.type.", "warning.type."):
        if prefix + slug in CATALOG[DEFAULT_LANGUAGE]:
            return tr(prefix + slug, lang)
    return str(value or "")


def epoca_label(epoca, lang: str = DEFAULT_LANGUAGE) -> str:
    return tr(f"epoca.{epoca}", lang) if epoca else tr("epoca.unknown", lang)


def route_label(route, lang: str = DEFAULT_LANGUAGE) -> str:
    return tr(f"route.{route}", lang) if route else ""
