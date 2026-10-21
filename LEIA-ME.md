# Trilha · Biblioteca de cursos

Sala de aula local com menu para alternar entre cursos, player, lista lateral, progresso individual e preparação de aulas no computador.

## Cursos e troca pelo menu

Use **Meus cursos** no topo da página para alternar entre Autodidata Fluente e WISE UP Online · Flávio Augusto. O curso escolhido e a última aula de cada curso são lembrados neste navegador. A mesma sessão do Telegram atende aos dois cursos.

Cada curso tem sua própria sincronização, aulas, módulos, progresso e exportação. O Autodidata mantém seu índice original de 88 aulas. O WISE UP usa o sumário fornecido: 519 códigos, de #F001 a #F519, em 24 módulos de Cities, Travel e Business. Hashtags ausentes na importação aparecem em um aviso e no módulo correspondente; não são substituídas por vídeos fictícios. A duração e o tamanho informados no catálogo podem diferir da soma dos vídeos disponíveis; a página mostra também a duração efetivamente importada.

Materiais identificados por #Doc são exibidos separadamente, acima da busca de aulas. O link inicia o download do arquivo original pelo navegador; não abre nem executa arquivos compactados. Esses materiais não entram na contagem de aulas concluídas.

Na primeira sincronização, o sistema consulta o convite cadastrado. Se a conta ainda não participa, tenta entrar usando esse convite. Quando o canal exige aprovação, mostra a solicitação pendente; é necessário sincronizar novamente depois da aprovação. Um convite expirado exige atualização do cadastro.

A importação lê somente os metadados. Não baixa os 173,1 GB do WISE UP de uma só vez. O streaming e **Preparar aula** continuam funcionando individualmente por vídeo, com o cache compartilhado limitado a 2 GB por padrão.

## Como usar no Windows

