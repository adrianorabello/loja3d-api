# Plano de Implementação da API REST (loja3d-api) e Integração com Frontend

> **Data:** 18 de Outubro de 2026  
> **Status:** Plano de Execução Passo a Passo e Roteiro de Integração  
> **Aplicação Backend:** `loja3d-api`  
> **Aplicação Frontend:** `loja3d-app`  

---

## 1. Visão Geral e Estrutura de Diretórios Recomendada

Para substituir o script único `main.py` por uma arquitetura modular, escalável e de fácil manutenção, propõe-se a seguinte organização dentro de `loja3d-api/`:

```
loja3d-api/
├── .env.example                     # Modelo de variáveis de ambiente sem segredos
├── requirements.txt                 # Dependências diretas do projeto
├── pytest.ini                       # Configuração de testes unitários e de integração
├── main.py                          # Ponto de entrada FastAPI (lifespan, middlewares, routers)
├── app/
│   ├── __init__.py
│   ├── config.py                    # Pydantic Settings para carregar .env
│   ├── database.py                  # Conexão assíncrona Motor com MongoDB e ciclo de vida
│   ├── core/
│   │   ├── __init__.py
│   │   ├── security.py              # Hash de senhas (bcrypt) e codificação/decodificação JWT
│   │   ├── dependencies.py          # Injeção de dependências (get_current_user, require_role)
│   │   └── bootstrap.py             # Seed idempotente do administrador inicial
│   ├── models/                      # Schemas Pydantic (In, Out, DB)
│   │   ├── __init__.py
│   │   ├── user.py                  # Schemas de Utilizador, Endereço e Auth
│   │   ├── product.py               # Schemas de Produto, Dimensões e Cores
│   │   └── category.py              # Schemas de Categoria
│   ├── routers/                     # Endpoints da API agrupados por domínio
│   │   ├── __init__.py
│   │   ├── health.py                # Health check (API e MongoDB)
│   │   ├── auth.py                  # /api/v1/auth (login, signup, refresh, logout)
│   │   ├── users.py                 # /api/v1/users (perfil /me)
│   │   ├── products.py              # /api/v1/products (público)
│   │   ├── categories.py            # /api/v1/categories (público)
│   │   └── admin_products.py        # /api/v1/admin/products (restrito a ADMIN)
└── tests/
    ├── conftest.py                  # Fixtures de teste (cliente HTTP assíncrono, banco de teste)
    ├── test_health.py
    ├── test_auth.py
    ├── test_users.py
    ├── test_products.py
    └── test_bootstrap.py
```

---

## 2. Dependências Necessárias e Justificativas

As seguintes bibliotecas devem ser adicionadas a `loja3d-api/requirements.txt`:

| Dependência | Versão Recomendada | Finalidade e Justificativa |
|---|---|---|
| `fastapi` | `^0.128.0` (já presente) | Framework web moderno, assíncrono e com geração automática de OpenAPI. |
| `uvicorn[standard]` | `^0.39.0` (já presente) | Servidor ASGI de alta performance para execução do FastAPI. |
| `pydantic` | `^2.13.0` (já presente) | Validação rigorosa de dados e serialização de schemas JSON. |
| `pydantic-settings` | `^2.11.0` (já presente) | Carregamento tipado e seguro de variáveis de ambiente. |
| `motor` | `~=3.6.0` | Driver assíncrono oficial para MongoDB baseado no PyMongo, essencial para operações sem bloqueio no loop de eventos do FastAPI. |
| `passlib[bcrypt]` / `bcrypt` | `~=1.7.4` / `~=4.2.0` | Algoritmo padrão de mercado para hash seguro de senhas com salt automático e proteção contra ataques de força bruta. |
| `pyjwt` | `~=2.10.0` | Criação, assinatura e verificação robusta de tokens JWT (JSON Web Tokens) compatíveis com o frontend. |
| `pytest` | `~=8.3.0` | Framework de testes unitários e de integração. |
| `pytest-asyncio` | `~=0.25.0` | Suporte à execução de testes assíncronos no pytest. |
| `httpx` | `~=0.28.0` (já presente) | Cliente HTTP assíncrono para testes de endpoints com `AsyncClient`. |

---

## 3. Fases de Implementação Ordenadas por Dependência

