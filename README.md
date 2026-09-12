# Contador Master

Painel independente que acompanha, **só com dado público**, quanto do caso Banco Master no STF já
está acessível a qualquer pessoa: processos sob relatoria do ministro André Mendonça, andamentos
registrados e quantos deles vêm com documento que dá para abrir sem ser parte no processo.

👉 **Painel:** https://SEU-USUARIO.github.io/master-counter/ (preencher depois de publicar)

## Como rodar

```bash
pip install -r requirements.txt
python pipeline/coletar.py        # baixa do portal do STF
python pipeline/montar_dados.py   # gera docs/dados.json
python -m http.server -d docs 8099
```

No Windows do projeto: `py -3.10` no lugar de `python`.

## Como publicar no GitHub Pages (quando quiser)

O repositório já está iniciado e commitado localmente. Falta só criar o remoto:

**Pelo GitHub Desktop** (não há `gh` instalado nesta máquina): _Add existing repository_ →
aponte para esta pasta → _Publish repository_ (desmarque "Keep this code private") → depois, em
**Settings › Pages** do repositório, escolha **Source: GitHub Actions**.

**Ou pela linha de comando**, se instalar o `gh`:

```bash
gh repo create master-counter --public --source . --push
gh api -X POST repos/:owner/master-counter/pages -f build_type=workflow
```

Depois disso o workflow `.github/workflows/atualizar.yml` roda sozinho duas vezes por dia
(06h e 18h de Brasília), recoleta, commita `docs/dados.json` e republica a página.

## Fontes

- Portal de processos do STF — https://portal.stf.jus.br/processos/
- API pública de partes — `digital.stf.jus.br/integracoes-processos/api/public/partes/processos`

Nenhuma área restrita é acessada. A metodologia e os limites do número estão descritos na própria
página do painel e em [`00-LEIA-PRIMEIRO.md`](00-LEIA-PRIMEIRO.md).

## Licença

Código MIT. Dados são públicos do STF; o tratamento e o painel podem ser reusados com atribuição.
