"""Coleta os dados públicos dos processos do caso Banco Master no STF.

Fontes (todas públicas, sem login):
  1. API pública de partes    digital.stf.jus.br/integracoes-processos/api/public/partes/processos
  2. Abas do portal de processos  portal.stf.jus.br/processos/aba*.asp?incidente=<id>

Saída: dados/processos.json (estado atual) + dados/raw/<incidente>/*.html (cache bruto).

Uso:  py -3.10 pipeline/coletar.py [--sem-rede]
"""
from __future__ import annotations

import argparse
import json
import sys
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import urllib3
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "config" / "caso.json"
DIR_RAW = RAIZ / "dados" / "raw"
SAIDA = RAIZ / "dados" / "processos.json"

PORTAL = "https://portal.stf.jus.br/processos"
API_PARTES = (
    "https://digital.stf.jus.br/integracoes-processos/api/public/partes/processos"
)
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"}
PAUSA = 1.2  # segundos entre requisições — o portal é público, não vamos martelar

# Em algumas máquinas Windows (antivírus/proxy que reescreve TLS) a verificação de
# certificado do portal falha. Na primeira falha de SSL passamos a não verificar e
# avisamos — no GitHub Actions isso nunca é acionado.
VERIFICAR_TLS = True


# --------------------------------------------------------------------------- rede
def baixar(url: str, tentativas: int = 3) -> str:
    global VERIFICAR_TLS
    erro = None
    for i in range(tentativas):
        try:
            r = requests.get(url, headers=HEADERS, timeout=90, verify=VERIFICAR_TLS)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except requests.exceptions.SSLError as exc:
            erro = exc
            if VERIFICAR_TLS:
                VERIFICAR_TLS = False
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                print("    aviso: TLS do portal nao verificavel nesta maquina; seguindo sem verificacao")
            time.sleep(1)
        except Exception as exc:  # noqa: BLE001
            erro = exc
            time.sleep(2 + 3 * i)
    raise RuntimeError(f"falha ao baixar {url}: {erro}")


def descobrir_processos(termos: list[str], relator: str | None) -> list[dict]:
    """Busca processos pela API pública de partes e devolve os incidentes."""
    achados: dict[int, dict] = {}
    for termo in termos:
        for em_tramitacao in ("sim", "nao"):
            url = (
                f"{API_PARTES}?nome={requests.utils.quote(termo)}"
                f"&processosPorPagina=100&pagina=1"
                f"&processosEmTramitacao={em_tramitacao}&tipoPesquisa=PARTE"
            )
            try:
                dados = json.loads(baixar(url))
            except Exception as exc:  # noqa: BLE001
                print(f"    aviso: busca por '{termo}' falhou ({exc})")
                continue
            for parte in dados.get("partes", []):
                inc = parte.get("processoId")
                if not inc:
                    continue
                reg = achados.setdefault(
                    inc,
                    {
                        "incidente": inc,
                        "rotulo": parte.get("processoIdentificacao"),
                        "numero_unico": parte.get("processoNumeroUnico"),
                        "autuacao": parte.get("processoDataAutuacao"),
                        "publicidade": parte.get("processoPublicidade"),
                        "em_tramitacao": parte.get("processoEmTramitacao"),
                        "partes": [],
                        "origem_descoberta": termo,
                    },
                )
                nome = parte.get("pessoaNome")
                if nome and nome not in reg["partes"]:
                    reg["partes"].append(nome)
            time.sleep(PAUSA)
    return list(achados.values())


# -------------------------------------------------------------------------- parse
def _texto(no) -> str:
    return re.sub(r"\s+", " ", no.get_text(" ", strip=True)).strip() if no else ""


