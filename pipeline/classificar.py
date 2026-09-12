"""Classifica cada andamento quanto ao sigilo e cada processo quanto à apuração ativa.

Três níveis de confiança, do mais sólido ao mais inferido:

  1. SIGILO DECLARADO (sólido) — o próprio portal escreve "Petição Sigilosa",
     "Decisão (sigiloso)" ou "segredo". Cruzando com a existência de PDF baixável,
     sai a taxa de sigilo efetivamente levantado.
  2. PEÇA ESPERADA E AUSENTE (razoável) — andamento de um tipo que normalmente tem
     peça (decisão, despacho, certidão, manifestação) sem documento acessível.
     Separado de andamento que por natureza nunca tem peça (conclusão, remessa,
     autuação, publicação no DJE).
  3. APURAÇÃO ATIVA (inferência) — sinais objetivos nos andamentos de que a
     investigação ainda corre: diligência determinada, autos à autoridade policial,
     prorrogação de inquérito, movimentação recente. É o critério que a própria
     decisão de Fachin usou para mandar abrir o que não tem investigação em curso.
     É inferência a partir do andamento, não juízo sobre o mérito.

Não gera arquivo próprio: é importado por montar_dados.py.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

# tipos de andamento que por natureza não têm peça para o público
SEM_PECA_POR_NATUREZA = re.compile(
    r"conclus|remessa|expedid|autuad|protocolad|distribu|redistribu|baixa|juntada do mandado|"
    r"publica[çc][ãa]o|ata de julgamento|lista de julgamento|julgamento virtual|vista -|"
    r"suspenso o julgamento|devolu[çc][ãa]o|lan[çc]amento indevido|intimado eletronicamente",
    re.I,
)
# tipos que normalmente produzem peça
PECA_ESPERADA = re.compile(
    r"decis[ãa]o|despacho|certid[ãa]o|peti[çc][ãa]o|manifesta[çc][ãa]o|ac[óo]rd[ãa]o|"
    r"parecer|relat[óo]rio|senten[çc]a|deferid|indeferid",
    re.I,
)
MARCA_SIGILO = re.compile(r"sigil|segredo de justi", re.I)
# sinais de que a apuração continua correndo
APURACAO_ATIVA = re.compile(
    r"dilig[êe]ncia|autoridade policial|prorroga|inqu[ée]rito|busca e apreens|"
    r"quebra de sigilo|afastamento de sigilo|interceptac|pris[ãa]o",
    re.I,
)


def classificar_andamento(a: dict) -> str:
    texto = f"{a.get('nome','')} {a.get('descricao','')}"
    tem_doc = bool(a.get("documentos"))
    if a.get("invalido"):
        return "anulado"
    if MARCA_SIGILO.search(texto):
        return "sigiloso_liberado" if tem_doc else "sigiloso_fechado"
    if tem_doc:
        return "publico_com_peca"
    if SEM_PECA_POR_NATUREZA.search(a.get("nome", "")):
        return "sem_peca_por_natureza"
    if PECA_ESPERADA.search(a.get("nome", "")):
        return "peca_esperada_ausente"
    return "sem_peca_por_natureza"


ROTULOS = {
    "sigiloso_liberado": "Marcado como sigiloso e já acessível",
    "sigiloso_fechado": "Marcado como sigiloso e ainda fechado",
    "publico_com_peca": "Público, com peça acessível",
    "peca_esperada_ausente": "Deveria ter peça, e não há",
    "sem_peca_por_natureza": "Andamento sem peça por natureza",
    "anulado": "Andamento anulado pelo próprio STF",
}


def sinais_de_apuracao(andamentos: list[dict], iso) -> dict:
    """Sinais objetivos de investigação em curso, com janela de 180 dias."""
    limite = (date.today() - timedelta(days=180)).isoformat()
    recentes = [a for a in andamentos if (iso(a.get("data", "")) or "") >= limite]
    gatilhos = sorted(
        {
            a["nome"]
            for a in recentes
            if APURACAO_ATIVA.search(f"{a.get('nome','')} {a.get('descricao','')}")
        }
    )[:6]
    datas = sorted(filter(None, (iso(a.get("data", "")) for a in andamentos)))
    ultima = datas[-1] if datas else None
    movimentacao_recente = bool(
        ultima and ultima >= (date.today() - timedelta(days=60)).isoformat()
    )
    return {
        "apuracao_ativa": bool(gatilhos) and movimentacao_recente,
        "gatilhos": gatilhos,
        "movimentacao_recente": movimentacao_recente,
        "ultima_movimentacao": ultima,
    }
