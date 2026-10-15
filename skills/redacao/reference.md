# Redação: reference

## What a technical article is

A blog post about how something was built is an *explanation* in Diátaxis terms: it answers "why is it like this", not "how do I do X". It can show code, but it is not a tutorial and should not turn into numbered steps. Source: https://diataxis.fr/explanation/

Classic style (Pinker, *The Sense of Style*): the writer shows the reader something in the world, as one equal to another. No warm-up, no persuasion tricks, no talking about the text itself.

## Structure

- **Open with a fact, not a preamble.** The first two sentences carry a concrete thing: a number, a bug, a scene. Never "Neste post vou falar sobre", never "No cenário atual".
- **Concrete before abstract.** Show the code, the number or the failure, then name the principle. A principle with no example goes.
- **Headings say what the section shows.** "A URL decide o idioma" beats "Internacionalização". No "Introdução", no "Conclusão".
- **A number when the number is the point.** "Rápido" means nothing; "12 páginas em 4,9 s" means something. But a paragraph with three numbers, two file names and a commit hash is a changelog: keep the one number the reader will remember and link the rest.
- **Say what is missing.** An honest gap makes the rest credible. A list of virtues with no cost reads as an ad.
- **End on the next concrete thing**, a limit or an open question. No summary of what the reader just read, no moral, no call to action ("Faz isso no seu site").
- **Someone is talking.** The author has opinions, gets annoyed, is wrong, is unsure. A text where every sentence is a verified neutral fact has no one in it.

## Portuguese (pt-BR)

Each rule with a bad → good pair.

| Rule | Ruim | Bom |
|---|---|---|
| Verb over noun (nominalização) | realizar a implementação do cache | implementar o cache |
| No gerundismo | vamos estar analisando | vamos analisar |
| "Onde" only for places | o teste onde o erro aparece | o teste em que o erro aparece |
| No "a nível de" | a nível de arquitetura | na arquitetura |
| No "o mesmo" as pronoun | abri o arquivo e editei o mesmo | abri o arquivo e o editei |
| Active voice with a subject | foi decidido que o CI roda o lint | decidi que o CI roda o lint |
| "Se" impessoal sparingly | percebe-se que o build falha | o build falha |
| Short sentences, one idea each | a sentence of 45 words with three "que" | split it |
| Crase | devido à isso / referente a página | devido a isso / referente à página |
| Hyphen, 2009 agreement | auto-avaliação, anti-padrão | autoavaliação, antipadrão |
| Decimal comma, unit spaced | 4.9s, 50 % | 4,9 s, 50% |

English terms: use the word the Brazilian developer says (*build*, *deploy*, *commit*, *bundle*, *lint*). Do not italicise them and do not force a translation nobody uses ("implantação" for deploy reads like a manual). Translate when Portuguese has a word in daily use: *teste*, *ilha* (Astro island), *janela*, *acessibilidade*. Code identifiers go in backticks and are never translated.

Person: first person singular for a personal blog ("eu medi"). "A gente" fits a casual register; pick one and keep it. Address the reader as "você".

## AI tells

Habits that make prose worse, whoever wrote it. Remove on sight. Full list in English: https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing (the `humanizer` skill covers it, if installed).

- **Contrast that only adds weight**: "não é apenas X, é Y", "não se trata de X, mas de Y", "mais do que X, é Y". State Y.
- **Stock words**: crucial, fundamental, essencial, robusto, jornada, mergulhar, desvendar, no cenário atual, em um mundo, vale ressaltar, é importante destacar, em suma, em resumo, por fim mas não menos importante, transformador, potencializar, alavancar, ecossistema (outside its technical sense).
- **Triads by reflex**: three adjectives or three clauses where the meaning has one or two.
- **Dashes as the universal connector**: use a comma, a colon, parentheses or a full stop. At most one pair of dashes per article, and only for a real aside.
- **Closing one-liners**: a paragraph that ends with a short sentence repeating its point ("E isso faz toda a diferença.").
- **Staged run-up**: "A verdade é que", "O ponto é", "Aqui está o segredo:".
- **Bold labels and decorative lists**: prose that became bullets with a bolded first word. An article is paragraphs; a list only for things that are genuinely a list.
- **Connector piles**: "além disso", "dessa forma", "nesse sentido" opening consecutive paragraphs.
- **Inflated significance**: "um marco", "revolucionou", "mudou completamente". Say what changed and by how much.
- **Talking about the text**: "neste artigo", "como vimos acima", "vamos explorar".

### Structural tells

