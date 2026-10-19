# Especificação de Contratos da API e Modelo de Dados (MongoDB)

> **Data:** 18 de Outubro de 2026  
> **Status:** Especificação Técnica de Contratos, Segurança e Banco de Dados  
> **Aplicação Frontend:** `loja3d-app`  
> **Aplicação Backend:** `loja3d-api`  

---

## 1. Mapeamento Frontend → API

A tabela abaixo conecta diretamente cada tela, componente e serviço da aplicação Angular aos endpoints da API REST, métodos HTTP, perfis autorizados e coleções do MongoDB.

### Convenções de Status
* **[Confirmado]**: Requisito explicitamente implementado e verificado no código do Angular.
* **[Proposta Técnica]**: Decisão arquitetural desenhada para garantir compatibilidade REST, robustez e segurança.
* **[Pendente de Decisão]**: Ponto que depende de alinhamento com a liderança de produto / cliente.

| Tela / Componente Angular | Caminho do Ficheiro | Operação | Campos & Validações | Endpoint Proposto | Método | Perfil Autorizado | Coleção MongoDB | Situação Atual & Trabalho Necessário |
|---|---|---|---|---|---|---|---|---|
| **Sign Up** (`AuthSignUpComponent`) | `src/app/modules/auth/sign-up/` | Criar nova conta de cliente | `name` (req), `email` (req, email), `password` (req, min 4), `agreements` (reqTrue) | `/api/v1/auth/sign-up` | `POST` | Público (Guest) | `users` | **[Confirmado]** Frontend pronto. Backend precisa implementar criação exclusiva com `role: CUSTOMER`, hash de senha e retorno de JWT. |
| **Sign In** (`AuthSignInComponent`) | `src/app/modules/auth/sign-in/` | Autenticar utilizador e obter token | `email` (req, email), `password` (req) | `/api/v1/auth/sign-in` | `POST` | Público (Guest) | `users`, `refresh_tokens` | **[Confirmado]** Frontend pronto. Backend precisa validar credenciais, emitir token JWT e atualizar último login. Corrigir `AuthInterceptor` para não recarregar a tela em 401 de login. |
| **Renovar Sessão** (`AuthService.signInUsingToken`) | `src/app/core/auth/auth.service.ts` | Renovar token ao abrir a app (`check()`) | `access_token` (ou refresh token) | `/api/v1/auth/refresh` | `POST` | Autenticado | `users`, `refresh_tokens` | **[Confirmado]** Frontend chama endpoint relativo. Backend deve validar token/sessão e devolver novo par de tokens e dados do utilizador. |
| **Sign Out** (`AuthSignOutComponent`) | `src/app/modules/auth/sign-out/` | Encerrar sessão | N/A | `/api/v1/auth/sign-out` | `POST` | Autenticado | `refresh_tokens` | **[Proposta Técnica]** Frontend só limpa localStorage hoje. Backend deve invalidar a sessão/refresh token no banco. |
| **Perfil & Endereços** (`CustomerProfileComponent`) | `src/app/domains/customer/profile/` | Obter perfil do utilizador autenticado | Token de autorização Bearer | `/api/v1/users/me` | `GET` | Autenticado (`CUSTOMER`, `ADMIN`) | `users` | **[Confirmado]** No mock usa `GET api/common/user`. Backend deve retornar os dados do utilizador logado decodificado do token. |
| **Perfil & Endereços** (`CustomerProfileComponent`) | `src/app/domains/customer/profile/` | Atualizar dados pessoais e endereços | `name` (req), `email` (req, email), `dateOfBirth` (opc), `addresses` (array de UserAddress) | `/api/v1/users/me` | `PATCH` | Autenticado (`CUSTOMER`, `ADMIN`) | `users` | **[Confirmado]** Frontend envia payload via `UserService.update()`. Backend deve restringir alteração a apenas dados próprios e proibir alteração de `role`. |
| **Catálogo Público** (`KidsStoreComponent`, `HomePageComponent`) | `src/app/domains/storefront/` | Listar produtos ativos para a vitrine | Query params: `q` (busca textual), `category` (id), `sort` (`newest`, `price-asc`, `price-desc`, `name-asc`, `name-desc`) | `/api/v1/products` | `GET` | Público | `products` | **[Confirmado]** Backend deve filtrar estritamente `active: true`, aplicar busca e ordenação no MongoDB. |
| **Detalhe de Produto** (`ProductDetailsComponent`) | `src/app/domains/storefront/product-details/` | Obter produto por slug | `slug` (string na URL) | `/api/v1/products/{slug}` | `GET` | Público | `products` | **[Confirmado]** Backend deve buscar produto com `slug` correspondente e `active: true`. Retornar 404 se inativo ou inexistente. |
| **Categorias** (`CategoryService`) | `src/app/core/category/category.service.ts` | Listar categorias ativas | N/A | `/api/v1/categories` | `GET` | Público | `categories` | **[Confirmado]** Backend deve servir a lista de categorias com traduções `pt-PT` e `en`. |
| **Admin: Lista de Produtos** (`ProductListComponent`) | `src/app/domains/admin/products/list/` | Listar todos os produtos (ativos e inativos) | N/A (filtro e paginação feitos no Angular) | `/api/v1/admin/products` | `GET` | `ADMIN` | `products` | **[Confirmado]** Rota protegida por perfil. Retorna todo o acervo para o `MatTableDataSource`. |
| **Admin: Obter Produto** (`ProductResolver`) | `src/app/domains/admin/products/products.resolvers.ts` | Obter produto por id para edição | `id` (string na URL) | `/api/v1/admin/products/{id}` | `GET` | `ADMIN` | `products` | **[Confirmado]** Retorna produto pelo identificador único independentemente do status ativo. |
| **Admin: Criar Produto** (`ProductFormComponent`) | `src/app/domains/admin/products/form/` | Criar novo produto | `namePt` (req), `nameEn`, `descriptionPt`, `descriptionEn`, `slug` (req, regex), `categoryId` (req), `price` (req, >0), `dimensions`, `stock` (req, >=0), `colors`, `madeToOrder`, `active`, `featured`, `images` (min 1) | `/api/v1/admin/products` | `POST` | `ADMIN` | `products` | **[Confirmado]** Backend valida unicidade do `slug` (devolve 409 se duplicado). Gera `id` e `createdAt`. |
| **Admin: Atualizar Produto** (`ProductFormComponent`, `ProductListComponent`) | `src/app/domains/admin/products/form/` | Atualizar dados ou status do produto | `id`, dados parciais do produto | `/api/v1/admin/products/{id}` | `PATCH` | `ADMIN` | `products` | **[Confirmado]** Utilizado tanto para salvar edições completas quanto para o toggle rápido de `active`. Valida conflito de slug (409). |
| **Admin: Remover Produto** (`ProductListComponent`) | `src/app/domains/admin/products/list/` | Remover produto do catálogo | `id` | `/api/v1/admin/products/{id}` | `DELETE` | `ADMIN` | `products` | **[Confirmado]** Remove o documento ou aplica soft-delete. Retorna 204 No Content ou 200. |
| **Forgot Password** (`AuthForgotPasswordComponent`) | `src/app/modules/auth/forgot-password/` | Solicitar recuperação de senha | `email` (req, email) | `/api/v1/auth/forgot-password` | `POST` | Público | `users`, `password_resets` | **[Pendente de Decisão]** Sem serviço de e-mail contratado (SendGrid, Mailgun, AWS SES). Deve retornar 200 neutro para evitar enumeração de usuários. |
| **Reset Password** (`AuthResetPasswordComponent`) | `src/app/modules/auth/reset-password/` | Redefinir senha com token | `token` (URL), `password` (req), `passwordConfirm` (req) | `/api/v1/auth/reset-password` | `POST` | Público | `users`, `password_resets` | **[Pendente de Decisão]** Componente do Fuse não possui leitura de token na rota. Requer ajuste no frontend e tabela de tokens temporários. |

