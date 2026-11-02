# Clara Rosa Webstore API

API REST assíncrona desenvolvida com Python, FastAPI e MongoDB.

## Support chat (opt-in)

Persistent customer/admin support, REST + WebSocket, transactional MongoDB
history/outbox and private scanned GridFS attachments are available behind
`CHAT_ENABLED`. See [chat setup and contracts](docs/chat.md). The separate
`docker-compose.chat.yml` keeps the existing store database untouched.

## Personal profile and avatar

`GET/PATCH /api/v1/users/me` reads/updates only the authenticated user's profile.
The legacy `/api/common/user` and `{user: ...}` shape remain supported.
Editable fields are name (2-100 after trimming), phone/phoneCountry, dateOfBirth
and addresses. A changed email is rejected: use the existing email-change
confirmation endpoints. Roles, IDs, status and arbitrary avatar fields cannot
be changed through profile PATCH.

- `POST /api/v1/users/me/avatar`: Bearer-authenticated multipart, field `file`;
  JPEG/PNG, 1 byte to 10 MiB, at most 16 million pixels, no animation. Uses Pillow
  to decode and normalize to JPEG up to 512 x 512 and 512 KiB, with EXIF orientation
  applied and metadata removed. Returns `UserResponse` including `avatarVersion`.
- `GET /api/v1/users/me/avatar?v=<version>`: returns only the caller's stored JPEG,
  `Cache-Control: private, no-store`, and `X-Content-Type-Options: nosniff`.
  Version is a client cache key, not authorization. Without a photo returns 404.
- `DELETE /api/v1/users/me/avatar`: clears bytes/version, returns `avatar: null`.

Bytes are stored as BSON binary in the user's MongoDB document and excluded from
ordinary profile/login/refresh responses and authentication reads. Replacement is
atomic; invalid input or storage failure leaves the previous photo unchanged.
No local filesystem volume or public image URL is required. Upload errors use
413 (size), 415 (type), 422 (invalid image), 429 (rate limit), 503 (write failure).
Configure the deployment's request-body limit to allow this bounded multipart
upload; the application reads at most 10 MiB + 1 byte from the uploaded file.
There is no endpoint accepting an arbitrary user ID for these operations.

## Product image persistence

Product create/update accepts the existing `images` array. New JPEG/PNG data URLs
are decoded, validated and stored as BSON binary in `products.image_data`, with
`id`, `content_type` and `data` per image. The `images` array stores only endpoint
references for these uploads. Data URLs are transport/preview only, not the
persisted format for new uploads. The original validated image bytes/resolution
are preserved, including PNG transparency.