Avoiding the words above is not enough: a model that drops "crucial" and every dash still writes in its own shape. These came from a draft that had none of the word-level tells and still read as machine-made from the first line.

- **Even rhythm.** Every paragraph four to six sentences of similar length, each built the same way (claim, evidence, consequence). Vary on purpose: a one-line paragraph next to a long one, a long sentence that wanders when the thought wanders, a fragment.
- **Inventory paragraphs.** "Um confere... Outro garante... Outro checa... E tem um que...", "Pra mim, X quer dizer cinco coisas", a list of facts walked through in prose. Pick the one example that matters and tell it.
- **Fact density.** Identifiers, counts and commit hashes in every paragraph. The reader cannot hold them; link the commit, keep the story.
- **Narrator without a person.** No opinion, no joke, no doubt, no "eu achava". Everything reported, nothing felt.
- **Borrowed informality.** "tá" and "pra" sprinkled over formal syntax. The register is the author's, taken from their own text, and it holds through the whole article.
- **Swallowed scope.** The article grew to hold everything the apuração found. One idea per post; the rest is the next pauta.

### On AI detectors

Detectors are classifiers trained on model output. They flag predictable, even prose, and they also flag formal or non-native human writing: seven detectors marked 61% of TOEFL essays by human writers as AI (Liang et al., 2023: https://arxiv.org/abs/2304.02819). Do not chase a score and never rewrite to fool one. A flagged draft is a symptom that the author is missing from the text; the fix is the entrevista, not synonyms.

## Checklist before the editor's last aprova

1. Every number and name is in the fact sheet with a source.
2. The first two sentences carry a concrete fact.
3. No heading is generic.
4. No paragraph ends in a one-line moral.
5. None of the AI tells above. Search the text for "não é apenas", "crucial", "-", "além disso", "jornada".
6. Every paragraph is one line in the file (no hard wrap).
7. At least one honest limit is stated.
8. Code in backticks, identifiers untranslated, decimal comma in prose.
9. Every section carries something from the entrevista or the author's own text, and no feeling, habit or reason was invented for them.
10. Paragraph lengths vary; no three paragraphs in a row share the same shape.
11. The word count is within the pauta's target, and the scope is still the author's idea.
12. No closing summary section and no call to action.

## Reading list

Portuguese, writing:

- Othon M. Garcia, *Comunicação em Prosa Moderna* (FGV). The Brazilian classic on building a paragraph and an argument.
- *Manual de Redação da Presidência da República*, 3ª ed.: https://www.gov.br/planalto/pt-br/conheca-a-presidencia/manual-de-redacao-da-presidencia-da-republica. Clarity, concision, the "o mesmo" and gerund rules.
- *Manual de Comunicação da Secom do Senado*: https://www12.senado.leg.br/manualdecomunicacao. A newsroom style guide with one entry per style question (datas, maiúsculas) and a guide on using AI in writing.
- Microsoft pt-BR localization style guide (in the list): https://learn.microsoft.com/en-us/globalization/reference/microsoft-style-guides. How a large tech company handles English terms, "você" and capitalisation in Portuguese.

Portuguese, technical writing worth reading:

- Fabio Akita: https://akitaonrails.com/. Long-form, opinionated, full of numbers and real setups.
- Elton Minetto: https://eltonminetto.dev/. Short, direct Go and architecture posts.
- Lucas Santos: https://lsantos.dev/. Clear explanations of Node.js and TypeScript.
- Building Nubank: https://building.nubank.com/pt-br/. Engineering blog that writes for engineers, not recruiters.
- TabNews: https://www.tabnews.com.br/. Uneven, but shows what Brazilian developers actually read and discuss.

English, on writing:

- Google Technical Writing One and Two: https://developers.google.com/tech-writing
- Paul Graham, "Write Simply": https://paulgraham.com/simply.html
- Julia Evans, "Some tactics for writing in public": https://jvns.ca/blog/2023/08/07/tactics-for-writing-in-public/
- Dan Luu, "Writing non-advice": https://danluu.com/writing-non-advice/
- Steven Pinker, *The Sense of Style* (2014).

References often cited in articles about reliability:

- Google SRE book: https://sre.google/sre-book/table-of-contents/
- Kent C. Dodds, the testing trophy: https://kentcdodds.com/blog/the-testing-trophy-and-testing-classifications
- Ham Vocke, "The Practical Test Pyramid": https://martinfowler.com/articles/practical-test-pyramid.html
- Core Web Vitals: https://web.dev/articles/vitals
- WCAG 2.2: https://www.w3.org/TR/WCAG22/