```
┌────────────────────────────────────────────────────────┐
│ Fase 1: Fundação, Configuração & Conexão MongoDB       │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Fase 2: Autenticação, Perfis & Seed do Administrador   │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Fase 3: Categorias & Catálogo Público de Produtos      │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Fase 4: Administração de Produtos (CRUD Admin)         │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Fase 5: Perfil do Cliente & Gestão de Endereços        │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Fase 6: Padronização OpenAPI & Validação Geral         │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│ Fase 7: Integração Gradual com o Frontend Angular      │
└────────────────────────────────────────────────────────┘
```

---

### Fase 1: Fundação, Configuração e Conexão com MongoDB
**Objetivo:** Estabelecer a infraestrutura básica do backend, carregamento de configurações de ambiente e gestão segura da conexão com o MongoDB.

* **Tarefas Concretas:**
  1. Criar `loja3d-api/requirements.txt` com as dependências essenciais.
  2. Criar `loja3d-api/.env.example` documentando as variáveis (`MONGODB_URL`, `MONGODB_DB_NAME`, `JWT_SECRET_KEY`, `ADMIN_INITIAL_EMAIL`, `ADMIN_INITIAL_PASSWORD`, etc.).
  3. Implementar `app/config.py` utilizando `BaseSettings` do Pydantic.
  4. Implementar `app/database.py` gerenciando a instância do `AsyncIOMotorClient`, garantindo encerramento correto de conexões e criação de índices únicos.
  5. Configurar `main.py` com o contexto assíncrono `lifespan` para inicializar e finalizar o banco de dados.
  6. Implementar `app/routers/health.py` com verificação de conectividade com o MongoDB (`db.command('ping')`).
* **Critérios de Aceite:**
  * O servidor sobe com `uvicorn main:app --reload`.
  * Requisição para `GET /health` retorna `{"status": "ok", "database": "connected"}` quando o MongoDB está ativo.
  * Se o MongoDB estiver inacessível, `GET /health` responde status 503 com `{"status": "degraded", "database": "disconnected"}`.

---

### Fase 2: Autenticação, Perfis de Acesso e Seed do Administrador
**Objetivo:** Garantir a persistência segura de utilizadores, emissão e validação de tokens JWT, controle por perfil (`ADMIN` vs `CUSTOMER`) e provisionamento automático do administrador inicial.

* **Tarefas Concretas:**
  1. Implementar `app/core/security.py` (funções de hash bcrypt, verificação de senha e assinatura de JWT).
  2. Implementar schemas em `app/models/user.py` (`UserBase`, `SignUpRequest`, `SignInRequest`, `UserResponse`, `TokenResponse`).
  3. Implementar `app/core/dependencies.py`:
     * `get_current_user`: extrai e valida o token Bearer via header `Authorization`.
     * `get_current_active_user`: impede utilizadores com `is_active=False`.
     * `require_role(allowed_roles)`: garante autorização baseada em perfil.
  4. Implementar `app/core/bootstrap.py`:
     * Executa no `lifespan` após conexão com o banco.
     * Cria o administrador inicial se não existir nenhum utilizador com o e-mail configurado.
     * Se o utilizador já existir e for `CUSTOMER`, emite alerta crítico e não o promove.
     * Nunca loga a senha ou o hash.
  5. Implementar rotas em `app/routers/auth.py`:
     * `POST /api/v1/auth/sign-up`: cria estritamente `CUSTOMER` e emite token inicial.
     * `POST /api/v1/auth/sign-in`: valida credenciais e emite tokens.
     * `POST /api/v1/auth/refresh`: rotaciona e emite novo token.
     * `POST /api/v1/auth/sign-out`: revoga refresh token.
* **Critérios de Aceite & Testes:**
  * Teste unitário de criação e verificação de senha com bcrypt.
  * Teste do seed: executado 3 vezes consecutivas; apenas 1 registro de administrador existe e a senha original permanece intacta.
  * Cadastro de cliente via `/sign-up`: o usuário recebe perfil `CUSTOMER` mesmo que tente injetar `role: "ADMIN"` no payload.
  * Tentativa de cadastro com e-mail duplicado: retorna código `409 Conflict`.
  * Login com senha incorreta: retorna `401 Unauthorized` sem derrubar a aplicação.
  * Utilizador com `is_active=False`: login recusado com `403 Forbidden`.

---

### Fase 3: Categorias e Catálogo Público de Produtos
**Objetivo:** Servir os dados necessários para a vitrine e catálogo público da loja (`/`, `/products`, `/products/:slug`).

