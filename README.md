# Clara Rosa Webstore API

API REST assíncrona desenvolvida com Python, FastAPI e MongoDB.

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

## Inicialização e dados de demonstração

No arranque, a API conecta-se ao MongoDB, inicializa índices e executa o bootstrap configurado. Com as opções padrão, uma base vazia recebe um administrador inicial e dados de catálogo de demonstração.

As credenciais de exemplo (`admin@clararosa.pt` / `admin` e `cliente@clararosa.pt` / `cliente`) são apenas para desenvolvimento. Não as utilize em produção. Configure uma senha forte para o administrador inicial. Depois da criação inicial da conta, pode desativar `BOOTSTRAP_ADMIN_ENABLED` se não precisar que o bootstrap volte a ser executado.

## Testes

```bash
source .venv/bin/activate
pytest -v
```

## Funcionalidades de conta e autenticação

- Cadastro, login, consulta da sessão e logout com revogação de refresh token.
- Verificação de e-mail e recuperação de senha.
- Atualização de perfil e alteração de e-mail com confirmação.
- Hash de senhas com Argon2id; hashes bcrypt antigos são migrados durante o login.
- Tokens de confirmação são de uso único e guardados como hash.
- Validação de telefone com `phonenumbers`, armazenado em formato E.164 e com país ISO.
- Limitação de requisições por IP em memória.
- Em desenvolvimento, `EMAIL_BACKEND=console` escreve os e-mails nos logs. Para envio real, configure SMTP.
