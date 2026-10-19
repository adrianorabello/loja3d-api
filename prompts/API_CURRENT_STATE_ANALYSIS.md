# Análise do Estado Atual: Frontend (Fuse Starter) e Backend (loja3d-api)

> **Data:** 18 de Outubro de 2026  
> **Status:** Diagnóstico arquitetural e levantamento de contratos  
> **Autor:** Arquiteto de Software / Desenvolvedor Sênior  

---

## 1. Contexto e Estrutura do Workspace

O repositório `clara-rosa-webstore` reúne a arquitetura de comércio eletrónico de impressão 3D voltada para o mercado de Portugal (EUR, pt-PT e en). A investigação abrangeu os seguintes diretórios reais do workspace:

| Identificador | Papel | Caminho Real no Sistema de Ficheiros |
|---|---|---|
| **Fuse starter** | **Aplicação real frontend** (Angular 11.2, Fuse 12.2, Angular Material, Tailwind, ngx-translate). Consumidor primário da API. | `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-app` |
| **loja3d-api** | **Aplicação backend** (Python 3.9, FastAPI, Pydantic). Destinado a fornecer a API REST e persistência no MongoDB. | `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-api` |
| **Loja-online-3d** | Protótipo visual React 19 / Figma Make. **Apenas referência visual/design**, sem código a ser reaproveitado no backend. | `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja-online-3D-responsiva` |
| **Fuse demo** | Template completo do Fuse. **Apenas referência de componentes e padrões Fuse**. | `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/fuse-demo-v12.2.0` |
| **prompts** | Documentação e planos de arquitetura globais do projeto. | `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/prompts` |

---

## 2. Diagnóstico Detalhado do Frontend (`loja3d-app`)

A aplicação Angular possui uma estrutura modular com domínios bem demarcados (`src/app/domains/` e `src/app/core/`). A navegação e o acesso são diferenciados entre a área pública da loja, a área do cliente e a área administrativa.

### 2.1 Telas de Cadastro, Edição e Fluxos Implementados

A investigação rastreou diretamente os componentes, formulários e serviços no código:

#### A. Administração de Produtos
* **Caminhos dos Arquivos:**
  * Lista: `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-app/src/app/domains/admin/products/list/product-list.component.ts`
  * Formulário (Novo/Edição): `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-app/src/app/domains/admin/products/form/product-form.component.ts`
  * Utilitários do formulário: `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-app/src/app/domains/admin/products/product-form.utils.ts`
* **Rotas:**
  * `/admin/products` (Listagem geral com filtros, paginação e ações rápidas)
  * `/admin/products/new` (Criação de produto)
  * `/admin/products/:id/edit` (Edição com resolver `ProductResolver`)
* **Campos e Validações no Formulário:**
  * `namePt`: string, `Validators.required` (gera automaticamente o `slug` na criação).
  * `nameEn`: string, opcional (com fallback no frontend para `pt-PT`).
  * `descriptionPt`: string, opcional.
  * `descriptionEn`: string, opcional.
  * `slug`: string, `Validators.required`, padrão regex `/^[a-z0-9]+(?:-[a-z0-9]+)*$/`. Deve ser único no catálogo.
  * `categoryId`: string, `Validators.required` (seleção a partir da lista de categorias).
  * `price`: numérico, `[Validators.required, Validators.min(0.01)]`. Representa valor monetário em EUR com até 2 casas decimais.
  * `dimensions`: subgrupo `{ width, height, depth }`, unidade implícita `'mm'`. Validador customizado `_validateDimensions`: dimensões são opcionais, mas caso qualquer uma seja preenchida, as três devem ser números finitos maiores que zero.
  * `stock`: inteiro, `[Validators.required, Validators.min(0), Validators.pattern(/^\d+$/)]`.
  * `colors`: `FormArray` com `{ name: string (required), hex: string (required, regex /^#[0-9a-fA-F]{6}$/) }`. O `id` da cor é gerado via `slugify(color.name)`.
  * `madeToOrder`: booleano (padrão `false`).
  * `active`: booleano (padrão `true`). Se falso, não aparece na vitrine pública.
  * `featured`: booleano (padrão `false`). Exibido em destaque na Home.
  * `images`: array de strings (base64 data URLs ou caminhos de asset). Validação: obrigatoriamente `images.length > 0`. Arquivos aceitam `image/jpeg` e `image/png`, com tamanho máximo de 2MB por arquivo (`MAX_IMAGE_BYTES = 2 * 1024 * 1024`).