def parse_informacoes(html: str) -> dict:
    """A aba de informações é uma sequência de pares rótulo/valor em divs irmãs."""
    sopa = BeautifulSoup(html, "html.parser")
    info: dict[str, str] = {}

    assunto = sopa.select_one(".informacoes__assunto .processo-detalhes")
    if assunto:
        info["Assunto"] = " | ".join(_texto(li) for li in assunto.select("li")) or _texto(assunto)

    divs = sopa.select("div.processo-detalhes-bold, div.processo-detalhes")
    for i, div in enumerate(divs):
        bruto = _texto(div)
        if not bruto.endswith(":"):
            continue
        rotulo = bruto.rstrip(":").strip()
        if i + 1 < len(divs):
            valor = _texto(divs[i + 1])
            if valor and not valor.endswith(":"):
                info[rotulo] = valor[:600]

    for quadro in sopa.select(".processo-quadro"):
        rot = _texto(quadro.select_one(".rotulo"))
        num = _texto(quadro.select_one(".numero"))
        if rot:
            info[rot] = num

    return info


def parse_cabecalho(html: str) -> dict:
    """Classe/número, relator, publicidade e etiquetas da página de detalhe."""
    sopa = BeautifulSoup(html, "html.parser")
    cab: dict = {}

    campo = sopa.select_one("#classe-numero-processo")
    if campo and campo.get("value"):
        cab["rotulo"] = campo["value"].strip()

    rot = sopa.select_one(".processo-rotulo")
    if rot:
        m = re.search(r"(\d[\d.]*-[\d.]+\.\d{4}\.\d\.\d{2}\.\d{4})", _texto(rot))
        if m:
            cab["numero_unico"] = m.group(1)

    classe = sopa.select_one(".processo-classe")
    if classe:
        cab["classe"] = _texto(classe)

    for div in sopa.select(".processo-dados"):
        txt = _texto(div)
        if txt.startswith("Relator(a):"):
            cab["relator"] = txt.split(":", 1)[1].strip()
        elif txt.startswith("Relator(a) do ultimo incidente:") or txt.startswith("Relator(a) do último incidente:"):
            cab["relator_ultimo_incidente"] = txt.split(":", 1)[1].strip()
        elif txt.startswith("Origem:"):
            cab["origem"] = txt.split(":", 1)[1].strip()

    etiquetas = [_texto(b) for b in sopa.select(".badge") if _texto(b)]
    if etiquetas:
        cab["etiquetas"] = etiquetas
        for e in etiquetas:
            baixa = e.lower()
            if baixa.startswith("públic"):
                cab["publicidade"] = "Público"
            elif "egredo" in baixa:
                cab["publicidade"] = "Segredo de Justiça"

    proc = sopa.select_one("#descricao-procedencia")
    if proc:
        cab["procedencia"] = _texto(proc)
    return cab


def parse_andamentos(html: str) -> list[dict]:
    sopa = BeautifulSoup(html, "html.parser")
    itens = []
    for item in sopa.select("div.andamento-item"):
        data = _texto(item.select_one(".andamento-data"))
        nome = _texto(item.select_one(".andamento-nome"))
        descricao = ""
        for col in item.select("div.col-md-9"):
            txt = _texto(col)
            if txt:
                descricao = txt
                break
        docs = []
        for a in item.select("a[href*='downloadPeca'], a[href*='downloadTexto']"):
            href = a.get("href", "")
            docs.append(
                {
                    "titulo": _texto(a) or "documento",
                    "url": href if href.startswith("http") else f"{PORTAL}/{href}",
                    "id": (re.search(r"id=(\d+)", href) or [None, None])[1],
                    "tipo": "peca" if "downloadPeca" in href else "texto",
                }
            )
        julgador = _texto(item.select_one(".andamento-julgador"))
        itens.append(
            {
                "data": data,
                "nome": nome,
                "descricao": descricao,
                "julgador": julgador,
                "documentos": docs,
                "invalido": bool(item.select_one(".andamento-invalido")),
            }
        )
    return itens


def parse_lista_simples(html: str, seletor: str) -> list[dict]:
    sopa = BeautifulSoup(html, "html.parser")
    linhas = []
    for tr in sopa.select(seletor):
        cels = [_texto(td) for td in tr.select("td")]
        if any(cels):
            docs = [
                a.get("href")
                for a in tr.select("a[href*='downloadPeca'], a[href*='downloadTexto']")
            ]
            linhas.append({"colunas": cels, "documentos": docs})
    return linhas


