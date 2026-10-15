#!/usr/bin/env python3
import json
import os
import re
import statistics
import sys
import urllib.parse
import urllib.request

LT = os.environ.get("LANGUAGETOOL_URL", "http://127.0.0.1:8010")
SKIP_RULES = {"WHITESPACE_RULE", "UPPERCASE_SENTENCE_START", "FORMAL_PRA_PARA", "REMOVER_EU_NÓS"}


def prose(text):
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    url = r"\((?:[^()]|\([^()]*\))*\)"
    text = re.sub(r"!\[[^\]]*\]" + url, "", text)
    text = re.sub(r"\[([^\]]*)\]" + url, r"\1", text)
    text = re.sub(r"`[^`]*`", "código", text)
    lines = [l for l in text.splitlines() if l.strip() and not l.startswith(("#", ">"))]
    return [l.strip() for l in lines]


def ritmo(paragraphs):
    body = " ".join(paragraphs)
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", body) if len(s.split()) > 1]
    sl = [len(s.split()) for s in sentences]
    pl = [len(p.split()) for p in paragraphs]
    words = sum(pl)
    cv = lambda xs: statistics.stdev(xs) / statistics.mean(xs) if len(xs) > 1 else 0.0
    return {
        "palavras": words,
        "frases": len(sl),
        "cv_frase": round(cv(sl), 2),
        "paragrafos": pl,
        "cv_paragrafo": round(cv(pl), 2),
        "eu_por_100": round(100 * len(re.findall(r"\b(eu|meu|minha|me|comigo)\b", body, re.I)) / max(words, 1), 1),
        "digitos_por_100": round(100 * len(re.findall(r"\d+", body)) / max(words, 1), 1),
    }


def languagetool(paragraphs):
    data = urllib.parse.urlencode({"language": "pt-BR", "text": "\n\n".join(paragraphs)}).encode()
    with urllib.request.urlopen(f"{LT}/v2/check", data, timeout=60) as r:
        matches = json.load(r)["matches"]
    for m in matches:
        if m["rule"]["id"] in SKIP_RULES:
            continue
        ctx = m["context"]
        frag = ctx["text"][ctx["offset"] : ctx["offset"] + ctx["length"]]
        fix = ", ".join(x["value"] for x in m["replacements"][:3])
        yield f'{m["rule"]["id"]}: "{frag}" -> {fix or "?"} ({m["message"]})'


def demo():
    p = prose("---\nt: x\n---\n# H\n\nEu fiz `a` e [b](u_(x)).\n\n> nota\n\nOutra frase curta. E mais uma aqui.\n")
    assert p == ["Eu fiz código e b.", "Outra frase curta. E mais uma aqui."], p
    r = ritmo(p)
    assert r["palavras"] == 12 and r["frases"] == 3 and r["eu_por_100"] == 8.3, r


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("uso: checar.py artigo.md   (ou --demo)")
    if sys.argv[1] == "--demo":
        demo()
        sys.exit(0)
    paragraphs = prose(open(sys.argv[1], encoding="utf-8").read())
    print(json.dumps(ritmo(paragraphs), ensure_ascii=False))
    try:
        for line in languagetool(paragraphs):
            print(line)
    except OSError as e:
        print(f"LanguageTool fora do ar em {LT} ({e}); suba com: podman run -d --rm --name languagetool -p 127.0.0.1:8010:8010 docker.io/erikvl87/languagetool")