* **Tratamento de Erros e Respostas:**
  * Código `409 Conflict`: mapeado para a mensagem `admin.products.slugTaken`.
  * Outros erros: exibem `admin.products.saveError`.

#### B. Perfil do Cliente e Gestão de Endereços
* **Caminho do Arquivo:**
  * Componente: `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-app/src/app/domains/customer/profile/profile.component.ts`
* **Rota:** `/account/profile` (protegida por `AuthGuard`).
* **Operações:**
  * Consulta do utilizador logado via `UserService.user$` (alimentado por `AuthService.signIn`, `signInUsingToken` ou `GET api/common/user`).
  * Edição dos dados pessoais:
    * `name`: string, `Validators.required`.
    * `email`: string, `[Validators.required, Validators.email]`.
    * `dateOfBirth`: string (opcional, formato ISO `YYYY-MM-DD`).
  * Gestão de Endereços (`UserAddress[]`) embutidos no documento do utilizador:
    * `id`: string (gerado no frontend como `address-${timestamp}-${seq}`).
    * `label`: string, `Validators.required` (ex: "Casa", "Trabalho").
    * `street`: string, `Validators.required`.
    * `unit`: string, opcional (andar, apartamento, bloco).
    * `postalCode`: string, `Validators.required` (formato típico PT `XXXX-XXX`).
    * `city`: string, `Validators.required`.
    * `country`: string, `Validators.required` (padrão "Portugal").
* **Comportamento de Persistência:**
  * Adicionar, editar ou remover endereços altera o array local de endereços do utilizador.
  * O salvamento consolidado ocorre através de `UserService.update(updatedUser)` via requisição HTTP `PATCH api/common/user` com corpo `{ user: updatedUser }`.
  * Se a API responder `409 Conflict`, o componente interpreta como `customerAccount.emailTaken`.

#### C. Autenticação e Gestão de Utilizadores
* **Caminhos dos Arquivos:**
  * Sign In: `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-app/src/app/modules/auth/sign-in/sign-in.component.ts`
  * Sign Up: `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-app/src/app/modules/auth/sign-up/sign-up.component.ts`
  * Forgot Password: `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-app/src/app/modules/auth/forgot-password/forgot-password.component.ts`
  * Reset Password: `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-app/src/app/modules/auth/reset-password/reset-password.component.ts`
  * Sign Out: `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-app/src/app/modules/auth/sign-out/sign-out.component.ts`
  * Serviço de Autenticação: `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-app/src/app/core/auth/auth.service.ts`
  * Tipos de Autenticação: `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-app/src/app/core/auth/auth.types.ts`
* **Formulários e Operações:**
  * **Sign In (`/sign-in`):**
    * Campos: `email` (required, email), `password` (required), `rememberMe` (booleano).
    * Envia: `POST api/auth/sign-in` com `{ email, password }`.
    * Espera: `SignInResponse` `{ user: User, access_token: string, token_type: string }`.
    * Armazena token em `localStorage.getItem('access_token')`.
    * Redireciona para `/signed-in-redirect`, onde o `SignedInRedirectGuard` direciona `ADMIN` para `/admin/products` e `CUSTOMER` para `/`.
  * **Sign Up (`/sign-up`):**
    * Campos: `name` (required), `email` (required, email), `password` (required, min 4 chars), `agreements` (requiredTrue).
    * Envia: `POST api/auth/sign-up` com `{ name, email, password }`.
    * Espera: `SignInResponse`. Já cria sessão imediata e redireciona para `/signed-in-redirect`.
    * Erro `409`: exibe mensagem de email já cadastrado.
  * **Forgot Password (`/forgot-password`):**
    * Envia: `POST api/auth/forgot-password` com string pura `email`.
    * No mock atual: sempre responde `[200, true]`. Não há envio de e-mail real configurado.
  * **Reset Password (`/reset-password`):**
    * Campos: `password` (required), `passwordConfirm` (required, mustMatch).
    * Envia: `POST api/auth/reset-password` com string pura `password`.
    * **Atenção:** O componente herdado do Fuse não lê token de recuperação da URL e não envia identificador do utilizador. Trata-se de um mock incompleto.
  * **Sign Out (`/sign-out`):**
    * Limpa `localStorage.removeItem('access_token')`. Atualmente não efetua chamada ao backend.

