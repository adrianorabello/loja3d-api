# Testes automatizados com Postman

## Importar e selecionar o ambiente

No Postman, use **Import** para importar:

1. [Coleção Printoy 3D](./Printoy3D.postman_collection.json).
2. [Ambiente remoto](./Printoy3D.production.postman_environment.json) ou
   [ambiente local](./Printoy3D.local.postman_environment.json).

Selecione o ambiente importado no seletor do Postman. Todas as requisições usam
`{{baseUrl}}`: o ambiente remoto já aponta para `https://api.printoy3d.com`.
Para outro servidor, altere apenas essa variável, sem barra final nem `/api/v1`.
O ambiente local usa `http://localhost:8000`.

## Execução segura no ambiente remoto

Abra a coleção e selecione **Run collection**. Mantenha a ordem das pastas,
execute desde a pasta **00 - Inicializacao e health** e use uma iteração.

Por padrão, `allowWrites=false`: são executadas 18 requisições de leitura pública
e verificações de acesso negado. As demais requisições são ignoradas antes de
serem enviadas, com aviso no Postman Console. **Ignoradas não significa aprovadas:
esse modo não valida o backend inteiro.**

O endpoint de categorias pode inicializar as categorias padrão se a base estiver
vazia, conforme o comportamento atual do backend. Mesmo o modo de leitura não
garante ausência dessa inicialização.

## Executar o fluxo completo

**Prefira um servidor e uma base de dados exclusivos para testes.** `baseUrl`
seleciona o servidor, não a base MongoDB: a base é configurada no backend.
Não habilite alterações na produção sem avaliar os efeitos abaixo.

Configure no ambiente do Postman:

| Variável | Valor |
|---|---|
| `baseUrl` | Origem do servidor, por exemplo `https://api.printoy3d.com` |
| `allowWrites` | `true`, em minúsculas |
| `adminEmail` | E-mail de um administrador existente |
| `adminPassword` | Senha desse administrador, somente no valor local do Postman |
| `testEmailDomain` | `example.com` por padrão; use um domínio/inbox de testes autorizado para validar envio real |

Execute a coleção inteira, em ordem, com uma iteração. Não paralelize as
requisições: há dependências entre cadastro, sessão, criação, atualização e
eliminação de produtos. Tokens, senhas dos clientes e identificadores gerados
ficam em variáveis locais da execução, sem serem exportados no ambiente.

### Cobertura

A coleção inclui as **78 operações HTTP de negócio/health atualmente publicadas**
no OpenAPI, considerando método + caminho, inclusive os aliases:

- Health na raiz e em `/api/v1`.
- Cadastro, registro, login, sessão, refresh, fallback por access token, rotação,
  rejeição de refresh reutilizado, logout e sign-out.
- Perfil, moradas, telefone, data de nascimento, formato Fuse, persistência,
  proteção contra elevação de papel e alteração direta de e-mail.
- Categorias, catálogo público, detalhe por slug, pesquisa, filtro por categoria
  e ordenação por preço na consulta filtrada.
- CRUD administrativo e aliases `/product`, envelope Fuse, conflito de slug,
  preço, stock, visibilidade de inativos, eliminação e confirmação de ausência.
- Navegação, mensagens, notificações e atalhos.
- As dez operações novas de pedidos personalizados, exclusivamente em `/api/v1`:
  criação, lista/detalhe do proprietário, mensagens e ações do cliente;
  lista/detalhe administrativo, mensagens, publicação de orçamentos e transições.
  A subpasta **Pedidos personalizados - fluxo ordenado**, dentro da API v1,
  reutiliza os mesmos clientes e sessão administrativa da execução, antes do
  logout. Verifica isolamento do segundo cliente (`404`), papéis (`403`),
  pesquisa/paginação, versões obsoletas (`409`), informação adicional,
  mensagens, revisões de orçamento, aprovação sem mensagem, pagamento manual,
  produção/pausa, tracking opcional (validado quando informado), entrega, cancelamento e rejeição.
- Caminhos de erro 400, 401, 403, 404, 409 e 422, conforme o cenário.
- Pedidos de reenvio de verificação, recuperação de senha e alteração de e-mail.
  A confirmação desses três fluxos usa tokens inválidos na execução automática;
  os casos de sucesso com tokens reais são opcionais.

Isto cobre os endpoints, não todas as combinações de entrada, estados de conta,
falhas de infraestrutura, limites de tráfego ou todas as opções de ordenação.
Swagger, ReDoc e o documento OpenAPI não são endpoints de negócio desta suíte.

### Dados e efeitos da execução completa

- Cria **quatro clientes por execução**, com e-mails únicos. Eles permanecem na
  base: **não existe endpoint para eliminar contas**. A coleção não acessa o
  MongoDB diretamente nem apaga utilizadores existentes.
- Envia e-mails para as contas de teste e os novos endereços de teste.
  O backend de e-mail precisa funcionar. Em desenvolvimento, `EMAIL_BACKEND=console`
  permite acompanhar os links nos logs; não é permitido em produção.