---

## 2. Autenticação e Autorização

### 2.1 Perfis de Acesso (`Role`)
O sistema adota estritamente dois perfis:
1. `CUSTOMER`: Utilizador padrão do ecommerce. Pode gerir o seu perfil, consultar a vitrine e gerir endereços. Não tem permissão para aceder a rotas de administração ou consultar dados de outros clientes.
2. `ADMIN`: Administrador da plataforma. Possui acesso total ao CRUD de produtos e categorias, bem como visualização gerencial.

### 2.2 Estratégia de Sessão e Tokens
* **Estratégia Recomendada para a Fase Atual:**
  * **Access Token:** JWT (JSON Web Token), assinado com algoritmo HMAC-SHA256 (`HS256`) através de uma chave secreta robusta (`JWT_SECRET_KEY`).
    * **Tempo de Expiração:** 15 a 30 minutos (`ACCESS_TOKEN_EXPIRE_MINUTES = 30`).
    * **Claims do Payload:**
      * `sub`: ID do utilizador (string).
      * `email`: E-mail normalizado.
      * `role`: `"ADMIN"` ou `"CUSTOMER"`.
      * `iat`: Timestamp de emissão.
      * `exp`: Timestamp de expiração.
      * `iss`: `"loja3d-api"`.
  * **Refresh Token:** String opaca de alta entropia (32 bytes aleatórios codificados em base64 URL-safe), com hash SHA-256 persistido no MongoDB na coleção `refresh_tokens`.
    * **Tempo de Expiração:** 7 a 30 dias (`REFRESH_TOKEN_EXPIRE_DAYS = 7`).
    * **Rotação e Revogação:** A cada uso em `/api/v1/auth/refresh`, o refresh token anterior é revogado e um novo par de tokens é emitido. No logout (`/api/v1/auth/sign-out`), o token é marcado como revogado.
  * **Compatibilidade com o Fuse Starter:**
    * O frontend atual armazena o token em `localStorage` e o injeta via `Authorization: Bearer <token>` no `AuthInterceptor`.
    * *Nota de Segurança:* Para mitigar riscos de XSS em longo prazo, planeia-se a transição futura do Refresh Token para cookie `HttpOnly`, `SameSite=Strict` e `Secure`. No entanto, nesta fase de integração, para compatibilidade imediata com a arquitetura existente do Fuse, a API aceitará tanto o envio via body/header quanto preparará os headers para cookies.