1. Tenha Python 3.11 ou superior instalado e disponível no PATH.
2. Feche qualquer instância do servidor e execute **conectar.bat**. As bibliotecas são instaladas automaticamente na primeira vez.
3. Obtenha seu API ID e API Hash em [my.telegram.org/apps](https://my.telegram.org/apps). É o cadastro de um aplicativo pessoal na API do Telegram. Informe os dois no terminal local; não envie esses dados pelo chat.
4. Entre com seu telefone com código do país, código de login e senha de duas etapas, se houver. A conta deve participar do canal. O assistente consulta o convite sem ingressar automaticamente. Se necessário, permite escolher outro canal da sua conta.
5. Execute **iniciar.bat** e acesse [http://127.0.0.1:8765](http://127.0.0.1:8765).
6. Clique em **Sincronizar Telegram**. O sistema importa os metadados dos vídeos de todo o histórico do canal. Canais grandes podem demorar; o botão mostra a contagem. Sincronizar novamente preserva o progresso existente.
7. Escolha uma aula na lista lateral. O player tem controle de velocidade, anterior/próxima, retomada e conclusão manual. Ao chegar ao fim, marca a aula como concluída. A próxima aula exige um clique.

O Telegram Desktop aberto não fornece sua sessão a esta aplicação. O primeiro login é separado. A sessão é reutilizada nas próximas execuções.

## Organização e progresso

- As hashtags são lidas sem distinguir maiúsculas de minúsculas; #F1 e #F01 representam a mesma posição. A sequência usa o número da hashtag, não o nome do arquivo ou a data de publicação.
- O índice do usuário define os 13 módulos. Vídeos sem código reconhecido aparecem em “Outros vídeos do canal”.
- Se houver mais de um vídeo com a mesma hashtag, todos aparecem em ordem de mensagem. O total de aulas conta os códigos únicos. Uma aula com várias partes só é contabilizada como concluída quando todas as partes importadas foram concluídas.
- A posição é salva no SQLite a cada oito segundos, ao pausar e ao sair da página. Uma interrupção abrupta pode perder os segundos mais recentes.
- O botão de exportação gera um JSON de consulta/backup. Não há importador de JSON. Para restaurar a instalação inteira, copie a pasta **data** com o servidor fechado.
- Mensagens removidas do canal não são apagadas automaticamente do catálogo; ao tentar reproduzi-las, o servidor informa que não estão disponíveis.

## Streaming e limites

No modo streaming, o servidor entrega trechos do vídeo do Telegram ao navegador usando HTTP Range. É possível avançar para outro ponto sem baixar todo o arquivo primeiro. O cryptg acelera a descriptografia em código nativo. A velocidade ainda depende da conexão e dos limites do Telegram.

Se uma aula travar, selecione **Preparar aula**. A reprodução é pausada enquanto o vídeo inteiro é baixado, e a tela mostra a porcentagem. Ao concluir, pressione Play: a reprodução e as buscas passam a usar o arquivo local, sem depender da velocidade do Telegram. Uma aula é preparada por vez. Não há transcodificação; formatos incompatíveis continuam exigindo conversão externa.

O cache fica em `data/video-cache`, limitado a 2 GB por padrão. Ao preparar novas aulas, arquivos de cache antigos são removidos conforme necessário; seu progresso e sua sessão não são removidos. Arquivos em uso no Windows podem impedir a liberação de espaço. A variável `TRILHA_CACHE_MB` ajusta esse limite. Uma aula maior que o limite pode usar o streaming, mas não pode ser preparada. O servidor só usa arquivos cujo download foi concluído e cujo tamanho confere. Arquivos incompletos não são servidos.

É preciso manter o servidor funcionando nos dois modos. A primeira preparação exige internet. MP4 com H.264/AAC costuma ser adequado ao navegador; a compatibilidade depende do arquivo original.

O servidor escuta somente em 127.0.0.1:8765. Não foi preparado para publicação na internet nem para vários usuários. Ele consulta mensagens e baixa trechos dos vídeos; não envia mensagens ao canal.

A pasta **data** contém `config.json` com as credenciais da API, `telegram.session` com a sessão da conta e `trilha.db` com o progresso. Não compartilhe essa pasta nem inclua esses arquivos em repositórios. Para revogar a sessão, use a área Dispositivos do Telegram.

## Desenvolvimento

### Abrir e rodar no VS Code

Execute **abrir-vscode.bat** ou abra o arquivo **trilha.code-workspace** no VS Code. O ambiente Python local já está preparado nesta máquina.

O iniciador abre a página somente depois da resposta do backend. Após alterar Python, reinicie a tarefa do servidor. Para atualizar HTML/CSS/JavaScript, atualize a página no navegador. A API `/api/health` identifica a versão 1.3.0 e informa se o acelerador está ativo. As APIs de módulos, aulas, status, sincronização e exportação aceitam `course_id=autodidata` ou `course_id=wise-up`.

No menu **Terminal → Executar Tarefa**, escolha **Trilha: conectar Telegram** para fazer o primeiro login. Depois escolha **Trilha: iniciar servidor** e abra http://127.0.0.1:8765. Pare o servidor com Ctrl+C antes de executar a configuração da conta. As tarefas funcionam sem instalar extensões no editor.

Para depurar com F5, use a configuração **Trilha: servidor local**. Esse recurso requer a extensão Python Debugger da Microsoft. O terminal também pode executar os comandos abaixo sem ativar o ambiente virtual.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python connect.py
.venv\Scripts\python app.py
.venv\Scripts\python -m unittest discover -s tests -v
```

É possível usar a variável `TRILHA_DATA_DIR` para separar dados de teste. Os testes usam um cliente Telegram simulado; não entram na conta real.

Referências: [credenciais da API](https://core.telegram.org/api/obtaining_api_id), [Telethon e iter_download](https://docs.telethon.dev/en/stable/modules/client.html#telethon.client.downloads.DownloadMethods.iter_download).