# ------------------------------------------------------------------------ coleta
ABAS = {
    "detalhe": "detalhe.asp?incidente={inc}",
    "informacoes": "abaInformacoes.asp?incidente={inc}",
    "andamentos": "abaAndamentos.asp?incidente={inc}&imprimir=",
    "decisoes": "abaDecisoes.asp?incidente={inc}",
    "peticoes": "abaPeticoes.asp?incidente={inc}",
}


def coletar_processo(inc: int, usar_cache: bool) -> dict:
    pasta = DIR_RAW / str(inc)
    pasta.mkdir(parents=True, exist_ok=True)
    paginas: dict[str, str] = {}
    for aba, molde in ABAS.items():
        arquivo = pasta / f"{aba}.html"
        if usar_cache and arquivo.exists():
            paginas[aba] = arquivo.read_text(encoding="utf-8", errors="ignore")
            continue
        html = baixar(f"{PORTAL}/{molde.format(inc=inc)}")
        arquivo.write_text(html, encoding="utf-8")
        paginas[aba] = html
        time.sleep(PAUSA)

    andamentos = parse_andamentos(paginas["andamentos"])
    proc = {
        "incidente": inc,
        "url_portal": f"{PORTAL}/detalhe.asp?incidente={inc}",
        "url_pecas": (
            "https://redir.stf.jus.br/estfvisualizadorpub/jsp/consultarprocessoeletronico/"
            f"ConsultarProcessoEletronico.jsf?seqobjetoincidente={inc}"
        ),
        "cabecalho": parse_cabecalho(paginas["detalhe"]),
        "informacoes": parse_informacoes(paginas["informacoes"]),
        "andamentos": andamentos,
        "decisoes": parse_lista_simples(paginas["decisoes"], "tr"),
        "peticoes": parse_lista_simples(paginas["peticoes"], "tr"),
    }
    return proc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-rede", action="store_true", help="usa o cache em dados/raw")
    ap.add_argument("--sem-descoberta", action="store_true")
    args = ap.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    seeds = {p["incidente"]: p for p in cfg["processos_seed"]}

    cache_desc = RAIZ / "dados" / "descoberta.json"
    descobertos: list[dict] = []
    if cfg["descoberta"]["ativa"] and not (args.sem_rede or args.sem_descoberta):
        descobertos = descobrir_processos(
            cfg["descoberta"]["termos_parte"], cfg["descoberta"].get("somente_relator")
        )
        cache_desc.write_text(
            json.dumps(descobertos, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"descoberta: {len(descobertos)} processos com as partes buscadas")
    elif cache_desc.exists():
        descobertos = json.loads(cache_desc.read_text(encoding="utf-8"))
        print(f"descoberta (cache): {len(descobertos)} processos")

    catalogo: dict[int, dict] = {}
    for d in descobertos:
        catalogo[d["incidente"]] = d
    for inc, s in seeds.items():
        catalogo.setdefault(inc, {"incidente": inc, "rotulo": s.get("rotulo")})
        catalogo[inc]["nota"] = s.get("nota", "")
        catalogo[inc]["seed"] = True

    processos = []
    for inc, meta in sorted(catalogo.items()):
        print(f"  coletando {meta.get('rotulo') or inc} (incidente {inc})…", flush=True)
        try:
            proc = coletar_processo(inc, usar_cache=args.sem_rede)
        except Exception as exc:  # noqa: BLE001
            print(f"    ERRO: {exc}")
            continue
        proc.update({k: v for k, v in meta.items() if k not in proc})
        processos.append(proc)

    relator_alvo = (cfg["descoberta"].get("somente_relator") or "").upper()
    if relator_alvo:
        for p in processos:
            rel = (p.get("cabecalho", {}).get("relator") or "").upper()
            p["do_relator_alvo"] = relator_alvo in rel

    saida = {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "caso": cfg["caso"],
        "marcos": cfg["marcos"],
        "processos": processos,
    }
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(
        json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"ok: {len(processos)} processos → {SAIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