### 2.3 Regras de Segurança no Backend
1. **Hash de Senha:** Utilização de `passlib[bcrypt]` com fator de custo 12 (`bcrypt`). As senhas nunca são salvas ou registradas em texto puro.
2. **Normalização de E-mail:** Todos os e-mails recebidos para cadastro ou login passam por `.strip().lower()`.
3. **Prevenção contra Elevação de Privilégios (Mass Assignment):**
   * O schema Pydantic `SignUpRequest` **não possui** o campo `role`. O endpoint de cadastro atribui forçadamente `role = UserRole.CUSTOMER`.
   * O schema `UserProfileUpdateRequest` para `/api/v1/users/me` aceita apenas `name`, `dateOfBirth` e `addresses`. Campos como `role`, `is_active` e `id` são excluídos do schema de entrada.
4. **Proteção contra Usuários Desativados:**
   * A dependência FastAPI `get_current_active_user` verifica se `user.is_active is True`. Se o utilizador foi desativado por um administrador, todas as requisições autenticadas são rejeitadas com `403 Forbidden`.
5. **Proteção contra Tentativas Excessivas (Rate Limiting):**
   * Aplicar rate limit em `/api/v1/auth/sign-in` (ex: máximo 5 tentativas por minuto por IP) utilizando middleware simples ou biblioteca compatível (`slowapi`).

---

## 3. Modelo de Dados no MongoDB

A base de dados adotada é o MongoDB, utilizando o driver assíncrono oficial **Motor** (`AsyncIOMotorClient`).

### 3.1 Coleção: `users`
Armazena clientes e administradores.

