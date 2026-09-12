"""Agrega dados/mencoes.json nas visões que o painel usa e rastreia as levas.

Três leituras, cada uma com um limite honesto:

  1. QUEM APARECE      — quantas peças públicas citam cada nome (composição atual).
  2. POR PROCESSO      — matriz processo x nome: mostra que um processo gira em torno
                         de um ministro e outro traz políticos.
  3. POR LEVA          — agrupado pela data em que a peça foi vista pela primeira vez
                         por este pipeline. É a única medida direta de "o que entrou
                         agora"; a primeira execução é toda linha de base.

A data do andamento é a de juntada da peça, NÃO a de levantamento do sigilo — uma peça
de fevereiro que saiu do sigilo em setembro continua datada de fevereiro. Por isso a
série por mês é descrita como "material por mês de juntada", e as levas são medidas
pela observação do próprio pipeline.

Uso:  py -3.10 pipeline/montar_mencoes.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parent.parent
MENCOES = RAIZ / "dados" / "mencoes.json"
VISTAS = RAIZ / "dados" / "pecas_vistas.json"
SAIDA = RAIZ / "docs" / "mencoes.json"


def iso(data_br: str) -> str:
    p = (data_br or "").split("/")
    return f"{p[2]}-{p[1]}-{p[0]}" if len(p) == 3 else ""


def main() -> None:
    bruto = json.loads(MENCOES.read_text(encoding="utf-8"))
    pecas = bruto["pecas"]
    grupos = bruto["grupos"]
    hoje = date.today().isoformat()

    # --- rastreamento de levas: quando cada peça apareceu pela primeira vez ----
    vistas = json.loads(VISTAS.read_text(encoding="utf-8")) if VISTAS.exists() else {}
    novas = 0
    for p in pecas:
        if p["id"] not in vistas:
            vistas[p["id"]] = {"visto_em": hoje, "processo": p["processo"]}
            novas += 1
    VISTAS.write_text(json.dumps(vistas, ensure_ascii=False, indent=1), encoding="utf-8")

    # --- 1. quem aparece ------------------------------------------------------
    por_nome_pecas: Counter[str] = Counter()
    por_nome_subst: Counter[str] = Counter()
    por_nome_mencoes: Counter[str] = Counter()
    processos_por_nome: dict[str, set] = defaultdict(set)
    datas_por_nome: dict[str, list] = defaultdict(list)

    for p in pecas:
        for nome, n in p["mencoes"].items():
            por_nome_pecas[nome] += 1
            por_nome_mencoes[nome] += n
            if p.get("substantiva"):
                por_nome_subst[nome] += 1
            processos_por_nome[nome].add(p["processo"])
            d = iso(p["data_andamento"])
            if d:
                datas_por_nome[nome].append(d)

    pessoas = [
        {
            "nome": nome,
            "grupo": grupos.get(nome, ""),
            "pecas": por_nome_pecas[nome],
            "pecas_de_conteudo": por_nome_subst[nome],
            "mencoes": por_nome_mencoes[nome],
            "processos": sorted(processos_por_nome[nome]),
            "primeira_peca": min(datas_por_nome[nome]) if datas_por_nome[nome] else None,
            "ultima_peca": max(datas_por_nome[nome]) if datas_por_nome[nome] else None,
        }
        for nome in por_nome_pecas
    ]
    pessoas.sort(key=lambda x: -x["pecas"])

    # nomes acompanhados que ainda não apareceram em nenhuma peça acessível —
    # a diferença entre o que foi anunciado como liberado e o que dá para abrir
    ausentes = [
        {"nome": nome, "grupo": grupo}
        for nome, grupo in grupos.items()
        if nome not in por_nome_pecas
    ]

    # --- 2. matriz processo x nome -------------------------------------------
    matriz: dict[str, Counter] = defaultdict(Counter)
    total_por_processo: Counter[str] = Counter()
    for p in pecas:
        total_por_processo[p["processo"]] += 1
        for nome in p["mencoes"]:
            matriz[p["processo"]][nome] += 1
    por_processo = [
        {
            "processo": proc,
            "pecas": total_por_processo[proc],
            "nomes": dict(cont.most_common()),
        }
        for proc, cont in sorted(matriz.items(), key=lambda kv: -total_por_processo[kv[0]])
    ]

    # --- 3. por mês de juntada e por leva observada ---------------------------
    por_mes: dict[str, Counter] = defaultdict(Counter)
    pecas_por_mes: Counter[str] = Counter()
    for p in pecas:
        d = iso(p["data_andamento"])
        if not d:
            continue
        mes = d[:7]
        pecas_por_mes[mes] += 1
        for nome in p["mencoes"]:
            por_mes[mes][nome] += 1
    serie_mes = [
        {"mes": mes, "pecas": pecas_por_mes[mes], "nomes": dict(por_mes[mes].most_common())}
        for mes in sorted(pecas_por_mes)
    ]

    por_leva: dict[str, Counter] = defaultdict(Counter)
    pecas_por_leva: Counter[str] = Counter()
    for p in pecas:
        leva = vistas[p["id"]]["visto_em"]
        pecas_por_leva[leva] += 1
        for nome in p["mencoes"]:
            por_leva[leva][nome] += 1
    levas = [
        {
            "data": leva,
            "pecas": pecas_por_leva[leva],
            "linha_de_base": leva == min(pecas_por_leva),
            "nomes": dict(por_leva[leva].most_common()),
        }
        for leva in sorted(pecas_por_leva)
    ]

    saida = {
        "gerado_em": bruto["gerado_em"],
        "observacao": bruto["observacao"],
        "resumo": dict(
            bruto["resumo"],
            pecas_novas_nesta_coleta=novas,
            nomes_encontrados=len(pessoas),
        ),
        "pessoas": pessoas,
        "ausentes": ausentes,
        "por_processo": por_processo,
        "serie_mes": serie_mes,
        "levas": levas,
    }
    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"ok: {len(pessoas)} nomes encontrados em {len(pecas)} peças "
        f"({novas} novas nesta coleta) -> {SAIDA.relative_to(RAIZ)}"
    )


if __name__ == "__main__":
    main()
