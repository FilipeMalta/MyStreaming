# MyStreaming · Trilha

Plataforma local para assistir aos cursos disponíveis na sua conta do Telegram, com menu de cursos, lista lateral, retomada, progresso por aula e preparação de vídeos para reprodução pelo disco.

## Executar no Windows

Requer Python 3.11 ou superior no PATH. As dependências são instaladas automaticamente em um ambiente virtual na primeira execução.

1. Clone o repositório e abra a pasta no VS Code.
2. Execute `conectar.bat` e informe seu API ID, API Hash, telefone e código de login **somente no terminal local**. Obtenha as credenciais em [my.telegram.org/apps](https://my.telegram.org/apps).
3. Execute `configurar-cursos.bat` para cadastrar seus convites privados.
4. Execute `iniciar.bat`. O navegador abre quando o servidor responde em [127.0.0.1:8765](http://127.0.0.1:8765).
5. Escolha o curso em **Meus cursos** e clique em **Sincronizar Telegram**.

Os índices iniciais incluem Autodidata Fluente e WISE UP Online. O acesso aos vídeos depende da sua conta e dos canais configurados. Convites, credenciais e vídeos não são distribuídos neste repositório.

## Recursos

- Menu para alternar cursos, com progresso e última aula independentes.
- Organização por módulos e hashtags do Telegram.
- Reprodução com HTTP Range, velocidade e retomada.
- Aceleração nativa com cryptg.
- **Preparar aula** para baixar um vídeo e reproduzi-lo pelo arquivo local.
- Cache de 2 GB por padrão, ajustável com `TRILHA_CACHE_MB`.
- Materiais de apoio identificados por `#Doc`, para download separado.
- Exportação do progresso por curso em JSON.

O servidor escuta somente em localhost. Não foi preparado para exposição pública ou uso com vários usuários.

## Dados locais

`data/` contém as credenciais, a sessão da conta, o banco de progresso e o cache. Essa pasta é ignorada pelo Git. Mantenha-a privada; para fazer backup, copie-a com o servidor fechado. Não publique arquivos de sessão nem os convites dos canais.

Os convites também podem ser informados pelas variáveis `TRILHA_AUTODIDATA_INVITE` e `TRILHA_WISE_UP_INVITE` antes da primeira criação do banco. Para atualizar convites já cadastrados, use `configurar-cursos.bat`.

## Desenvolvimento e testes

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python app.py
```

As tarefas do VS Code estão em `.vscode/tasks.json`. Para depurar com F5, instale a extensão Python Debugger da Microsoft.

Consulte [LEIA-ME.md](LEIA-ME.md) para detalhes sobre cache, índices e limitações dos formatos de vídeo.