#### Estrutura do Documento (BSON):
```json
{
  "_id": ObjectId("67123456789abcdef0123456"),
  "email": "cliente@clararosa.pt",
  "password_hash": "$2b$12$K8...",
  "name": "Cliente Demo",
  "role": "CUSTOMER",
  "is_active": true,
  "date_of_birth": "1990-05-15",
  "avatar": "assets/images/avatars/female-01.jpg",
  "addresses": [
    {
      "id": "address-1729245000000-0",
      "label": "Casa",
      "street": "Rua das Flores, 123",
      "unit": "2º Dto",
      "postal_code": "4000-123",
      "city": "Porto",
      "country": "Portugal"
    }
  ],
  "created_at": ISODate("2026-10-18T10:00:00.000Z"),
  "updated_at": ISODate("2026-10-18T10:00:00.000Z")
}
```

#### Índices Obrigatórios:
```python
# 1. Unicidade de e-mail (case-insensitive via collation ou normalização lower-case)
db.users.create_index([("email", 1)], unique=True, name="idx_users_email_unique")

# 2. Busca por perfil e status
db.users.create_index([("role", 1), ("is_active", 1)], name="idx_users_role_status")
```

---

### 3.2 Coleção: `products`
Armazena o catálogo completo da loja.

#### Estrutura do Documento (BSON):
```json
{
  "_id": ObjectId("67123456789abcdef0123457"),
  "slug": "dragao-articulado",
  "name": {
    "pt-PT": "Dragão Articulado",
    "en": "Articulated Dragon"
  },
  "description": {
    "pt-PT": "Dragão articulado impresso em 3D, flexível e divertido.",
    "en": "3D printed articulated dragon, flexible and fun."
  },
  "category_id": "cat-figuras",
  "price_cents": 1500,
  "currency": "EUR",
  "dimensions": {
    "width": 120.0,
    "height": 45.0,
    "depth": 180.0,
    "unit": "mm"
  },
  "colors": [
    {
      "id": "verde-esmeralda",
      "name": {
        "pt-PT": "Verde Esmeralda",
        "en": "Emerald Green"
      },
      "hex": "#009966"
    }
  ],
  "images": [
    "assets/images/clara-rosa/dragon-01.jpg"
  ],
  "stock": 10,
  "active": true,
  "made_to_order": false,
  "featured": true,
  "created_at": ISODate("2026-10-18T10:00:00.000Z"),
  "updated_at": ISODate("2026-10-18T10:00:00.000Z")
}
```

#### Representação Monetária:
* **No Banco:** Inteiro `price_cents: 1500` (evita qualquer imprecisão de ponto flutuante IEEE-754).
* **Na API / Frontend:** Serializado no schema Pydantic como `price: 15.00` (float ou string formatada) e convertido de volta para cêntimos (`round(price * 100)`) na persistência.

#### Índices Obrigatórios:
```python
# 1. Unicidade de slug
db.products.create_index([("slug", 1)], unique=True, name="idx_products_slug_unique")

# 2. Vitrine pública: produtos ativos ordenados por data ou destaque
db.products.create_index([("active", 1), ("featured", -1), ("created_at", -1)], name="idx_products_storefront")

# 3. Filtro por categoria em produtos ativos
db.products.create_index([("active", 1), ("category_id", 1)], name="idx_products_category")

# 4. Índice de texto para busca multilíngue em nome e descrição
db.products.create_index(
    [
        ("name.pt-PT", "text"),
        ("name.en", "text"),
        ("description.pt-PT", "text"),
        ("description.en", "text")
    ],
    name="idx_products_text_search"
)
```

---

### 3.3 Coleção: `categories`
Categorias de produtos.

#### Estrutura do Documento (BSON):
```json
{
  "_id": ObjectId("67123456789abcdef0123458"),
  "code": "cat-figuras",
  "slug": "figuras",
  "name": {
    "pt-PT": "Figuras e Colecionáveis",
    "en": "Figures & Collectibles"
  },
  "created_at": ISODate("2026-10-18T10:00:00.000Z")
}
```

