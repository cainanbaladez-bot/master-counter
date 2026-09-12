# Contador Master

Painel independente que acompanha, **só com dado público**, quanto do caso Banco Master no STF já
está acessível a qualquer pessoa: processos sob relatoria do ministro André Mendonça, andamentos
registrados e quantos deles vêm com documento que dá para abrir sem ser parte no processo.

👉 **Painel:** https://cainanbaladez-bot.github.io/master-counter/

> Painel independente, sem revisão de profissional da área jurídica. Os números são leitura
> automatizada dos andamentos e peças publicados pelo STF.

## Como rodar

```bash
pip install -r requirements.txt
python pipeline/coletar.py        # baixa do portal do STF
python pipeline/montar_dados.py   # gera docs/dados.json
python -m http.server -d docs 8099
```

No Windows do projeto: `py -3.10` no lugar de `python`.

## Publicação

Já está no ar: repositório [cainanbaladez-bot/master-counter](https://github.com/cainanbaladez-bot/master-counter),
Pages servindo a pasta `docs/` via GitHub Actions.

O workflow `.github/workflows/atualizar.yml` roda sozinho duas vezes por dia (06h e 18h de
Brasília): recoleta o portal, relê as peças, regenera `docs/dados.json` e `docs/mencoes.json`,
commita e republica a página. Para rodar na hora, use o botão *Run workflow* na aba Actions.

## Fontes

- Portal de processos do STF — https://portal.stf.jus.br/processos/
- API pública de partes — `digital.stf.jus.br/integracoes-processos/api/public/partes/processos`

Nenhuma área restrita é acessada. A metodologia e os limites do número estão descritos na própria
página do painel e em [`00-LEIA-PRIMEIRO.md`](00-LEIA-PRIMEIRO.md).

## Licença

Código MIT. Dados são públicos do STF; o tratamento e o painel podem ser reusados com atribuição.
