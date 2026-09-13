@echo off
REM Coleta local + publicacao do painel.
REM Por que local: o portal do STF responde 403 para IP de datacenter, entao o
REM GitHub Actions NAO consegue coletar (descobrimos em 13/09/2026). A nuvem so
REM publica; quem raspa o portal e esta maquina.
REM
REM Uso manual:  coletar_e_publicar.cmd
REM Agendado:    Tarefa do Windows "MasterCounter-Coleta" 2x/dia

cd /d "%~dp0"
echo [%date% %time%] iniciando coleta >> coleta.log

py -3.10 pipeline\coletar.py         >> coleta.log 2>&1 || goto :falhou
py -3.10 pipeline\montar_dados.py    >> coleta.log 2>&1 || goto :falhou
py -3.10 pipeline\analisar_conteudo.py >> coleta.log 2>&1 || goto :falhou
py -3.10 pipeline\montar_mencoes.py  >> coleta.log 2>&1 || goto :falhou

git add docs/dados.json docs/mencoes.json dados/historico.jsonl dados/pecas_vistas.json
git diff --staged --quiet && (
  echo [%date% %time%] sem novidade, nada a publicar >> coleta.log
  exit /b 0
)
git commit -q -m "dados: coleta local %date% %time%" >> coleta.log 2>&1
git push -q origin main >> coleta.log 2>&1 || goto :falhou
echo [%date% %time%] publicado >> coleta.log
exit /b 0

:falhou
echo [%date% %time%] FALHOU - painel publicado foi preservado pelas travas >> coleta.log
exit /b 1
