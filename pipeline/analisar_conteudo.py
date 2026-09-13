"""Baixa as peças públicas dos processos e conta quem é citado em cada uma.

É o que permite responder "o material liberado até agora fala de quem?" — a leva
antiga girava em torno das contas de um ministro; a de 11/09/2026 trouxe nomes de
políticos. Aqui isso vira número.

IMPORTANTE: menção a um nome não diz nada sobre culpa, investigação ou suspeita.
O que se conta é a aparição do nome no texto de um documento público.

Uso:  py -3.10 pipeline/analisar_conteudo.py [--limite N] [--sem-download]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests
import urllib3

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parent.parent
PROCESSOS = RAIZ / "dados" / "processos.json"
NOMES = RAIZ / "config" / "nomes.json"
DIR_PECAS = RAIZ / "dados" / "pecas"
SAIDA = RAIZ / "dados" / "mencoes.json"

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
}
MAX_BYTES = 120_000_000  # peça maior que isso é registrada e não baixada
VERIFICAR_TLS = True


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t)


def baixar_peca(url: str, destino: Path) -> tuple[bool, int]:
    global VERIFICAR_TLS
    if destino.exists() and destino.stat().st_size > 0:
        return True, destino.stat().st_size
    for tentativa in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=180, verify=VERIFICAR_TLS, stream=True)
            r.raise_for_status()
            tamanho = int(r.headers.get("Content-Length") or 0)
            if tamanho > MAX_BYTES:
                return False, tamanho
            destino.write_bytes(r.content)
            return True, destino.stat().st_size
        except requests.exceptions.SSLError:
            if VERIFICAR_TLS:
                VERIFICAR_TLS = False
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                print("    aviso: TLS nao verificavel nesta maquina; seguindo sem verificacao")
        except Exception as exc:  # noqa: BLE001
            if tentativa == 2:
                print(f"    erro em {url}: {exc}")
            time.sleep(2 + 2 * tentativa)
    return False, 0


def baixar_em_memoria(url: str) -> bytes | None:
    """Baixa a peça sem gravar nada em disco — para quem não quer acumular PDF."""
    global VERIFICAR_TLS
    for tentativa in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=180, verify=VERIFICAR_TLS)
            r.raise_for_status()
            return r.content
        except requests.exceptions.SSLError:
            if VERIFICAR_TLS:
                VERIFICAR_TLS = False
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:  # noqa: BLE001
            time.sleep(2 + 2 * tentativa)
    return None


def extrair_de_bytes(conteudo: bytes, tipo: str) -> tuple[str, int]:
    if tipo == "texto":
        return limpar_rtf(conteudo.decode("latin-1", errors="ignore")), 1
    import fitz  # PyMuPDF

    try:
        with fitz.open(stream=conteudo, filetype="pdf") as doc:
            return chr(10).join(p.get_text() for p in doc), doc.page_count
    except Exception:  # noqa: BLE001
        return "", 0


def limpar_rtf(bruto: str) -> str:
    limpo = re.sub(r"\'([0-9a-f]{2})", lambda m: bytes.fromhex(m.group(1)).decode("latin-1"), bruto)
    limpo = re.sub(r"\[a-z]+-?\d* ?", " ", limpo)
    return re.sub(r"[{}]", " ", limpo)


def extrair_texto(caminho: Path) -> tuple[str, int]:
    """Devolve (texto, páginas). Aceita PDF (PyMuPDF) e RTF (texto cru)."""
    if caminho.suffix.lower() == ".rtf":
        bruto = caminho.read_text(encoding="latin-1", errors="ignore")
        limpo = re.sub(r"\\'([0-9a-f]{2})", lambda m: bytes.fromhex(m.group(1)).decode("latin-1"), bruto)
        limpo = re.sub(r"\\[a-z]+-?\d* ?", " ", limpo)
        limpo = re.sub(r"[{}]", " ", limpo)
        return limpo, 1
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("PyMuPDF nao instalado: pip install pymupdf")
        return "", 0
    try:
        with fitz.open(caminho) as doc:
            return "\n".join(pagina.get_text() for pagina in doc), doc.page_count
    except Exception as exc:  # noqa: BLE001
        print(f"    erro ao ler {caminho.name}: {exc}")
        return "", 0


def medir(reg: dict, texto: str, paginas: int, alvos: list) -> dict:
    """Preenche páginas, tipo de peça e contagem de nomes a partir do texto extraído."""
    if not reg["baixado"]:
        reg.update({"paginas": 0, "caracteres": 0, "sem_texto": None, "substantiva": None, "mencoes": {}})
        return reg
    norm = normalizar(texto)
    titulo = normalizar(reg["titulo"])
    reg["paginas"] = paginas
    reg["caracteres"] = len(texto)
    # PDF digitalizado sem OCR: muitas páginas, quase nenhum texto extraível
    reg["sem_texto"] = bool(paginas and len(texto) / max(1, paginas) < 120)
    # peça de conteúdo x expediente de cartório
    reg["substantiva"] = bool(
        re.search(r"(decisao|acordao|relatorio|parecer|manifestacao|peticao|sentenca)", titulo)
        or paginas >= 5
    )
    reg["mencoes"] = {
        nome: total
        for nome, _papel, padroes in alvos
        if (total := sum(len(p.findall(norm)) for p in padroes))
    }
    return reg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=0, help="processa só as N primeiras peças")
    ap.add_argument("--sem-download", action="store_true", help="usa só o que já está em dados/pecas")
    ap.add_argument(
        "--nao-guardar",
        action="store_true",
        help="lê as peças na memória e não grava PDF nenhum em disco",
    )
    args = ap.parse_args()

    cfg = json.loads(NOMES.read_text(encoding="utf-8"))
    alvos = [
        (n["nome"], n["papel"], [re.compile(rf"\b{re.escape(normalizar(v))}\b") for v in n["variantes"]])
        for n in cfg["nomes"]
    ]

    dados = json.loads(PROCESSOS.read_text(encoding="utf-8"))
    tarefas = []
    for p in dados["processos"]:
        # mesmo recorte do painel: só os processos do caso (semente ou do relator alvo)
        if not (p.get("seed") or p.get("do_relator_alvo")):
            continue
        for a in p.get("andamentos", []):
            for doc in a.get("documentos", []):
                if doc.get("id"):
                    tarefas.append(
                        {
                            "id": doc["id"],
                            "titulo": doc["titulo"],
                            "url": doc["url"],
                            "tipo": doc["tipo"],
                            "incidente": p["incidente"],
                            "processo": (p.get("cabecalho") or {}).get("rotulo") or p.get("rotulo"),
                            "data_andamento": a["data"],
                            "andamento": a["nome"],
                        }
                    )
    vistos, unicas = set(), []
    for t in tarefas:
        if t["id"] not in vistos:
            vistos.add(t["id"])
            unicas.append(t)
    if args.limite:
        unicas = unicas[: args.limite]

    DIR_PECAS.mkdir(parents=True, exist_ok=True)
    print(f"{len(unicas)} peças únicas a processar")

    saida = []
    for i, t in enumerate(unicas, 1):
        ext = ".rtf" if t["tipo"] == "texto" else ".pdf"
        caminho = DIR_PECAS / f"{t['id']}{ext}"

        if args.nao_guardar:
            conteudo = baixar_em_memoria(t["url"])
            time.sleep(0.4)
            reg = dict(t, bytes=len(conteudo or b""), baixado=bool(conteudo))
            texto, paginas = extrair_de_bytes(conteudo, t["tipo"]) if conteudo else ("", 0)
            saida.append(medir(reg, texto, paginas, alvos))
            if i % 25 == 0 or i == len(unicas):
                print(f"  {i}/{len(unicas)} peças", flush=True)
            continue

        if not caminho.exists() and not args.sem_download:
            ok, tamanho = baixar_peca(t["url"], caminho)
            time.sleep(0.4)
        else:
            ok, tamanho = caminho.exists(), caminho.stat().st_size if caminho.exists() else 0

        reg = dict(t, bytes=tamanho, baixado=bool(ok and caminho.exists()))
        if reg["baixado"]:
            texto, paginas = extrair_texto(caminho)
            norm = normalizar(texto)
            reg["paginas"] = paginas
            reg["caracteres"] = len(texto)
            # PDF digitalizado sem OCR: muitas páginas, quase nenhum texto extraível
            reg["sem_texto"] = bool(paginas and len(texto) / max(1, paginas) < 120)
            # peça de conteúdo x expediente: decisão/acórdão/relatório, ou volume de texto
            titulo = normalizar(reg["titulo"])
            reg["substantiva"] = bool(
                re.search(r"(decisao|acordao|relatorio|parecer|manifestacao|peticao|sentenca)", titulo)
                or paginas >= 5
            )
            reg["mencoes"] = {
                nome: total
                for nome, _papel, padroes in alvos
                if (total := sum(len(p.findall(norm)) for p in padroes))
            }
        else:
            reg.update({"paginas": 0, "caracteres": 0, "sem_texto": None, "substantiva": None, "mencoes": {}})
        saida.append(reg)

        if i % 25 == 0 or i == len(unicas):
            print(f"  {i}/{len(unicas)} peças", flush=True)

    com_texto = [r for r in saida if r["caracteres"] > 0 and not r["sem_texto"]]
    resumo = {
        "pecas": len(saida),
        "baixadas": sum(1 for r in saida if r["baixado"]),
        "com_texto": len(com_texto),
        "digitalizadas_sem_ocr": sum(1 for r in saida if r["sem_texto"]),
        "paginas": sum(r["paginas"] for r in saida),
        "substantivas": sum(1 for r in saida if r.get("substantiva")),
    }
    SAIDA.write_text(
        json.dumps(
            {
                "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "observacao": cfg["observacao"],
                "papeis": cfg["papeis"],
                "papel_do_nome": {n["nome"]: n["papel"] for n in cfg["nomes"]},
                "resumo": resumo,
                "pecas": saida,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"ok: {resumo} -> {SAIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