- Cria quatro produtos e elimina apenas os IDs capturados na própria execução.
  Se houver falha ou interrupção antes da limpeza, procure pelos slugs
  `postman-v1-...` e `postman-legacy-...` no painel administrativo. Não existe
  rollback garantido depois de uma execução interrompida.
- Cria três pedidos personalizados: um entregue, um cancelado pelo cliente e
  outro rejeitado pelo administrador. São preservados para auditoria, incluindo
  revisões e histórico; não existe endpoint para eliminar pedidos. Todos usam
  o `runId` no título. Só IDs capturados nessa execução podem ser usados pelo
  fluxo; IDs antigos são limpos na inicialização. As versões/IDs são locais à
  execução, não são exportados para os ambientes.
- Os pedidos não cobram, enviam notificações, fazem uploads ou emitem
  reembolsos. `referenceLinks` são URLs externas HTTP(S), sem credenciais e sem
  fetch pelo servidor. Confirmação de pagamento e cancelamento são manuais e
  exigem motivos; cancelar após pagamento **não** faz reembolso automático.
  Criar ou executar ações pelas rotas do cliente requer `CUSTOMER`.
  Consulte a [matriz de transições por ator/precondições](../docs/print-requests.md).
- O sign-out completo é feito apenas nos novos clientes. No administrador é
  revogado somente o refresh token obtido pelo teste, preservando outras sessões.
- Tokens de acesso JWT já emitidos continuam válidos até expirar: logout e
  sign-out revogam refresh tokens, não invalidam imediatamente access tokens.

Não exporte ambientes preenchidos com senhas/tokens nem os envie ao Git.

### Limitação de requisições

O backend compartilha limites por IP entre rotas e aliases. Uma execução completa
faz oito tentativas de login, quatro cadastros válidos, dois cadastros inválidos e
duas tentativas duplicadas. Use **Delay = 1500 ms** para evitar rajadas, mas isso
não garante ausência de 429 se outras pessoas estiverem a usar o mesmo IP.
Não faça várias iterações seguidas: o cadastro permite dez tentativas por hora
e os fluxos de e-mail têm janelas de quinze minutos. Se receber **429**, aguarde
a janela do limitador; não trate esse resultado como aprovação. Para execuções
frequentes, use apenas um backend isolado com `RATE_LIMIT_ENABLED=false`.

## Confirmações opcionais com e-mail real

A pasta **04 - OPCIONAL - Tokens reais recebidos por email** é ignorada enquanto
as variáveis correspondentes estiverem vazias. Para testar um caso de sucesso:

1. Use exclusivamente uma conta de teste e obtenha um token novo pelo e-mail
   enviado ou pelo log do backend `console`.
2. Configure `allowWrites=true`, as credenciais administrativas e a variável:
   - `verificationToken`: token do link de confirmação de e-mail.
   - `emailChangeToken`: token do link de alteração de e-mail. Informe também
     `emailFlowAccessToken`, access token da conta que solicitou a alteração.
   - `passwordResetToken`: token do link de recuperação. Informe também
     `newPassword` com pelo menos oito caracteres.
3. Execute **individualmente** a requisição correspondente na pasta opcional.
   Não precisa executar toda a coleção novamente.
4. Limpe as variáveis após usar. Os tokens são de uso único: repetir a requisição
   com o mesmo token deverá falhar. A redefinição altera a senha e revoga todos
   os refresh tokens dessa conta; a confirmação de novo e-mail altera o login.

A coleção não consegue ler a caixa de e-mail nem os logs do servidor remoto.
Um HTTP 200 no pedido de envio confirma a resposta da API, não a entrega na caixa.

## Automatizar pela linha de comando

Requer Node.js/npm. Na pasta `loja3d-api`, o modo seguro pode ser executado sem
instalação global:

```bash
npm exec --yes --package=newman@6.2.1 -- newman run \
  postman/Printoy3D.postman_collection.json \
  -e postman/Printoy3D.production.postman_environment.json \
  --delay-request 1500 \
  --reporters cli,junit \
  --reporter-junit-export postman/printoy-postman-results.xml
```

Para trocar a URL, acrescente `--env-var 'baseUrl=http://localhost:8000'`.
Para habilitar o fluxo completo, configure `allowWrites`, `adminEmail` e
`adminPassword` num arquivo de ambiente **local, fora do Git**, e use esse arquivo
com `-e`. Evite senhas na linha de comando, no histórico do terminal ou nos logs
do CI. Proteja também os relatórios que possam conter dados de teste.

O Newman retorna código diferente de zero quando há falhas. Não use
`--suppress-exit-code` no CI. Os scripts exigem um runtime recente do Postman;
Newman 6.2.1 suporta `pm.execution.skipRequest()`.

## Manutenção

Os JSONs são gerados por [generate-collection.cjs](./generate-collection.cjs).
Depois de alterar o contrato ou os cenários:

```bash
node postman/generate-collection.cjs
node --test postman/collection.test.cjs
```

Os testes locais verificam a geração dos arquivos, a sintaxe dos scripts,
o bloqueio de alterações por padrão, as variáveis e a proteção da eliminação.
Eles não substituem a execução HTTP da coleção contra um backend de testes.