* **Tarefas Concretas:**
  1. Implementar schemas em `app/models/category.py` e `app/models/product.py` garantindo suporte a `LocalizedText` (`{"pt-PT": str, "en": str}`) e dimensões em milímetros.
  2. Implementar `app/routers/categories.py`:
     * `GET /api/v1/categories`: retorna lista de categorias ordenada por nome.
  3. Implementar `app/routers/products.py`:
     * `GET /api/v1/products`: aplica filtros por query string (`q` textual, `category` por id, `sort` por data/preço/nome). Filtra estritamente `active: True`.
     * `GET /api/v1/products/{slug}`: busca produto pelo slug único e ativo. Retorna 404 se não encontrado ou inativo.
  4. Implementar conversão de preço: persistido em cêntimos (`price_cents`) e devolvido no JSON como float em euros (`price: float`).
* **Critérios de Aceite & Testes:**
  * Produtos inativos (`active: False`) **nunca** são retornados em `GET /api/v1/products` ou `GET /api/v1/products/{slug}`.
  * A ordenação por preço ascendente/descendente e por data mais recente funciona com precisão.
  * A busca por texto encontra produtos tanto pelo nome em português quanto em inglês.

---

### Fase 4: Administração de Produtos (CRUD Restrito)
**Objetivo:** Suportar a gestão completa do acervo de produtos através da área administrativa (`/admin/products`, `/admin/products/new`, `/admin/products/:id/edit`).

* **Tarefas Concretas:**
  1. Implementar `app/routers/admin_products.py` protegido pela dependência `require_role(["ADMIN"])`.
  2. Endpoints a implementar:
     * `GET /api/v1/admin/products`: retorna todos os produtos (ativos e inativos) para o `MatTableDataSource` do Angular.
     * `GET /api/v1/admin/products/{id}`: retorna produto por id para edição.
     * `POST /api/v1/admin/products`: cria produto, gerando `id` e `createdAt`. Se o `slug` já existir, retorna `409 Conflict`.
     * `PATCH /api/v1/admin/products/{id}`: atualiza dados parciais ou alterna o status `active`. Valida conflito de slug se alterado (409).
     * `DELETE /api/v1/admin/products/{id}`: remove o produto.
* **Critérios de Aceite & Testes:**
  * Requisição feita com token de cliente `CUSTOMER` para qualquer rota `/api/v1/admin/*` recebe `403 Forbidden`.
  * Criação de produto com slug já existente retorna `409 Conflict` com código legível.
  * Toggle do campo `active` via PATCH atualiza o documento com sucesso.

---

### Fase 5: Perfil do Cliente e Gestão de Endereços
**Objetivo:** Permitir que o cliente autenticado visualize e atualize os seus dados de cadastro e endereços de entrega em `/account/profile`.

* **Tarefas Concretas:**
  1. Implementar `app/routers/users.py`:
     * `GET /api/v1/users/me`: retorna os dados do cliente decodificado do token JWT.
     * `PATCH /api/v1/users/me`: atualiza `name`, `dateOfBirth` e a lista embutida `addresses`.
  2. Implementar validação estrita no payload de atualização:
     * Proibir expressamente qualquer tentativa de alterar `role`, `id`, `is_active` ou `created_at`.
     * Se o e-mail for alterado, verificar unicidade no banco (409 se já utilizado).
* **Critérios de Aceite & Testes:**
  * Cliente atualiza nome e adiciona endereço com sucesso.
  * Tentativa de enviar `role: "ADMIN"` no payload do PATCH é ignorada ou rejeitada, mantendo o perfil intacto como `CUSTOMER`.
  * Um cliente **jamais** consegue consultar ou alterar o perfil de outro cliente (o id é sempre extraído do token, nunca de parâmetros da URL).

---

### Fase 6: Padronização OpenAPI, Swagger UI e Tratamento de Erros
**Objetivo:** Garantir documentação interativa completa e padronização das respostas de erro da API.

* **Tarefas Concretas:**
  1. Configurar metadados do `FastAPI` (título, descrição, versão, tags ordenadas).
  2. Configurar segurança `BearerAuth` no OpenAPI para permitir testes com token diretamente no Swagger UI (`/docs`).
  3. Adicionar middleware ou manipulador global de exceções para garantir que erros 400, 401, 403, 404, 409, 422 e 500 sigam o formato padrão `{ "detail": "...", "code": "..." }`.
  4. Configurar CORS permissivo para origens de desenvolvimento (`http://localhost:4200`, `http://localhost:4201`, `http://localhost:4202`) com suporte a métodos completos e headers de autorização.
* **Critérios de Aceite:**
  * O Swagger UI em `http://localhost:8000/docs` lista todos os endpoints com schemas de entrada/saída documentados.
  * O botão "Authorize" permite colar o token JWT e executar requisições autenticadas diretamente pela interface.

