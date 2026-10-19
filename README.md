# Clara Rosa Webstore — API Backend (`loja3d-api`)

API REST assíncrona desenvolvida com Python 3.9+, FastAPI e MongoDB para a loja online Clara Rosa.

---

## 1. Infraestrutura com Docker Compose

Para subir o MongoDB com persistência em volume e a interface visual de gestão (Mongo Express), utilize o Docker Compose:

```bash
cd loja3d-api

# Iniciar o MongoDB e Mongo Express em segundo plano
docker compose up -d

# Para subir apenas o MongoDB:
docker compose up -d mongodb

# Para verificar o status dos contêineres:
docker compose ps

# Para parar os serviços:
docker compose down
```

### Serviços Disponibilizados:
* **MongoDB:** `localhost:27017`
  * Banco padrão configurado: `clara_rosa_store`
  * Volume com persistência: `clara_rosa_mongodb_data`
* **Mongo Express (UI Web):** `http://localhost:8081`
  * Permite inspecionar coleções e documentos diretamente pelo navegador.

---

## 2. Configuração e Execução da API

### Pré-requisitos
* Python 3.9+
* Ambiente virtual ativo

```bash
cd loja3d-api

# 1. Ativar o ambiente virtual
source .venv/bin/activate

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Criar/verificar o arquivo .env
cp -n .env.example .env

# 4. Iniciar o servidor de desenvolvimento
uvicorn main:app --reload --port 8000
```

### URLs da Aplicação:
* **API Base:** `http://localhost:8000`
* **Swagger UI (Documentação OpenAPI):** `http://localhost:8000/docs`
* **ReDoc:** `http://localhost:8000/redoc`
* **Health Check:** `http://localhost:8000/health`

---

## 3. Testes Automatizados

```bash
cd loja3d-api
source .venv/bin/activate
pytest -v
```

---

## 4. Credenciais Pré-configuradas (Bootstrap)

Na primeira inicialização com o MongoDB vazio, a API provisiona automaticamente:
* **Administrador:**
  * E-mail: `admin@clararosa.pt`
  * Senha: `admin`
* **Cliente de Testes:**
  * E-mail: `cliente@clararosa.pt`
  * Senha: `cliente`
* **Catálogo Inicial:**
  * 4 categorias e 7 produtos demonstrativos (incluindo o item de teste inativo).

## Contas e autenticação (fase 1)

- Cadastro (`POST /auth/sign-up` ou `/auth/register`), login, `GET /auth/me`, `POST /auth/logout` (revoga o refresh token).
- Verificação de e-mail: `POST /auth/verify-email`, `POST /auth/resend-verification`.
- Recuperação: `POST /auth/forgot-password` (resposta sempre igual) e `POST /auth/reset-password` (revoga todas as sessões).
- Perfil: `PATCH /users/me` (apenas nome, data de nascimento, telefone, moradas). Troca de e-mail via
  `POST /users/me/email-change` + `/users/me/email-change/confirm`.
- Senhas em Argon2id (hashes bcrypt antigos são migrados no login). Tokens de e-mail são de uso único e guardados como hash.
- Telefone validado com `phonenumbers` e guardado em E.164 + país ISO.
- Rate limit em memória por IP (use um store partilhado com vários workers).
- Em desenvolvimento (`EMAIL_BACKEND=console`) os e-mails aparecem no log do servidor; em produção é obrigatório `smtp`.
- Fora desta fase: Google/Apple OAuth e Instagram (ver `.env.example` para configuração atual).