#### D. Vitrine Pública e Consumo do Catálogo
* **Caminhos dos Arquivos:**
  * Home: `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-app/src/app/domains/storefront/home/home.page.ts`
  * Catálogo / Kids Store: `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-app/src/app/domains/storefront/kids-store/kids-store.component.ts`
  * Detalhe de Produto: `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-app/src/app/domains/storefront/product-details/product-details.component.ts`
  * Serviço de Produto: `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-app/src/app/core/product/product.service.ts`
  * Serviço de Categorias: `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-app/src/app/core/category/category.service.ts`
* **Operações:**
  * Listagem pública com filtros: `GET ${baseUrl}/products` com parâmetros `q`, `category`, `sort`.
  * Detalhe do produto por slug: `GET ${baseUrl}/products/${slug}`.
  * Listagem de categorias: `GET ${baseUrl}/categories`.
  * **Carrinho de Compras (`CartService`):** puramente em `localStorage` (`clara_rosa_cart`). O projeto deliberadamente não possui persistência de carrinho ou checkout no backend nesta fase.

---

### 2.2 Análise dos Mocks, Interceptors e Configuração de API

#### A. A Armadilha do `AuthInterceptor` (Comportamento Crítico)
No arquivo `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-app/src/app/core/auth/auth.interceptor.ts`:
```typescript
if ( error instanceof HttpErrorResponse && error.status === 401 )
{
    // Sign out
    this._authService.signOut();

    // Reload the app
    location.reload();
}
```
* **O Problema:** Caso um utilizador digite a senha errada no login (`POST api/auth/sign-in`), se o backend responder `401 Unauthorized` (que é o padrão REST canónico), o `AuthInterceptor` intercepta o erro, limpa o token e executa `location.reload()`. Isso faz a página piscar/recarregar imediatamente e apaga qualquer alerta de erro para o utilizador.
* **Evidência Histórica no Mock:** No mock Fuse (`mock-api/common/auth/api.ts`), o autor do mock contornou isso devolvendo deliberadamente `404 Not Found` no sign-in quando as credenciais eram inválidas!
* **Ajuste Obrigatório no Frontend:** O `AuthInterceptor` deve ignorar respostas 401 originadas em rotas públicas de autenticação (como `/sign-in` e `/sign-up`), tratando o 401 com `signOut() + reload()` apenas em rotas protegidas cujo token expirou ou é inválido.

#### B. Disparidade de Prefixo de Endpoints (`API_BASE_URL`)
* `ProductService` e `CategoryService` utilizam `@Inject(API_BASE_URL) private _baseUrl: string` (definido no ambiente como `'api/clara-rosa'`).
* `AuthService` utiliza caminhos relativos hardcoded: `'api/auth/sign-in'`, `'api/auth/sign-up'`, `'api/auth/refresh-access-token'`.
* `UserService` utiliza caminho relativo hardcoded: `'api/common/user'`.
* `InitialDataResolver` chama `'api/common/messages'`, `'api/common/navigation'`, `'api/common/notifications'`, `'api/common/shortcuts'`, `'api/common/user'`.
* **Conclusão:** Para integrar com uma API real sem manter múltiplos prefixos caóticos, a API deve expor rotas padronizadas (ex: `/api/v1/...` ou `/api/...`), e os serviços do Angular devem unificar a injeção do `API_BASE_URL`.

#### C. Chave de Desativação do Mock (`useMockApi`)
Em `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-app/src/app/app.module.ts`:
```typescript
...(environment.useMockApi ? [FuseMockApiModule.forRoot(mockApiServices)] : [])
```
Ao definir `useMockApi: false` em `environment.ts`, o interceptor de mock sequer é instanciado, liberando as chamadas HTTP para o endereço configurado em `environment.apiBaseUrl`.

---

## 3. Diagnóstico Detalhado do Backend (`loja3d-api`)

A inspeção em `/Users/adriano.rabello/Developer/projects/clara_rosa/clara-rosa-webstore/loja3d-api` revelou o estado atual do projeto backend:

