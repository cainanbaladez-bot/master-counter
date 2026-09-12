# Contador Master — leia primeiro

Painel público (GitHub Pages) que mede **quanto do caso Banco Master no STF já está acessível a
qualquer cidadão**: quantos andamentos existem nos processos sob relatoria do ministro André
Mendonça e em quantos deles há documento que dá para abrir sem ser parte no processo.

Nasceu de uma piada de rede social ("um contador da porcentagem de arquivos que o Mendonça vai
liberando"), mas o painel é sério: só dado público, coleta reproduzível, metodologia declarada na
própria página.

---

## Mapa

```
Master-counter/
  config/caso.json          processos-semente, termos de descoberta e MARCOS (editar à mão)
  config/nomes.json         nomes acompanhados + variantes de grafia (editar à mão)
  pipeline/
    coletar.py              portal do STF -> dados/processos.json (+ cache em dados/raw/)
    montar_dados.py         processos.json -> docs/dados.json (+ dados/historico.jsonl)
    analisar_conteudo.py    baixa as peças (PDF/RTF), extrai texto, conta nomes -> dados/mencoes.json
    montar_mencoes.py       -> docs/mencoes.json (+ dados/pecas_vistas.json, que define as LEVAS)
  dados/
    raw/<incidente>/*.html  cache bruto das abas do portal (fora do git)
    pecas/<id>.pdf|.rtf     cache das peças baixadas (fora do git; ~0,4 MB cada)
    processos.json          estado bruto normalizado (fora do git)
    historico.jsonl         1 linha por coleta: e daqui que sai a curva do contador
    pecas_vistas.json       id da peça -> data em que apareceu (VERSIONADO: define as levas)
  docs/
    index.html              o painel (arquivo único, sem dependências)
    dados.json              contador, série e processos (versionado)
    mencoes.json            nomes citados, levas e matriz processo x nome (versionado)
  .github/workflows/atualizar.yml   cron 2x/dia -> coleta -> commit -> deploy Pages
```

Ambiente: **`py -3.10`** no Windows do Cainan (`pip install -r requirements.txt`).
No GitHub Actions roda em 3.11.

---

## Fluxo de ponta a ponta

1. **Descoberta** — API pública de partes do STF
   (`digital.stf.jus.br/integracoes-processos/api/public/partes/processos?nome=VORCARO&…`)
   devolve todos os processos em que a parte aparece, já com `processoId` (o *incidente*) e o
   campo `processoPublicidade` (Público / Segredo de Justiça).
2. **Coleta** — para cada incidente, baixa as abas server-side do portal:
   `detalhe.asp`, `abaInformacoes.asp`, `abaAndamentos.asp?imprimir=`, `abaDecisoes.asp`,
   `abaPeticoes.asp`. Cada andamento vira `{data, nome, descrição, documentos[]}`; documento é um
   link `downloadPeca.asp?id=…` (PDF) ou `downloadTexto.asp` (RTF).
3. **Agregação** — `montar_dados.py` calcula o contador (andamentos com documento / total),
   a série diária, o acumulado, os tipos de andamento e acrescenta uma linha em `historico.jsonl`.
4. **Publicação** — o Action commita `docs/dados.json` + `historico.jsonl` e publica `docs/` no
   GitHub Pages.

### Nomes citados nas peças (seção "Quem aparece")

`analisar_conteudo.py` baixa cada peça pública (média 0,4 MB; ~1 s por download), extrai o texto com
PyMuPDF (RTF é lido cru) e conta ocorrências dos nomes de `config/nomes.json`, normalizando acentos.
Peça digitalizada sem OCR é marcada `sem_texto` e não conta nome nenhum — por isso os totais por
pessoa são **piso, não teto**.

Três cuidados que estão escritos na página e não devem ser removidos:
- **citação não é acusação** — o nome aparecer num documento não diz nada sobre investigação;
- a **data do andamento é a de juntada**, não a de levantamento do sigilo (peça de fevereiro
  liberada em setembro continua datada de fevereiro);
- por isso as **levas** são medidas pela observação do pipeline: `pecas_vistas.json` guarda quando
  cada id de peça apareceu pela primeira vez. A 1ª coleta inteira é "linha de base"; da segunda em
  diante, cada coleta mostra o que entrou e quais nomes vieram junto. **Esse arquivo é versionado —
  se ele se perder, perde-se a série de levas.**

### O que o contador é e o que não é
- **É**: % de andamentos que trazem documento baixável no portal público do STF.
- **Não é**: % dos ~4 mil arquivos / 26 GB citados na imprensa. O STF não publica o total de peças
  de um processo em formato aberto; peça restrita simplesmente não aparece com link. Por isso o
  denominador é o *andamento*, não o *arquivo* — e isso está escrito na página.
- A lista completa de peças (incluindo as restritas) existe no visualizador
  `redir.stf.jus.br/estfvisualizadorpub/...?seqobjetoincidente=<incidente>`, que é JSF atrás de
  proteção anti-bot: abre no navegador, não abre por `requests`. O painel linka para ele em cada
  processo ("peças"), mas **não** o raspa. Se um dia valer a pena, o caminho é Playwright.

---

## Detalhes que custaram tempo (não redescobrir)

- O portal devolve **403** para `User-Agent` curto. Precisa do UA completo de Chrome.
- Busca por classe/número funciona por querystring: `listarProcessos.asp?classe=Pet&numeroProcesso=15556`
  (classe com a grafia do combo: `Pet`, `Inq`, `HC` — `INQ` maiúsculo devolve "não encontrado").
- `abaAndamentos.asp` do Pet 15556 tem ~3,6 MB. Coleta completa leva alguns minutos; há pausa de
  1,2 s entre requisições de propósito.
- Na máquina do Cainan a verificação TLS do portal falha (proxy/antivírus). O coletor detecta o
  `SSLError`, avisa e segue sem verificar. No Actions isso nunca dispara.
- Incidentes já conhecidos: Pet 15556 = 7514886 · Inq 5026 = 7473347 · Inq 5035 = 7498168 ·
  Pet 15504 = 7509527 · Pet 15499 = 7509111 · Pet 15198 = 7473336.

---

## Tarefas comuns

| Quero… | Faço |
|---|---|
| Atualizar os números agora | `py -3.10 pipeline/coletar.py && py -3.10 pipeline/montar_dados.py` |
| Atualizar os nomes citados | `py -3.10 pipeline/analisar_conteudo.py && py -3.10 pipeline/montar_mencoes.py` |
| Reler as peças sem rebaixar | `py -3.10 pipeline/analisar_conteudo.py --sem-download` |
| Acompanhar mais um nome | editar `config/nomes.json` e reler as peças |
| Reprocessar sem bater no STF | `py -3.10 pipeline/coletar.py --sem-rede` (usa `dados/raw/`) |
| Acrescentar um processo à mão | editar `config/caso.json` → `processos_seed` |
| Registrar um marco (cobrança, decisão) | editar `config/caso.json` → `marcos` (com `fonte`) |
| Ver o painel local | `py -3.10 -m http.server -d docs 8099` |

## Pendências
- Publicar no GitHub (repo + Pages) — ver README.
- Avaliar coleta do visualizador de peças por Playwright, para ter o denominador real
  (peças restritas x liberadas) em vez do proxy por andamento.
