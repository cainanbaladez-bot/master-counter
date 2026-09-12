"""Transforma dados/processos.json no dados.json que o painel consome.

Também acumula dados/historico.jsonl — uma linha por execução — que é o que
permite ver o contador subir ao longo do tempo (peça antiga que sai do sigilo
não gera andamento novo; só aparece como documento a mais no total).

Uso:  py -3.10 pipeline/montar_dados.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parent.parent
ENTRADA = RAIZ / "dados" / "processos.json"
HISTORICO = RAIZ / "dados" / "historico.jsonl"
SAIDA = RAIZ / "docs" / "dados.json"


def iso(data_br: str) -> str | None:
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", data_br or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def resumir_processo(p: dict) -> dict:
    andamentos = p.get("andamentos", [])
    com_doc = [a for a in andamentos if a.get("documentos")]
    docs = [d for a in andamentos for d in a.get("documentos", [])]
    datas = sorted(filter(None, (iso(a.get("data", "")) for a in andamentos)))
    cab = p.get("cabecalho", {})
    return {
        "incidente": p["incidente"],
        "rotulo": cab.get("rotulo") or p.get("rotulo") or str(p["incidente"]),
        "numero_unico": p.get("numero_unico") or cab.get("numero_unico"),
        "relator": cab.get("relator", ""),
        "publicidade": cab.get("publicidade") or p.get("publicidade") or "—",
        "etiquetas": cab.get("etiquetas", []),
        "em_tramitacao": p.get("em_tramitacao"),
        "autuacao": p.get("autuacao") or p.get("informacoes", {}).get("Data de Protocolo"),
        "assunto": p.get("informacoes", {}).get("Assunto", ""),
        "origem": p.get("informacoes", {}).get("Origem", ""),
        "nota": p.get("nota", ""),
        "partes": p.get("partes", [])[:12],
        "url_portal": p["url_portal"],
        "url_pecas": p["url_pecas"],
        "andamentos": len(andamentos),
        "andamentos_com_documento": len(com_doc),
        "documentos": len(docs),
        "pct_com_documento": round(100 * len(com_doc) / len(andamentos), 1) if andamentos else 0.0,
        "primeira_movimentacao": datas[0] if datas else None,
        "ultima_movimentacao": datas[-1] if datas else None,
        "decisoes": len(p.get("decisoes", [])),
        "peticoes": len(p.get("peticoes", [])),
    }


def no_escopo(p: dict) -> bool:
    """A busca por parte traz homônimos e processos antigos de outras 'Master'.

    Fica no painel quem é semente curada em config/caso.json ou quem está sob
    relatoria do ministro alvo.
    """
    if p.get("seed"):
        return True
    return bool(p.get("do_relator_alvo"))


def main() -> None:
    bruto = json.loads(ENTRADA.read_text(encoding="utf-8"))
    dentro = [p for p in bruto["processos"] if no_escopo(p)]
    fora = [p for p in bruto["processos"] if not no_escopo(p)]
    processos = [resumir_processo(p) for p in dentro]
    processos.sort(key=lambda r: (-r["documentos"], -r["andamentos"]))

    # --- série temporal: andamentos e documentos por dia -------------------
    por_dia_and: Counter[str] = Counter()
    por_dia_doc: Counter[str] = Counter()
    tipos: Counter[str] = Counter()
    for p in dentro:
        for a in p.get("andamentos", []):
            d = iso(a.get("data", ""))
            if not d:
                continue
            por_dia_and[d] += 1
            por_dia_doc[d] += len(a.get("documentos", []))
            tipos[a.get("nome") or "(sem nome)"] += 1

    dias = sorted(set(por_dia_and) | set(por_dia_doc))
    acumulado = 0
    serie = []
    for d in dias:
        acumulado += por_dia_doc[d]
        serie.append(
            {
                "data": d,
                "andamentos": por_dia_and[d],
                "documentos": por_dia_doc[d],
                "documentos_acumulados": acumulado,
            }
        )

    total_and = sum(p["andamentos"] for p in processos)
    total_com = sum(p["andamentos_com_documento"] for p in processos)
    total_doc = sum(p["documentos"] for p in processos)

    resumo = {
        "processos": len(processos),
        "processos_sob_relator": sum(
            1 for p in processos if "MENDONÇA" in (p["relator"] or "").upper()
        ),
        "processos_publicos": sum(1 for p in processos if (p["publicidade"] or "").startswith("Públic")),
        "processos_sigilosos": sum(1 for p in processos if "egredo" in (p["publicidade"] or "")),
        "andamentos": total_and,
        "andamentos_com_documento": total_com,
        "documentos": total_doc,
        "pct_andamentos_com_documento": round(100 * total_com / total_and, 1) if total_and else 0.0,
        "fora_do_escopo": len(fora),
    }

    # --- histórico de execuções -------------------------------------------
    linha = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "documentos": total_doc,
        "andamentos": total_and,
        "processos": len(processos),
        "por_processo": {str(p["incidente"]): p["documentos"] for p in processos},
    }
    anterior = []
    if HISTORICO.exists():
        anterior = [json.loads(l) for l in HISTORICO.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not anterior or anterior[-1]["documentos"] != total_doc or anterior[-1]["ts"][:10] != linha["ts"][:10]:
        with HISTORICO.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(linha, ensure_ascii=False) + "\n")
        anterior.append(linha)

    historico = [
        {"ts": h["ts"], "documentos": h["documentos"], "andamentos": h["andamentos"]}
        for h in anterior
    ]

    saida = {
        "gerado_em": bruto["gerado_em"],
        "caso": bruto["caso"],
        "marcos": sorted(bruto["marcos"], key=lambda m: m["data"]),
        "resumo": resumo,
        "processos": processos,
        "serie": serie,
        "tipos_andamento": [
            {"nome": n, "n": q} for n, q in tipos.most_common(15)
        ],
        "historico": historico,
        "fora_do_escopo": [
            {
                "rotulo": p.get("rotulo"),
                "relator": p.get("cabecalho", {}).get("relator", ""),
                "url_portal": p["url_portal"],
            }
            for p in fora
        ],
        "fontes": [
            {
                "nome": "Portal de processos do STF",
                "url": "https://portal.stf.jus.br/processos/",
            },
            {
                "nome": "API pública de partes (digital.stf.jus.br)",
                "url": "https://digital.stf.jus.br/integracoes-processos/api/public/partes/processos",
            },
        ],
    }
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"ok: {len(processos)} processos, {total_and} andamentos, {total_doc} documentos "
        f"→ {SAIDA.relative_to(RAIZ)}"
    )


if __name__ == "__main__":
    main()