#### Índices Obrigatórios:
```python
db.categories.create_index([("code", 1)], unique=True, name="idx_categories_code_unique")
db.categories.create_index([("slug", 1)], unique=True, name="idx_categories_slug_unique")
```

---

### 3.4 Coleção: `refresh_tokens`
Gestão de sessões ativas e rotação de credenciais.

#### Estrutura do Documento (BSON):
```json
{
  "_id": ObjectId("67123456789abcdef0123459"),
  "token_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "user_id": ObjectId("67123456789abcdef0123456"),
  "expires_at": ISODate("2026-10-25T10:00:00.000Z"),
  "revoked": false,
  "created_at": ISODate("2026-10-18T10:00:00.000Z")
}
```

#### Índices Obrigatórios:
```python
db.refresh_tokens.create_index([("token_hash", 1)], unique=True, name="idx_refresh_tokens_hash")
db.refresh_tokens.create_index([("user_id", 1)], name="idx_refresh_tokens_user")
# TTL Index para expiração automática no MongoDB
db.refresh_tokens.create_index([("expires_at", 1)], expireAfterSeconds=0, name="idx_refresh_tokens_ttl")
```

---

## 4. Gestão de IDs e Serialização Pydantic

O MongoDB gera internamente `_id: ObjectId`. A aplicação frontend espera um campo `id: string`.
Para manter a compatibilidade perfeita sem acoplar o frontend ao MongoDB:
* Na camada Pydantic, define-se um tipo auxiliar ou validador com `BeforeValidator` / `Field(alias="_id")`:
```python
from pydantic import BaseModel, ConfigDict, Field
from bson import ObjectId

class MongoBaseModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={ObjectId: str}
    )
```
* O campo `_id` do documento é projetado e serializado na saída JSON como `id: str(doc["_id"])`.

---

## 5. Seed do Administrador Inicial

### 5.1 Requisitos e Comportamento
O seed deve ser executado automaticamente na inicialização da aplicação FastAPI através do manipulador de ciclo de vida `lifespan`:

1. **Variáveis de Ambiente:**
   * `ADMIN_INITIAL_EMAIL`: E-mail do administrador inicial (ex: `admin@clararosa.pt`).
   * `ADMIN_INITIAL_PASSWORD`: Senha inicial forte (ex: fornecida no deploy ou `.env`).
   * `ADMIN_INITIAL_NAME`: Nome de exibição (padrão: `"Administrador Clara Rosa"`).
   * `BOOTSTRAP_ADMIN_ENABLED`: Booleano (padrão `true`). Em ambientes de produção já provisionados, pode ser configurado para `false`.
2. **Idempotência e Segurança em Concorrência:**
   * O seed verifica se já existe algum utilizador com `email == ADMIN_INITIAL_EMAIL.lower()`.
   * **Caso 1: Nenhum usuário existe com o e-mail:**
     Cria o usuário com `role: "ADMIN"`, senha com hash bcrypt, `is_active: True`.
   * **Caso 2: Já existe usuário e o perfil é `ADMIN`:**
     Não faz nada. **Nunca altera a senha existente** nem sobrescreve dados de perfil.
   * **Caso 3: Já existe usuário, mas o perfil é `CUSTOMER`:**
     Emite um erro nos logs e **aborta o seed sem alterar nada**. O seed jamais promove silenciosamente um cliente a administrador.
   * **Proteção de Logs:** A senha e o hash nunca são impressos no console ou nos arquivos de log. Se as variáveis obrigatórias estiverem ausentes, o seed apenas avisa que o bootstrap foi ignorado por falta de credenciais.

---

## 6. Contratos OpenAPI (Endpoints, Schemas e Erros)

A API disponibilizará a documentação interativa em `/docs` (Swagger UI) e `/redoc`.

### 6.1 Formato Padronizado de Resposta de Erro
Todas as respostas de erro da API seguirão um formato consistente:
```json
{
  "detail": "Descrição legível do erro",
  "code": "ERROR_CODE_STRING",
  "field": "nome_do_campo_opcional"
}
```