### 3.1 Tecnologias e Ambiente Atual
* **Interpretador Python:** Python 3.9.6 (ambiente virtual configurado em `loja3d-api/.venv`).
* **Framework:** FastAPI `0.128.8` sobre Starlette `0.49.3` e Uvicorn `0.39.0`.
* **Validação:** Pydantic `2.13.5` e Pydantic-Settings `2.11.0`.
* **Ponto de Entrada:** Ficheiro único `loja3d-api/main.py` (33 linhas).
* **Dependências Faltantes:**
  * Nenhum ficheiro `requirements.txt` ou `pyproject.toml` versionado.
  * Nenhum driver MongoDB instalado (`motor` ou `pymongo` ausentes).
  * Nenhuma biblioteca de hash de senha instalada (`passlib`, `bcrypt` ou `argon2` ausentes).
  * Nenhuma biblioteca JWT instalada (`python-jose` ou `pyjwt` ausentes).
  * Nenhum suporte a testes (`pytest` ausente).
  * Nenhum ficheiro `.env` ou `.env.example`.

### 3.2 Código Atual de `loja3d-api/main.py`
O ficheiro atual contém apenas um esboço inicial em memória:
```python
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="Loja 3D API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://localhost:4201"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

class Product(BaseModel):
    id: int
    name: str
    price_cents: int = Field(ge=0)
    image_url: Optional[str] = None
    width_cm: float = Field(gt=0)
    height_cm: float = Field(gt=0)
    depth_cm: float = Field(gt=0)
    active: bool = True

products = [
    Product(id=1, name="Suporte de celular", price_cents=750, width_cm=8, height_cm=12, depth_cm=10)
]

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/products", response_model=list[Product])
def list_products():
    return [product for product in products if product.active]
```

### 3.3 Discrepâncias entre o Modelo do Backend Atual e o Frontend
1. **Identificador de Produto:** O backend usa `int` sequencial (`id: 1`), enquanto o frontend espera `string` (`id: "prd-..."` ou string hexadecimal do MongoDB `_id`).
2. **Internacionalização (i18n):** O backend usa `name: str`. O frontend exige `name: LocalizedText` (`{"pt-PT": str, "en": str}`) e `description: LocalizedText`.
3. **Preço:** O backend usa `price_cents: int`. O frontend trabalha com `price: float` (EUR, ex: `15.00`). No banco deve ser persistido como cêntimos ou `Decimal128` para evitar erros de ponto flutuante, mas exposto/convertido adequadamente na API.
4. **Dimensões:** O backend usa `width_cm`, `height_cm`, `depth_cm`. O frontend espera um objeto aninhado `dimensions: { width: float, height: float, depth: float, unit: "mm" }` em milímetros.
5. **Cores:** O backend não possui suporte a cores. O frontend exige array `colors: [{ id: str, name: LocalizedText, hex: str }]`.
6. **Imagens:** O backend possui `image_url: Optional[str]`. O frontend envia `images: list[str]` (múltiplas imagens em base64 ou URL).
7. **Campos Adicionais Faltantes no Backend:** `slug` (obrigatório, indexado), `categoryId`, `currency` ("EUR"), `stock`, `madeToOrder`, `featured`, `createdAt`.
8. **CORS:** O middleware atual permite apenas `allow_methods=["GET"]` e `allow_credentials=False`. A aplicação precisa de `POST`, `PATCH`, `PUT`, `DELETE`, `OPTIONS` e suporte a `Authorization` header.

---

## 4. Classificação de Funcionalidades: Prontas vs Parciais vs Demonstrativas