The per-file limit remains 2 MiB (not the profile's 10 MiB), with at most
16 million pixels and no animation. The full product document must fit MongoDB's
16 MiB limit; exceeding it returns 413 before writing. Invalid content returns
415/422, and database write failures return 503 without claiming success.
Product fields and image bytes are saved atomically in one document. Replacing,
removing or deleting the product removes the corresponding stored bytes.

`GET /api/v1/products/{productId}/images/{imageId}` serves the stored bytes with the
validated MIME type, `nosniff` and a one-hour public cache. Product photos are
public media, including photos referenced by inactive products; inactive products
remain excluded from the public catalogue. Photo IDs are random and replaced for
new uploads. Removed URLs return 404 from the API, but already cached copies may
remain until their cache expires. Admin writes still require the ADMIN role.

Catalogue and admin JSON responses exclude the binary fields. Existing static
asset paths and external HTTP(S) URLs remain references; they are not downloaded.
Existing inline Base64 images convert on the next product save (including edits
without changing `images`). There is no automatic bulk rewrite of existing data.
Configure deployment request-body limits for Base64 transport overhead (~33%) and
multiple images; the old JSON create/edit contracts remain compatible.

## Requisitos

- Python 3.9 ou superior
- MongoDB 7 (local ou serviço gerido, como MongoDB Atlas)
- Docker Compose, opcional, para executar o MongoDB localmente

## Configuração das variáveis de ambiente

As configurações são lidas de variáveis do sistema ou de um arquivo `.env` na pasta da API. Comece pelo exemplo:

```bash
cp .env.example .env
```

Edite o `.env` para seu ambiente. Não versione esse arquivo nem compartilhe seus segredos. O `.gitignore` ignora arquivos `.env`, exceto `.env.example`.

| Variável | Padrão de desenvolvimento | Descrição |
|---|---|---|
| `ENVIRONMENT` | `development` | Ambiente da aplicação. Use `production` em produção; o envio de e-mail pelo backend `console` não é permitido nesse ambiente. |
| `FRONTEND_URL` | `http://localhost:4201` | URL pública do frontend, usada nos links de confirmação de e-mail e recuperação de senha. |
| `CORS_ORIGINS` | Origens localhost definidas em `app/config.py` | Origens autorizadas pelo CORS, separadas por vírgula e sem barra final. Exemplo: `https://loja.example.com,https://admin.example.com`. |
| `MONGODB_URL` | `mongodb://127.0.0.1:27017` | URI de conexão do MongoDB. Em produção, use a URI do cluster e guarde credenciais apenas nas variáveis de ambiente da plataforma. |
| `MONGODB_DB_NAME` | `clara_rosa_store` | Nome da base de dados MongoDB utilizada pela API. |
| `JWT_SECRET_KEY` | Segredo de desenvolvimento definido em `app/config.py` | Segredo de assinatura dos tokens JWT. Defina um valor aleatório, forte e exclusivo em produção; nunca use o valor padrão. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Validade do token de acesso, em minutos. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Validade do refresh token, em dias. |
| `RATE_LIMIT_ENABLED` | `true` | Ativa o limitador de requisições em memória. Em múltiplas instâncias, use um mecanismo compartilhado para manter limites consistentes. |
| `EMAIL_BACKEND` | `console` | Backend de e-mail: `console` para desenvolvimento ou `smtp` para envio real. `console` não pode ser usado com `ENVIRONMENT=production`. |
| `EMAIL_FROM` | `Printoy 3D <no-reply@printoy.pt>` | Nome e endereço remetente dos e-mails. |
| `SMTP_HOST` | Vazio | Servidor SMTP. Obrigatório para envio por SMTP. |
| `SMTP_PORT` | `587` | Porta do servidor SMTP. |
| `SMTP_USER` | Vazio | Utilizador SMTP, quando exigido pelo provedor. |
| `SMTP_PASSWORD` | Vazio | Palavra-passe SMTP. Mantenha-a como segredo. |
| `SMTP_STARTTLS` | `true` | Ativa STARTTLS na conexão SMTP. |
| `EMAIL_VERIFICATION_EXPIRE_HOURS` | `24` | Validade dos links de verificação de e-mail, em horas. |
| `PASSWORD_RESET_EXPIRE_MINUTES` | `60` | Validade dos links de recuperação de senha, em minutos. |
| `BOOTSTRAP_ADMIN_ENABLED` | `true` | Cria o administrador inicial se ainda não existir. |
| `ADMIN_INITIAL_EMAIL` | `admin@clararosa.pt` | E-mail do administrador inicial. |
| `ADMIN_INITIAL_PASSWORD` | `admin` | Senha do administrador inicial. Defina uma senha forte antes de iniciar em produção. |
| `ADMIN_INITIAL_NAME` | `Clara Rosa Admin` | Nome do administrador inicial. |

Além das configurações acima, `PROJECT_NAME`, `VERSION`, `API_V1_STR` e `JWT_ALGORITHM` têm valores padrão no código e podem ser substituídas por variáveis de ambiente.

### Variáveis na Vercel

Cadastre as configurações na página **Project → Settings → Environment Variables** e selecione os ambientes em que cada uma deve estar disponível. Para que a API inicie e possa servir inclusive a documentação Swagger, configure pelo menos:

```text
ENVIRONMENT=production
FRONTEND_URL=https://<dominio-do-frontend>
CORS_ORIGINS=https://<dominio-do-frontend>
MONGODB_URL=<uri-de-conexao-do-mongodb>
MONGODB_DB_NAME=clara_rosa_store
JWT_SECRET_KEY=<segredo-aleatorio-forte>
BOOTSTRAP_ADMIN_ENABLED=true
ADMIN_INITIAL_EMAIL=<email-do-administrador>
ADMIN_INITIAL_PASSWORD=<senha-forte-do-administrador>
EMAIL_BACKEND=smtp
SMTP_HOST=<servidor-smtp>
SMTP_PORT=587
SMTP_USER=<utilizador-smtp>
SMTP_PASSWORD=<senha-smtp>
SMTP_STARTTLS=true
```

Substitua os valores entre `<...>` pelos dados reais. Não use uma URI local como `mongodb://127.0.0.1:27017` na Vercel: esse endereço aponta para o próprio ambiente da função, não para seu computador nem para um cluster acessível. A aplicação conecta ao MongoDB durante o arranque; uma URI ausente, inválida ou inacessível faz o arranque falhar.

Para a loja Printoy publicada, configure no projeto **da API** na Vercel, no
ambiente **Production**, e faça um novo deploy do backend:

```text
FRONTEND_URL=https://www.printoy3d.com
CORS_ORIGINS=https://www.printoy3d.com,https://printoy3d.com
```

`www.printoy3d.com` e `printoy3d.com` são origens diferentes. Alterar o `.env`
local ou publicar apenas o frontend não modifica a configuração da API remota.
Não use `*` como atalho: autorize explicitamente os domínios da loja.
Para verificar sem criar uma conta:

```bash
curl -i -X OPTIONS https://api.printoy3d.com/api/auth/sign-up \
  -H 'Origin: https://www.printoy3d.com' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
```

O resultado esperado é HTTP 200 e
`access-control-allow-origin: https://www.printoy3d.com`. HTTP 400 com
`Disallowed CORS origin` impede o cadastro pelo navegador, mesmo que o Postman
consiga chamar a API; Postman e curl não aplicam a política CORS do navegador.

O ponto de entrada ASGI da aplicação é `main.py`, com o objeto `app`. Configure o diretório raiz do projeto Vercel como `loja3d-api` se este estiver dentro de um monorepo. Este projeto não inclui atualmente um arquivo `vercel.json`; confirme nos logs da implantação se a Vercel detectou e construiu a função Python corretamente.

## MongoDB local com Docker Compose

O Compose inicia o MongoDB com persistência em volume e o Mongo Express para inspeção local:

```bash
docker compose up -d
```

- MongoDB: `mongodb://127.0.0.1:27017`
- Mongo Express: <http://localhost:8081>
- Volume persistente: `clara_rosa_mongodb_data`

Para iniciar apenas o MongoDB, use `docker compose up -d mongodb`. Para verificar os serviços, `docker compose ps`; para pará-los, `docker compose down`. O Compose não apaga o volume de dados ao parar os serviços.

## Instalar e executar a API

Na pasta `loja3d-api`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8000
```

No Windows, ative o ambiente virtual com `.venv\Scripts\activate`. A API precisa de um MongoDB acessível antes de atender requisições.

### Endpoints úteis

- API: <http://localhost:8000>
- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- OpenAPI JSON: <http://localhost:8000/openapi.json>
- Health check: <http://localhost:8000/health>
- Rotas versionadas: prefixo `/api/v1`

## Pedidos de impressão personalizada

O backend persiste pedidos, revisões de orçamento e histórico visível ao cliente
em MongoDB. O contrato completo e a matriz de transições por ator estão em
[docs/print-requests.md](docs/print-requests.md).

- Cliente: `POST /api/v1/print-requests`, `GET /api/v1/print-requests`,
  `GET /api/v1/print-requests/{id}`, `POST .../{id}/messages` e
  `POST .../{id}/actions`.
- Administrador: `GET /api/v1/admin/print-requests`, `GET .../{id}`,
  `POST .../{id}/messages`, `POST .../{id}/quote` e `POST .../{id}/transition`.
- Criar e executar mutações pelas rotas do cliente exige papel `CUSTOMER`.
  As leituras pessoais também aceitam `ADMIN`, mas continuam limitadas ao
  proprietário; gerir pedidos de terceiros exige as rotas administrativas.
- Listagens usam `{items,total,page,pageSize}`, com paginação, pesquisa, filtro
  de estado e ordenação no servidor. Todas as mutações exigem `version`; uma
  versão obsoleta ou transição inválida devolve `409`. Outro proprietário recebe
  `404`, sem revelar a existência do pedido.
- `allowedActions` e `allowedTransitions` são calculados pelo servidor.
  Datas/histórico/orçamentos usam UTC; campos opcionais não definidos são
  omitidos, não enviados como `null`.
- O pagamento é confirmado **manualmente por um administrador**, com motivo no
  histórico. Não há gateway, comprovativo, cobrança, notificação de pedidos ou
  reembolso automático. O cancelamento administrativo após pagamento não
  representa reembolso.
- São aceites apenas `referenceLinks` HTTP(S), sem credenciais: até cinco URLs.
  São referências externas, sem download/fetch pelo servidor e sem uploads
  binários. O envio do pedido não cobra o cliente.

## Inicialização e dados de demonstração

No arranque, a API conecta-se ao MongoDB, inicializa índices e executa o bootstrap configurado. Com as opções padrão, uma base vazia recebe um administrador inicial e dados de catálogo de demonstração.

As credenciais de exemplo (`admin@clararosa.pt` / `admin` e `cliente@clararosa.pt` / `cliente`) são apenas para desenvolvimento. Não as utilize em produção. Configure uma senha forte para o administrador inicial. Depois da criação inicial da conta, pode desativar `BOOTSTRAP_ADMIN_ENABLED` se não precisar que o bootstrap volte a ser executado.

## Testes

```bash
source .venv/bin/activate
pytest -v
```

Os testes Python usam exclusivamente o MongoDB local
`mongodb://127.0.0.1:27017` e a base `clara_rosa_test_store`, que é eliminada no
fim da sessão. O `conftest.py` substitui a URI, a base e o backend de e-mail
(`console`) antes de carregar a configuração; não utiliza o MongoDB nem o SMTP
de produção do `.env`. Os testes do fluxo personalizado estão em
`tests/test_print_requests.py`.

### Testes automatizados no Postman

Importe a [coleção de testes](postman/Printoy3D.postman_collection.json) e o
[ambiente remoto](postman/Printoy3D.production.postman_environment.json).
A variável `baseUrl` já aponta para `https://api.printoy3d.com`; também há um
[ambiente local](postman/Printoy3D.local.postman_environment.json).

Por segurança, `allowWrites=false` executa apenas as leituras públicas e os
testes de acesso negado. O fluxo completo requer `allowWrites=true` e
credenciais administrativas; cria contas, envia e-mails e testa o CRUD de
produtos. Consulte as [instruções de execução e automatização](postman/README.md)
antes de habilitá-lo, especialmente no ambiente de produção.

## Funcionalidades de conta e autenticação

- Cadastro, login, consulta da sessão e logout com revogação de refresh token.
- Verificação de e-mail e recuperação de senha.
- Atualização de perfil e alteração de e-mail com confirmação.
- Hash de senhas com Argon2id; hashes bcrypt antigos são migrados durante o login.
- Tokens de confirmação são de uso único e guardados como hash.
- Validação de telefone com `phonenumbers`, armazenado em formato E.164 e com país ISO.
- Limitação de requisições por IP em memória.
- Em desenvolvimento, `EMAIL_BACKEND=console` escreve os e-mails nos logs. Para envio real, configure SMTP.