### 6.2 Resumo dos Endpoints

#### Autenticação (`/api/v1/auth`)
* `POST /api/v1/auth/sign-in`
  * **Body:** `{"email": "admin@clararosa.pt", "password": "senha"}`
  * **200 OK:** `{"user": UserResponse, "access_token": "ey...", "token_type": "bearer", "refresh_token": "..."}`
  * **401 Unauthorized:** `{"detail": "Credenciais inválidas", "code": "INVALID_CREDENTIALS"}`
  * **403 Forbidden:** `{"detail": "Utilizador desativado", "code": "USER_INACTIVE"}`
* `POST /api/v1/auth/sign-up`
  * **Body:** `{"name": "Novo Cliente", "email": "novo@cliente.pt", "password": "senha"}`
  * **201 Created:** `{"user": UserResponse, "access_token": "ey...", "token_type": "bearer", "refresh_token": "..."}`
  * **409 Conflict:** `{"detail": "Este e-mail já está registado", "code": "EMAIL_ALREADY_EXISTS"}`
* `POST /api/v1/auth/refresh`
  * **Body:** `{"access_token": "ey...", "refresh_token": "..."}`
  * **200 OK:** `{"user": UserResponse, "access_token": "ey...", "token_type": "bearer", "refresh_token": "..."}`
  * **401 Unauthorized:** `{"detail": "Token expirado ou inválido", "code": "TOKEN_EXPIRED"}`
* `POST /api/v1/auth/sign-out`
  * **Headers:** `Authorization: Bearer <token>`
  * **200 OK:** `{"success": true}`

#### Utilizadores e Perfil (`/api/v1/users`)
* `GET /api/v1/users/me`
  * **Headers:** `Authorization: Bearer <token>`
  * **200 OK:** Retorna objeto `UserResponse` completo do utilizador autenticado.
* `PATCH /api/v1/users/me`
  * **Headers:** `Authorization: Bearer <token>`
  * **Body:** `{"name": "...", "dateOfBirth": "1990-01-01", "addresses": [...]}`
  * **200 OK:** `UserResponse` atualizado.
  * **409 Conflict:** `{"detail": "E-mail já está em uso", "code": "EMAIL_TAKEN"}` (caso altere email).

#### Catálogo Público (`/api/v1/products`)
* `GET /api/v1/products`
  * **Params:** `q`, `category`, `sort`
  * **200 OK:** `[ProductResponse, ...]` (apenas com `active: true`)
* `GET /api/v1/products/{slug}`
  * **200 OK:** `ProductResponse`
  * **404 Not Found:** `{"detail": "Produto não encontrado", "code": "PRODUCT_NOT_FOUND"}`

#### Categorias (`/api/v1/categories`)
* `GET /api/v1/categories`
  * **200 OK:** `[CategoryResponse, ...]`

#### Administração de Produtos (`/api/v1/admin/products`) — Protegido por `Role: ADMIN`
* `GET /api/v1/admin/products`
  * **200 OK:** `[ProductResponse, ...]` (inclui ativos e inativos)
* `GET /api/v1/admin/products/{id}`
  * **200 OK:** `ProductResponse`
  * **404 Not Found:** `{"detail": "Produto não encontrado", "code": "PRODUCT_NOT_FOUND"}`
* `POST /api/v1/admin/products`
  * **Body:** `ProductCreateRequest`
  * **201 Created:** `ProductResponse`
  * **409 Conflict:** `{"detail": "O slug já se encontra em uso", "code": "SLUG_ALREADY_EXISTS"}`
* `PATCH /api/v1/admin/products/{id}`
  * **Body:** `ProductUpdateRequest`
  * **200 OK:** `ProductResponse`
  * **409 Conflict:** `{"detail": "O slug já se encontra em uso", "code": "SLUG_ALREADY_EXISTS"}`
* `DELETE /api/v1/admin/products/{id}`
  * **204 No Content**
  * **404 Not Found**