---

### Fase 7: Integração Gradual com o Frontend Angular (`loja3d-app`)
**Objetivo:** Conectar a aplicação Angular à API real do backend sem quebrar componentes ou layouts existentes.

* **Arquivos do Frontend a Modificar:**
  1. `src/environments/environment.ts`:
     * Definir `useMockApi: false`.
     * Ajustar `apiBaseUrl: 'http://localhost:8000/api/v1'` (ou usar proxy do Angular CLI).
  2. `src/app/core/auth/auth.interceptor.ts`:
     * **Ajuste Crítico:** Impedir que o interceptor execute `signOut() + location.reload()` quando o erro 401 for resposta de `/sign-in` ou rotas públicas de autenticação.
  3. `src/app/core/auth/auth.service.ts`:
     * Ajustar as URLs relativas para utilizarem o prefixo correto injetado (`API_BASE_URL` ou `/api/v1/auth/...`).
  4. `src/app/core/user/user.service.ts`:
     * Alterar o endpoint de atualização de `'api/common/user'` para `${this._baseUrl}/users/me` com método `PATCH`.
  5. `src/app/app.resolvers.ts` (`InitialDataResolver`):
     * Adaptar ou simplificar as chamadas de inicialização do painel admin, consumindo o usuário real autenticado.
* **Critérios de Aceite da Integração:**
  * Cadastrar um novo cliente no formulário do Angular: o utilizador é persistido no MongoDB e a sessão é estabelecida.
  * Iniciar sessão como administrador: a navegação redireciona para `/admin/products` e exibe os produtos vindos do banco.
  * Criar um produto no admin: o produto aparece imediatamente no catálogo da vitrine pública.
  * Execução dos testes automatizados do Angular (`npm test`): os testes unitários do frontend continuam passando.

---

## 4. Instruções de Execução Local do Backend

### 4.1 Pré-requisitos
* Python 3.9+ instalado.
* Instância do MongoDB rodando localmente (porta 27017) ou string de conexão do MongoDB Atlas / contêiner Docker.

### 4.2 Configuração do Ambiente
```bash
# 1. Navegar até a pasta do backend
cd loja3d-api

# 2. Ativar o ambiente virtual existente
source .venv/bin/activate

# 3. Instalar as dependências
pip install -r requirements.txt

# 4. Criar o ficheiro .env a partir do modelo
cp .env.example .env
```

Exemplo de conteúdo para o `.env`:
```env
PROJECT_NAME="Clara Rosa Webstore API"
API_V1_STR="/api/v1"
CORS_ORIGINS=["http://localhost:4200","http://localhost:4201","http://localhost:4202"]

MONGODB_URL="mongodb://localhost:27017"
MONGODB_DB_NAME="clara_rosa_store"

JWT_SECRET_KEY="SUA_CHAVE_SECRETA_MUITO_SEGURA_E_ALEATORIA_AQUI"
JWT_ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

BOOTSTRAP_ADMIN_ENABLED=true
ADMIN_INITIAL_EMAIL="admin@clararosa.pt"
ADMIN_INITIAL_PASSWORD="AdminPassword123!"
ADMIN_INITIAL_NAME="Administrador Clara Rosa"
```

### 4.3 Inicialização da Aplicação
```bash
# Iniciar a API com live-reload na porta 8000
uvicorn main:app --reload --port 8000
```
* **Swagger UI:** `http://localhost:8000/docs`
* **Health Check:** `http://localhost:8000/health`

### 4.4 Execução de Testes Automatizados
```bash
pytest -v
```

---

## 5. Riscos e Decisões Pendentes

1. **Serviço de Envio de E-mails (Recuperação de Senha):**
   * *Situação:* Os fluxos de *Forgot Password* e *Reset Password* no frontend estão desenhados apenas como esboço mock.
   * *Decisão Necessária:* Definir o provedor de e-mail transacional (ex: Amazon SES, SendGrid, Resend ou Mailgun) ou adiar a implementação da recuperação de senha para uma fase posterior ao MVP de catálogo e vendas.
2. **Armazenamento de Imagens em Produção:**
   * *Situação:* Para o MVP, o envio de fotos via formulário do admin está baseado em strings base64 no JSON (com limite de 2MB por foto).
   * *Evolução Recomendada:* Para escala comercial, planejar endpoint dedicado de upload multipart (`POST /api/v1/admin/uploads`) persistindo arquivos em storage de objetos (ex: AWS S3, Cloudflare R2 ou MinIO) e guardando apenas URLs públicas no MongoDB.
