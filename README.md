# Painel local do Ceará

Dashboard interativo local para os Boletins de Urna do Ceará. O CSV bruto é preservado; o preparo lê em blocos, valida o escopo CE e produz `data/ce_votos.parquet`. O Streamlit consulta essa base com DuckDB. A tabela oficial de locais do TSE fornece nomes, endereços e coordenadas para o mapa.

## Preparar o ambiente (Linux/macOS)

Na raiz do repositório:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Para rodar os testes de desenvolvimento, instale também `requirements-dev.txt`.

## Preparar os dados

Passe o caminho do CSV BWEB do Ceará. Esta opção baixa a tabela oficial de locais do TSE para associar coordenadas; requer internet:

```bash
.venv/bin/python prepare_ce_data.py /home/matheus/converter_arq/caminho/arquivo.csv --download-localities
```

O Parquet será gravado em `data/ce_votos.parquet`. O script processa em blocos e mantém apenas as linhas `SG_UF=CE`. A conversão pode levar alguns minutos e requer espaço para o arquivo Parquet e os dados temporários. Também é possível fornecer uma tabela de locais já baixada:

```bash
.venv/bin/python prepare_ce_data.py /caminho/para/bweb_1t_CE.csv --localities /caminho/para/locais_ce.csv
```

Sem uma tabela de localidades, os filtros, indicadores e gráficos funcionam, mas os pontos não terão coordenadas para aparecer no mapa.

## Abrir o painel

```bash
.venv/bin/python -m streamlit run dashboard.py
```

O Streamlit abrirá o painel no navegador local. O processamento e as consultas eleitorais são locais; o mapa usa tiles raster do OpenStreetMap (sem chave de API) e requer internet para exibir o fundo cartográfico. Os locais são agrupados em clusters para facilitar a leitura inicial; amplie ou clique em um agrupamento para explorar os pontos e abrir o resumo de um local.

## Empacotamento Windows

O instalador distribuível deve ser construído em Windows; PyInstaller não produz
um executável Windows a partir deste Linux. Use Windows com Python 3.12 e Inno
Setup, e rode PowerShell na raiz do projeto:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\windows\build_windows.ps1
```

O script cria um ambiente de build limpo, instala `requirements-build.txt` e
monta `dist\CE2026Dashboard` em modo **onedir**. Para também compilar o instalador
Inno Setup (ISCC precisa estar instalado; o script procura no PATH e nos locais
comuns de instalação):

```powershell
.\windows\build_windows.ps1 -BuildInstaller
```

O instalador resultante fica em `dist\installer`. Ele instala sem exigir
administração, no perfil do usuário, e oferece atalhos do menu Iniciar e da
área de trabalho. O diretório onedir pode ser distribuído sem o instalador.
O pacote inclui `data\ce_votos.parquet` (~68 MiB); não é necessário instalar
Python ou Streamlit na máquina de destino. O launcher grava logs em
`%LOCALAPPDATA%\CE2026Dashboard\logs` e pode ser iniciado também em desenvolvimento
com `python launcher.py`. O painel liga somente em `127.0.0.1`; não fica acessível
pela rede local. O mapa depende de internet para carregar os tiles do OpenStreetMap.
O bundle não é assinado; o SmartScreen/antivírus pode exibir avisos de editor
desconhecido.

### Construir pelo GitHub Actions

Também é possível usar o workflow `Windows Installer` em um repositório GitHub
privado, sem configurar secrets:

1. Crie um repositório **privado** no GitHub e adicione este projeto. Inclua
   `data/ce_votos.parquet` (~71,5 MB) no commit: ele fica abaixo do limite de
   100 MB por arquivo do GitHub, mas o GitHub pode exibir um aviso por ser um
   arquivo grande. Não inclua o CSV original (cerca de 1,2 GB), nem `.venv`,
   `.venv-build`, ou outros ambientes virtuais; não altere `.gitignore` para
   rastrear ambientes.
2. Faça push do branch para o GitHub.
3. No repositório, abra **Actions > Windows Installer > Run workflow** e
   execute o workflow. Ele também pode rodar em pushes para `main` e tags `v*`.
4. Quando terminar, abra a execução e baixe o artifact
   `CE2026Dashboard-Windows-Installer`. O arquivo compactado contém
   `CE2026Dashboard-Setup.exe`.

O artifact é um download associado à execução do workflow, sujeito à retenção
configurada no GitHub; não é uma Release permanente. Os dados eleitorais do TSE
são públicos, mas antes de enviar o repositório e os dados para GitHub, verifique
as políticas legais, de segurança e da sua organização.

## Testes

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q tests/test_dashboard_data.py
.venv/bin/python -m pytest -q tests/test_launcher.py
```

Os testes usam fixtures pequenas e não leem o CSV de produção.