| Funcionalidade / Tela | Classificação | Situação no Frontend | Situação no Backend Atual | Necessidade para Produção |
|---|---|---|---|---|
| **Catálogo Público de Produtos** | Pronta no frontend | Consome `ProductService.getProducts()` com filtros e ordenação | Rota GET rudimentar com modelo divergente | Adequar modelo Pydantic, integrar filtros MongoDB (`q`, `category`, `sort`) |
| **Detalhe de Produto (`/products/:slug`)** | Pronta no frontend | Busca por `slug`, trata 404 redirecionando | Inexistente | Criar rota `GET /api/v1/products/{slug}` |
| **Lista Admin de Produtos (`/admin/products`)** | Pronta no frontend | `MatTableDataSource`, pesquisa, toggle ativo, remoção | Inexistente | Criar rota protegida `GET /api/v1/admin/products` e `PATCH/DELETE` |
| **Formulário de Produto (`/admin/products/new`, edit)** | Pronta no frontend | Validações completas, upload de fotos (2MB), slug automático | Inexistente | Criar rotas protegidas `POST /api/v1/products` e `PATCH /api/v1/products/{id}` com validações de conflito (409) |
| **Categorias de Produtos** | Pronta no frontend | `CategoryService.getCategories()` | Inexistente | Criar coleção `categories` e rota `GET /api/v1/categories` |
| **Perfil do Cliente (`/account/profile`)** | Pronta no frontend | Edição de dados pessoais e gestão de endereços embutidos | Inexistente | Criar `GET /api/v1/users/me` e `PATCH /api/v1/users/me` |
| **Sign In (`/sign-in`)** | Pronta no frontend | Form reativo, validações, token em localStorage | Inexistente | Criar `POST /api/v1/auth/sign-in` com hash bcrypt e JWT |
| **Sign Up (`/sign-up`)** | Pronta no frontend | Form reativo, aceitação de termos, cria CUSTOMER | Inexistente | Criar `POST /api/v1/auth/sign-up` exclusivo para CUSTOMER |
| **Sign Out (`/sign-out`)** | Pronta no frontend | Limpa token local | Inexistente | Criar rota `POST /api/v1/auth/sign-out` para revogação de sessão |
| **Renovação de Sessão (`check()`)** | Pronta no frontend | Envia token para renovação ao iniciar app | Inexistente | Criar rota `POST /api/v1/auth/refresh` |
| **Forgot Password** | Parcial / Demonstrativa | Formulário existe, mas mock responde true sem backend | Inexistente | Definir se haverá envio de e-mail (requer SMTP/serviço externo) ou se permanecerá suspenso |
| **Reset Password** | Demonstrativa / Incompleta | Componente não recebe token de redefinição via query param | Inexistente | Requer redesenho do fluxo com token assinado e expiração se for implementado |
| **Carrinho de Compras** | Pronta (Client-Side) | Persistido exclusivamente em `localStorage` (`CartService`) | Não aplicável | Não persistir no backend nesta fase (conforme diretriz arquitetural) |

---

## 5. Lacunas e Riscos Identificados

1. **Inconsistência nos Contratos de Preço e Moeda:**
   * O frontend trabalha com `price` em ponto flutuante (ex: `15.00` EUR). No MongoDB, armazenar float diretamente causa erros de arredondamento IEEE-754.
   * **Recomendação:** A API deve persistir `price_cents` (inteiro) no MongoDB e serializar como `price` (float arredondado a 2 casas) no schema Pydantic de saída para o Angular.
2. **Gestão de Imagens (Uploads):**
   * O formulário do admin atualmente converte imagens para strings base64 (até 2MB por ficheiro) e as inclui diretamente no payload JSON do produto.
   * Colocar strings base64 pesadas diretamente no documento MongoDB pode degradar a performance e atingir o limite BSON de 16MB por documento se um produto tiver muitas fotos.
   * **Recomendação Proporcional:** Para o estágio atual (MVP inicial), aceitar as imagens em base64 com limite estrito de fotos por produto (ex: máximo 5 fotos de 2MB) ou armazená-las no sistema de ficheiros local/estático servido pelo FastAPI (`/static/uploads`), guardando apenas URLs no banco.
3. **Segurança de Endpoints de Utilizador:**
   * O Angular atualmente chama `PATCH api/common/user` enviando `{ user: updatedUser }`.
   * **Vulnerabilidade Potencial:** Se a API aceitar o objeto `user` sem filtragem estrita, um utilizador mal-intencionado poderia tentar enviar `role: "ADMIN"` no payload para se auto-promover.
   * **Defesa Obrigatória:** O schema Pydantic de atualização de perfil do cliente (`UserProfileUpdate`) deve permitir **exclusivamente** `name`, `dateOfBirth` e `addresses`. O campo `role` e `email` (ou verificação de email) devem ser geridos sob regras estritas do servidor, nunca aceitando alteração de privilégio via payload.
4. **Seed do Administrador:**
   * Não existe qualquer mecanismo de provisionamento ou usuário administrador persistido. O seed deve rodar no evento `lifespan` do FastAPI, sendo 100% idempotente.
