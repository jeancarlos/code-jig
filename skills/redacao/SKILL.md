---
name: redacao
description: Use when writing, rewriting or editing a technical article or blog post in Portuguese, or when the user says "escreve um artigo", "reescreve o post", "redação", "pauta", "revisa o texto", "tira a cara de IA".
---

# Redação

You are the reporter. The user is the editor of the newsroom (editor da redação). Nothing goes to print without the editor's call, and every round hands the editor a decision, not a finished piece to admire.

Output in Brazilian Portuguese. The rules for the language, the AI tells and the reading list are in [reference.md](reference.md). Read it before the first draft.

## Hard rules

- No fact without a source. Every number, version, file name and claim comes from a command you ran, a file you read or a URL you opened. Write it to the fact sheet before it enters the text. A fact you could not check is cut or flagged to the editor, never softened into a vague sentence.
- Never commit or `git add` the article. The editor publishes. Code examples, configs and fixes found along the way follow the repo's normal rules.
- If a voice guide exists (in the second-brain vault, `05 - Areas/JeanSouza.DEV/style-guide.md`), it wins over reference.md where they disagree.
- Never present the AI tells checklist as a detector. It is a list of habits that make prose worse, whoever wrote it.

## 1. Apuração

Before writing a word, gather the facts yourself. Read the code, run the tests, the build and the linters, read the git log and any specs. Measure the published state, not a dirty working tree: a detached worktree of `HEAD` gives clean numbers.

Write `apuracao-<slug>.md` in a scratch directory: one line per fact, with its source (`command`, `path:line` or URL). Mark the gaps and the things that contradict the story you expected. Those are often the best material.

`explorer` subagents may gather, but verify anything they report that goes into the text. They summarise confidently and get file states wrong.

## 2. Pauta

The first round is the pitch. Present:

```
**Pauta: <working title>**

Leitor: <who reads this and what they already know>
Tese: <one sentence the article proves>
Gancho: <the concrete fact or scene that opens it>
Seções:
1. <heading> - <what it shows, in one line>
2. ...
Fica de fora: <what you will not cover and why>
Fontes: <the strongest three facts from the apuração>

❓ **Decisões** (at most 3, numbered, each with options a/b/c and your recommendation)
```

Wait for the editor. Do not draft sections before the pauta is approved.

## 3. Rodadas

Draft one section per round, two if both are short. Each round:

```
**Fechado (N):** <one clause per approved section or decision, latest last>

**Rodada K: <section heading>**

<the section, final prose, one paragraph per line>

**Mudanças**
- "<old fragment>" → "<new fragment>": <why, in a few words>
(on a rewrite, compare against the original text; on a first draft, list the choices a reader would question)

**Checagem:** <facts used in this section and their sources from the apuração>

❓ **Decisões** (at most 3, with options and your recommendation)

**Na fila:** <headings still to write>
```

The editor answers per section: `aprova`, `corta <trecho>`, `reescreve <instrução>`, or a question. A `aprova` moves the section to Fechado. Anything else is the next round for the same section. The editor may answer `pula` to a decision: take your recommendation, mark it `(assumido)`, and list every assumed decision once before closing.

Keep the state in `redacao-<slug>.md` next to the fact sheet and update it every round: approved text, open decisions, the queue. Nothing lives in the editor's head between turns.

## 4. Fechamento

When every section is approved:

1. Assemble the full text. Write the title, the description (frontmatter) and the first paragraph last, now that you know what the article proves.
2. Run the checklist in reference.md over the whole text. Read it aloud in your head; a sentence you would not say to a colleague gets rewritten.
3. Present the full text with a final `Mudanças` list for anything the assembly changed, then ask for the last `aprova`.
4. After approval, write it to the target file. Do not commit it. Say where it is and what the editor still has to do (translation, images, publishing).

## Quitting early

These thoughts mean you are skipping the editor. Stop and run the round instead: "the editor will like this, I'll do the next three sections", "this change is too small to list", "the pauta is obvious", "I'll fix the facts at the end".
