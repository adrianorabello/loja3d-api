const fs = require('node:fs');
const path = require('node:path');

const script = (listen, source) => ({
    listen,
    script: {
        type: 'text/javascript',
        exec: (listen === 'test' ? `(() => {\n${source.trim()}\n})();` : source.trim()).split('\n')
    }
});

const userChecks = `
pm.test("Perfil sem dados sensiveis", function () {
    pm.expect(data.id).to.be.a("string").and.not.empty;
    pm.expect(data.email).to.be.a("string").and.not.empty;
    pm.expect(data.role).to.eql("CUSTOMER");
    ["password", "password_hash", "token_hash"].forEach(key => pm.expect(data).not.to.have.property(key));
});`;

const productChecks = `
pm.test("Contrato do produto", function () {
    pm.expect(data.id).to.be.a("string").and.not.empty;
    pm.expect(data.slug).to.be.a("string").and.not.empty;
    pm.expect(data.name).to.have.property("pt-PT");
    pm.expect(data.price).to.be.a("number").and.above(0);
    pm.expect(data.currency).to.eql("EUR");
    pm.expect(data.stock).to.be.a("number").and.at.least(0);
    pm.expect(data.active).to.be.a("boolean");
    pm.expect(data.images).to.be.an("array");
    pm.expect(data.createdAt).to.be.a("string");
});`;

function request(name, method, route, {
    status = 200, body, token, writes = false, checks = '', before = '', description = ''
} = {}) {
    const event = [];
    const guard = writes ? `
if (pm.variables.get("allowWrites") !== "true") {
    console.warn("IGNORADO (altera dados): " + pm.info.requestName + ". Defina allowWrites=true para executar.");
    pm.execution.skipRequest();
} else {
    if (!pm.variables.get("adminEmail") || !pm.variables.get("adminPassword")) {
        pm.execution.skipRequest();
        throw new Error("Defina adminEmail e adminPassword antes de habilitar allowWrites.");
    }
    ${before}
}` : before;
    if (guard.trim()) event.push(script('prerequest', guard));
    event.push(script('test', `
pm.test("HTTP ${status}", function () { pm.response.to.have.status(${status}); });
${status === 204 ? `
pm.test("Resposta sem corpo", function () { pm.expect(pm.response.text()).to.eql(""); });
` : `
pm.test("Content-Type JSON", function () {
    pm.expect(pm.response.headers.get("Content-Type")).to.match(/application\\/json/i);
});
const data = pm.response.json();
${status >= 400 ? 'pm.test("Erro explicito", function () { pm.expect(data).to.have.property("detail"); });' : ''}
${checks}
`}
`));
    return {
        name,
        event,
        request: {
            method,
            header: body === undefined ? [] : [{ key: 'Content-Type', value: 'application/json' }],
            auth: token
                ? { type: 'bearer', bearer: [{ key: 'token', value: `{{${token}}}`, type: 'string' }] }
                : { type: 'noauth' },
            url: `{{baseUrl}}${route}`,
            description: `${writes ? 'ALTERA DADOS. Requer allowWrites=true e credenciais de administrador. ' : ''}${description}`,
            ...(body === undefined ? {} : {
                body: { mode: 'raw', raw: JSON.stringify(body, null, 2), options: { raw: { language: 'json' } } }
            })
        }
    };
}

function sessionChecks(role, store = true) {
    return `
pm.test("Sessao ${role}", function () {
    pm.expect(data.user.role).to.eql("${role}");
    pm.expect(data.access_token).to.be.a("string").and.not.empty;
    pm.expect(data.refresh_token).to.be.a("string").and.not.empty;
    pm.expect(data.token_type).to.eql("bearer");
    pm.expect(data.user).not.to.have.property("password_hash");
});
${store ? `
if (pm.response.code === 200 || pm.response.code === 201) {
    pm.variables.set("${role === 'ADMIN' ? 'adminToken' : 'customerToken'}", data.access_token);
    pm.variables.set("${role === 'ADMIN' ? 'adminRefresh' : 'customerRefresh'}", data.refresh_token);
}` : ''}`;
}

const messageChecks = 'pm.test("Mensagem explicita", function () { pm.expect(data.message).to.be.a("string").and.not.empty; });';
const customer = { writes: true, token: 'customerToken' };
const admin = { writes: true, token: 'adminToken' };
const credentials = { email: '{{customerEmail}}', password: '{{customerPassword}}' };
const product = {
    slug: '{{productSlug}}',
    name: { 'pt-PT': 'Produto Postman', en: 'Postman product' },
    description: { 'pt-PT': 'Criado pelo teste automatizado', en: 'Created by automated test' },
    categoryId: '{{categoryId}}',
    price: 12.35,
    currency: 'EUR',
    dimensions: { width: 20, height: 30, depth: 40, unit: 'mm' },
    colors: [{ id: 'blue', name: { 'pt-PT': 'Azul', en: 'Blue' }, hex: '#0000ff' }],
    images: [],
    stock: 3,
    active: true,
    madeToOrder: false,
    featured: false
};

function suite(label, prefix, catalog, suiteId) {
    const auth = `${prefix}/auth`;
    const items = [];
    const add = (...args) => items.push(request(...args));
    add('Categorias e categoria para o produto de teste', 'GET', `${catalog}/categories`, {
        before: `
pm.variables.set("customerEmail", "postman-${suiteId}-" + pm.variables.get("runId") + "@" + pm.variables.get("testEmailDomain"));
pm.variables.set("productSlug", "postman-${suiteId}-" + pm.variables.get("runId"));
["customerToken", "customerRefresh", "adminToken", "adminRefresh", "productId", "legacyProductId", "oldRefresh", "aliasRefresh", "aliasCustomerToken", "signOutRefresh", "printRequestId", "printRequestVersion", "printQuoteVersion", "createdPrintRequestIds"].forEach(key => pm.variables.set(key, ""));`,
        checks: `
pm.test("Categorias disponiveis", function () {
    pm.expect(data).to.be.an("array").and.not.empty;
    data.forEach(category => {
        pm.expect(category.id).to.be.a("string").and.not.empty;
        pm.expect(category.slug).to.be.a("string");
        pm.expect(category.name).to.have.property("pt-PT");
    });
});
if (data.length) pm.variables.set("categoryId", data[0].id);`
    });
    add('Produtos publicos', 'GET', `${catalog}/products`, {
        checks: 'pm.test("Lista publica", function () { pm.expect(data).to.be.an("array"); data.forEach(p => pm.expect(p.active).to.eql(true)); });'
    });
    add('Produto inexistente', 'GET', `${catalog}/products/postman-missing-{{runId}}`, { status: 404 });
    add('Perfil sem autenticacao', 'GET', `${prefix}/users/me`, { status: 401 });
    add('Administracao sem autenticacao', 'GET', `${catalog}/admin/products`, { status: 401 });
    add('Cadastro invalido', 'POST', `${auth}/sign-up`, {
        status: 422, writes: true, body: { name: 'X', email: 'invalid', password: 'short' }
    });
    add('Cadastrar cliente', 'POST', `${auth}/sign-up`, {
        status: 201, writes: true,
        body: { name: 'Cliente Postman', ...credentials, confirmPassword: '{{customerPassword}}', dateOfBirth: '2000-01-15' },
        checks: sessionChecks('CUSTOMER') + `
pm.test("Email da conta criada", function () { pm.expect(data.user.email).to.eql(pm.variables.get("customerEmail")); });`
    });
    add('Cadastro duplicado', 'POST', `${auth}/sign-up`, {
        status: 409, writes: true, body: { name: 'Cliente Postman', ...credentials }
    });
    add('Alias register', 'POST', `${auth}/register`, {
        status: 201, writes: true,
        body: { name: 'Alias Postman', email: 'postman-alias-' + suiteId + '-{{runId}}@{{testEmailDomain}}', password: '{{customerPassword}}' },
        checks: sessionChecks('CUSTOMER', false) + `
if (pm.response.code === 201) {
    pm.variables.set("aliasRefresh", data.refresh_token);
    pm.variables.set("aliasCustomerToken", data.access_token);
}`
    });
    add('Login incorreto', 'POST', `${auth}/sign-in`, {
        status: 401, writes: true, body: { email: '{{customerEmail}}', password: 'Incorrect-{{runId}}' }
    });
    add('Login cliente', 'POST', `${auth}/sign-in`, {
        writes: true, body: credentials, checks: sessionChecks('CUSTOMER')
    });
    add('Alias login', 'POST', `${auth}/login`, {
        writes: true, body: credentials, checks: sessionChecks('CUSTOMER')
    });
    add('Sessao atual', 'GET', `${auth}/me`, { ...customer, checks: userChecks });
    add('Perfil atual', 'GET', `${prefix}/users/me`, { ...customer, checks: userChecks });
    const profile = {
        name: 'Cliente Postman Atualizado',
        phone: '+351912345678', phoneCountry: 'PT', dateOfBirth: '2000-01-15',
        addresses: [{ id: 'postman-address', label: 'Teste', street: 'Rua de Teste, 1', postalCode: '4000-123', city: 'Porto', country: 'Portugal' }]
    };
    add('Atualizar perfil e morada', 'PATCH', `${prefix}/users/me`, {
        ...customer, body: profile, checks: userChecks + `
pm.test("Dados persistidos", function () {
    pm.expect(data.name).to.eql("Cliente Postman Atualizado");
    pm.expect(data.phone).to.eql("+351912345678");
    pm.expect(data.phoneCountry).to.eql("PT");
    pm.expect(data.dateOfBirth).to.eql("2000-01-15");
    pm.expect(data.addresses).to.have.lengthOf(1);
    pm.expect(data.addresses[0].postalCode).to.eql("4000-123");
});`
    });
    add('Alias common/user', 'GET', `${prefix}/common/user`, { ...customer, checks: userChecks });
    add('Atualizar perfil no formato Fuse e impedir elevacao de permissao', 'PATCH', `${prefix}/common/user`, {
        ...customer, body: { user: { name: 'Cliente Fuse Postman', role: 'ADMIN', emailVerified: true } },
        checks: userChecks + `
pm.test("Formato Fuse e campos protegidos", function () {
    pm.expect(data.name).to.eql("Cliente Fuse Postman");
    pm.expect(data.emailVerified).to.eql(false);
});`
    });
    add('Consultar persistencia do perfil', 'GET', `${prefix}/users/me`, {
        ...customer, checks: userChecks + 'pm.test("Nome persistido", function () { pm.expect(data.name).to.eql("Cliente Fuse Postman"); });'
    });
    add('Impedir alteracao direta de email', 'PATCH', `${prefix}/users/me`, {
        ...customer, status: 400, body: { email: 'postman-new-{{runId}}@{{testEmailDomain}}' }
    });
    add('Reenviar verificacao de email', 'POST', `${auth}/resend-verification`, {
        writes: true, body: { email: '{{customerEmail}}' }, checks: messageChecks
    });
    add('Rejeitar verificacao com token invalido', 'POST', `${auth}/verify-email`, {
        writes: true, status: 400, body: { token: 'invalid-postman-{{runId}}' }
    });
    add('Solicitar recuperacao de senha', 'POST', `${auth}/forgot-password`, {
        writes: true, body: { email: '{{customerEmail}}' }, checks: messageChecks
    });
    add('Rejeitar reset com token invalido', 'POST', `${auth}/reset-password`, {
        writes: true, status: 400, body: { token: 'invalid-postman-{{runId}}', password: '{{customerPassword}}' }
    });
    add('Solicitar alteracao de email', 'POST', `${prefix}/users/me/email-change`, {
        ...customer, body: { newEmail: `postman-change-${suiteId}-{{runId}}@{{testEmailDomain}}`, password: '{{customerPassword}}' },
        checks: messageChecks
    });
    add('Rejeitar confirmacao de alteracao com token invalido', 'POST', `${prefix}/users/me/email-change/confirm`, {
        ...customer, status: 400, body: { token: 'invalid-postman-{{runId}}' }
    });
    add('Rotacionar refresh token', 'POST', `${auth}/refresh`, {
        writes: true, body: { refresh_token: '{{customerRefresh}}' },
        before: 'pm.variables.set("oldRefresh", pm.variables.get("customerRefresh"));',
        checks: sessionChecks('CUSTOMER') + `
pm.test("Refresh foi rotacionado", function () { pm.expect(data.refresh_token).not.to.eql(pm.variables.get("oldRefresh")); });`
    });
    add('Rejeitar reutilizacao do refresh anterior', 'POST', `${auth}/refresh`, {
        writes: true, status: 401, body: { refresh_token: '{{oldRefresh}}' }
    });
    add('Alias refresh-access-token com fallback access_token', 'POST', `${auth}/refresh-access-token`, {
        writes: true, body: { access_token: '{{customerToken}}' },
        before: 'pm.variables.set("signOutRefresh", pm.variables.get("customerRefresh"));',
        checks: sessionChecks('CUSTOMER')
    });
    add('Cliente sem permissao administrativa', 'GET', `${catalog}/admin/products`, { ...customer, status: 403 });
    add('Login administrador', 'POST', `${auth}/sign-in`, {
        writes: true, body: { email: '{{adminEmail}}', password: '{{adminPassword}}' }, checks: sessionChecks('ADMIN')
    });
    add('Listar produtos administrativos', 'GET', `${catalog}/admin/products`, {
        ...admin, checks: 'pm.test("Lista administrativa", function () { pm.expect(data).to.be.an("array"); });'
    });
    add('Criar produto de teste', 'POST', `${catalog}/admin/products`, {
        ...admin, status: 201, body: product,
        checks: productChecks + `
if (pm.response.code === 201) pm.variables.set("productId", data.id);
pm.test("Preco e slug da criacao", function () {
    pm.expect(data.price).to.eql(12.35);
    pm.expect(data.slug).to.eql(pm.variables.get("productSlug"));
});`
    });
    add('Rejeitar slug duplicado', 'POST', `${catalog}/admin/products`, {
        ...admin, status: 409, body: product
    });
    add('Consultar produto administrativo', 'GET', `${catalog}/admin/products/{{productId}}`, {
        ...admin, checks: productChecks
    });
    add('Consultar produto publico por slug', 'GET', `${catalog}/products/{{productSlug}}`, {
        ...customer, checks: productChecks
    });
    add('Filtrar produtos por pesquisa e categoria, ordenar por preco', 'GET', `${catalog}/products?q={{productSlug}}&category={{categoryId}}&sort=price-asc`, {
        ...customer, checks: `
pm.test("Filtro encontra apenas o produto criado", function () {
    pm.expect(data).to.be.an("array").with.lengthOf(1);
    pm.expect(data[0].id).to.eql(pm.variables.get("productId"));
    pm.expect(data[0].categoryId).to.eql(pm.variables.get("categoryId"));
});`
    });
    add('Atualizar preco, stock e visibilidade', 'PATCH', `${catalog}/admin/products/{{productId}}`, {
        ...admin, body: { price: 15.99, stock: 7, active: false },
        checks: productChecks + `
pm.test("Alteracoes aplicadas", function () {
    pm.expect(data.price).to.eql(15.99);
    pm.expect(data.stock).to.eql(7);
    pm.expect(data.active).to.eql(false);
});`
    });
    add('Produto inativo oculto da loja', 'GET', `${catalog}/products/{{productSlug}}`, { ...customer, status: 404 });
    add('Alias product - criar com envelope Fuse', 'POST', `${catalog}/product`, {
        ...admin, status: 201, body: { product: { ...product, slug: '{{productSlug}}-legacy' } },
        checks: productChecks + 'if (pm.response.code === 201) pm.variables.set("legacyProductId", data.id);'
    });
    add('Alias product - consultar', 'GET', `${catalog}/product/{{legacyProductId}}`, { ...admin, checks: productChecks });
    add('Alias product - atualizar com envelope Fuse', 'PATCH', `${catalog}/product`, {
        ...admin, body: { id: '{{legacyProductId}}', product: { price: 9.95, stock: 2 } },
        checks: productChecks + 'pm.test("Preco atualizado no alias", function () { pm.expect(data.price).to.eql(9.95); });'
    });
    add('Eliminar apenas produto criado pelo teste', 'DELETE', `${catalog}/admin/products/{{productId}}`, {
        ...admin, status: 204,
        before: 'if (!pm.variables.get("productId")) { pm.execution.skipRequest(); throw new Error("Criacao do produto falhou; eliminacao bloqueada."); }'
    });
    add('Confirmar eliminacao', 'GET', `${catalog}/admin/products/{{productId}}`, { ...admin, status: 404 });
    add('Alias product - eliminar apenas produto criado pelo teste', 'DELETE', `${catalog}/product?id={{legacyProductId}}`, {
        ...admin, status: 204,
        before: 'if (!pm.variables.get("legacyProductId")) { pm.execution.skipRequest(); throw new Error("Criacao do produto legado falhou; eliminacao bloqueada."); }'
    });
    if (suiteId === 'v1') {
        items.push({ name: 'Pedidos personalizados - fluxo ordenado', item: printRequestCases() });
    }
    add('Terminar sessao da conta criada pelo alias register', 'POST', `${auth}/logout`, {
        writes: true, body: { refresh_token: '{{aliasRefresh}}' }, checks: messageChecks
    });
    add('Logout revoga refresh token', 'POST', `${auth}/logout`, {
        writes: true, body: { refresh_token: '{{customerRefresh}}' }, checks: messageChecks
    });
    add('Refresh revogado pelo logout', 'POST', `${auth}/refresh`, {
        writes: true, status: 401, body: { refresh_token: '{{customerRefresh}}' }
    });
    add('Sign-out revoga todas as sessoes do cliente', 'POST', `${auth}/sign-out`, {
        ...customer, checks: 'pm.test("Sign-out concluido", function () { pm.expect(data.success).to.eql(true); });'
    });
    add('Refresh revogado pelo sign-out', 'POST', `${auth}/refresh`, {
        writes: true, status: 401, body: { refresh_token: '{{signOutRefresh}}' }
    });
    add('Terminar apenas a sessao administrativa criada pelo teste', 'POST', `${auth}/logout`, {
        writes: true, body: { refresh_token: '{{adminRefresh}}' }, checks: messageChecks
    });
    return { name: label, item: items };
}

function printRequestCases() {
    const items = [];
    const root = '/api/v1/print-requests';
    const adminRoot = '/api/v1/admin/print-requests';
    const own = `${root}/{{printRequestId}}`;
    const managed = `${adminRoot}/{{printRequestId}}`;
    const checkDocument = `
pm.test("Contrato tipado do pedido", function () {
    ["id", "reference", "ownerId", "customerName", "customerEmail", "title", "description", "dimensions", "status"].forEach(key => {
        pm.expect(data[key], key).to.be.a("string").and.not.empty;
    });
    pm.expect(data.quantity).to.be.a("number").and.above(0);
    pm.expect(data.version).to.be.a("number").and.at.least(1);
    ["referenceLinks", "quotes", "history", "allowedActions", "allowedTransitions"].forEach(key => pm.expect(data[key], key).to.be.an("array"));
    ["createdAt", "updatedAt"].forEach(key => pm.expect(data[key]).to.match(/Z$/));
    data.quotes.forEach(quote => {
        pm.expect(quote.amountCents).to.be.a("number").and.above(0);
        pm.expect(quote.currency).to.eql("EUR");
        pm.expect(quote.validUntil).to.match(/Z$/);
        pm.expect(quote.createdAt).to.match(/Z$/);
        if (quote.approvedAt !== undefined) pm.expect(quote.approvedAt).to.be.a("string").and.match(/Z$/);
    });
    ["material", "color", "trackingUrl", "estimatedShipping"].forEach(key => {
        if (data[key] !== undefined) pm.expect(data[key], key).to.be.a("string");
    });
    ["password_hash", "internalNotes", "allowed_actions", "allowed_transitions"].forEach(key => pm.expect(data).not.to.have.property(key));
});
if (pm.response.code === 200 || pm.response.code === 201) {
    pm.variables.set("printRequestVersion", data.version);
    if (data.quotes.length) pm.variables.set("printQuoteVersion", data.quotes[data.quotes.length - 1].version);
}`;
    const guardCreatedId = `
const created = JSON.parse(pm.variables.get("createdPrintRequestIds") || "[]");
if (!created.includes(pm.variables.get("printRequestId"))) {
    pm.execution.skipRequest();
    throw new Error("Pedido nao criado nesta execucao; operacao bloqueada.");
}`;
    const captureCreate = `
if (pm.response.code === 201) {
    const created = JSON.parse(pm.variables.get("createdPrintRequestIds") || "[]");
    created.push(data.id);
    pm.variables.set("createdPrintRequestIds", JSON.stringify(created));
    pm.variables.set("printRequestId", data.id);
    pm.variables.set("printRequestVersion", data.version);
    pm.variables.set("printQuoteVersion", "");
}`;
    const createBody = {
        title: 'Pedido Postman {{runId}}',
        description: 'Peca de demonstracao criada apenas na base de testes isolada.',
        quantity: 1, dimensions: '20 x 30 x 40 mm', material: 'PLA', color: 'Azul',
        referenceLinks: ['https://example.com/model.stl']
    };
    const step = (name, method, route, options = {}) => {
        const {
            status = 200, state, checks = '', before = '', body,
            token = 'customerToken', existing = true, stale = false, quote = false
        } = options;
        items.push(request(name, method, route, {
            writes: true, token, status, body,
            before: `${existing ? guardCreatedId : ''}
${body && Object.hasOwn(body, 'version') ? `
const payload = JSON.parse(pm.request.body.raw);
payload.version = Number(pm.variables.get("printRequestVersion"))${stale ? ' - 1' : ''};
${Object.hasOwn(body, 'quoteVersion') ? 'payload.quoteVersion = Number(pm.variables.get("printQuoteVersion"));' : ''}
${quote ? 'payload.validUntil = new Date(Date.now() + 7 * 86400000).toISOString();' : ''}
pm.request.body.update(JSON.stringify(payload));
` : ''}
${before}`,
            checks: `${status < 300 && state ? checkDocument : ''}
${state ? `pm.test("Estado ${state}", function () { pm.expect(data.status).to.eql("${state}"); });` : ''}
${checks}`
        }));
    };
    const create = name => step(name, 'POST', root, {
        status: 201, existing: false, body: createBody, state: 'submitted', checks: captureCreate
    });
    const transition = (name, state, options = {}) => step(name, 'POST', `${managed}/transition`, {
        state, token: 'adminToken',
        body: { version: 1, status: state, message: `Teste manual: ${state}.`, ...options.body },
        ...Object.fromEntries(Object.entries(options).filter(([key]) => key !== 'body'))
    });
    const publish = (name, amountCents) => step(name, 'POST', `${managed}/quote`, {
        state: 'awaiting_quote_approval', token: 'adminToken', quote: true,
        body: { version: 1, amountCents, currency: 'EUR', scope: 'Peca em PLA azul.', leadDays: 7, validUntil: '2030-01-01T00:00:00Z' }
    });
    const action = (name, actionName, state, message, options = {}) => step(name, 'POST', `${own}/actions`, {
        state, body: {
            version: 1, action: actionName, message,
            ...(actionName === 'cancel' ? {} : { quoteVersion: 1 })
        }, ...options
    });
    const pageChecks = `
pm.test("Paginacao, pesquisa e filtro", function () {
    pm.expect(data.page).to.eql(1);
    pm.expect(data.pageSize).to.eql(1);
    pm.expect(data.total).to.eql(1);
    pm.expect(data.items).to.have.lengthOf(1);
    pm.expect(data.items[0].id).to.eql(pm.variables.get("printRequestId"));
    pm.expect(data.items[0].status).to.eql("submitted");
});`;
    items.push(request('Pedidos cliente sem autenticacao', 'GET', root, { status: 401 }));
    items.push(request('Pedidos admin sem autenticacao', 'GET', adminRoot, { status: 401 }));
    create('Criar pedido personalizado');
    step('Ler pedido persistido do cliente', 'GET', own, { state: 'submitted' });
    step('Listar pedidos do cliente', 'GET', `${root}?page=1&pageSize=1&q={{runId}}&status=submitted&sort=oldest`, { checks: pageChecks });
    step('Listar pedidos administrativos', 'GET', `${adminRoot}?page=1&pageSize=1&q={{runId}}&status=submitted&sort=newest`, { token: 'adminToken', checks: pageChecks });
    step('Ler pedido administrativo', 'GET', managed, { token: 'adminToken', state: 'submitted' });
    step('Cliente nao administra pedidos', 'GET', adminRoot, { status: 403 });
    step('Admin nao cria pedidos como cliente', 'POST', root, { token: 'adminToken', status: 403, body: createBody });
    step('Outro cliente nao le pedido', 'GET', own, { token: 'aliasCustomerToken', status: 404 });
    step('Outro cliente nao envia mensagem', 'POST', `${own}/messages`, { token: 'aliasCustomerToken', status: 404, body: { version: 1, message: 'Nao autorizado.' } });
    step('Outro cliente nao cancela pedido', 'POST', `${own}/actions`, { token: 'aliasCustomerToken', status: 404, body: { version: 1, action: 'cancel', message: 'Nao autorizado.' } });
    step('Mensagem cliente preserva estado', 'POST', `${own}/messages`, {
        state: 'submitted', body: { version: 1, message: 'Segue a referencia externa.' }
    });
    step('Mensagem admin preserva estado', 'POST', `${managed}/messages`, {
        token: 'adminToken', state: 'submitted', body: { version: 1, message: 'Pedido recebido pela equipa.' }
    });
    step('Mensagem obsoleta falha', 'POST', `${own}/messages`, {
        status: 409, stale: true, body: { version: 1, message: 'Nao deve ser persistida.' }
    });
    transition('Iniciar analise', 'under_review');
    transition('Solicitar informacoes', 'information_required');
    step('Resposta cliente retorna a analise', 'POST', `${own}/messages`, {
        state: 'under_review', body: { version: 1, message: 'A peca sera decorativa.' }
    });
    publish('Publicar primeira cotacao', 1250);
    action('Solicitar alteracoes da cotacao', 'request_changes', 'quote_changes_requested', 'Prefiro outra dimensao.');
    publish('Publicar segunda cotacao', 1500);
    action('Aprovacao obsoleta falha', 'approve_quote', undefined, '', { status: 409, stale: true });
    action('Aprovar cotacao atual sem mensagem', 'approve_quote', 'awaiting_payment', '');
    transition('Iniciar verificacao manual', 'payment_verification');
    transition('Reabrir pagamento nao confirmado', 'awaiting_payment');
    transition('Confirmar pagamento manualmente com motivo', 'payment_confirmed');
    action('Cliente nao cancela apos confirmacao', 'cancel', undefined, 'Nao permitido.', { status: 409 });
    transition('Iniciar producao apos pagamento', 'in_production');
    transition('Pausar producao com motivo', 'production_paused');
    transition('Retomar producao', 'in_production');
    transition('Expedicao rejeita tracking invalido', 'shipped', {
        status: 422, state: undefined, body: { trackingUrl: 'invalid-url' }
    });
    transition('Expedir com tracking', 'shipped', {
        body: { trackingUrl: 'https://example.com/tracking/postman', estimatedShipping: '2030-01-01' }
    });
    transition('Registar entrega', 'delivered');
    step('Ler historico final persistido', 'GET', own, {
        state: 'delivered', checks: `
pm.test("Historico e cotacoes preservados", function () {
    pm.expect(data.quotes).to.have.lengthOf(2);
    pm.expect(data.quotes[0]).not.to.have.property("approvedAt");
    pm.expect(data.quotes[1].approvedAt).to.be.a("string");
    pm.expect(data.history.length).to.be.above(15);
    pm.expect(data.allowedActions).to.eql([]);
    pm.expect(data.allowedTransitions).to.eql([]);
    pm.expect(data.trackingUrl).to.eql("https://example.com/tracking/postman");
});`
    });
    create('Criar pedido para expedicao sem tracking');
    transition('Iniciar analise sem tracking', 'under_review');
    publish('Publicar cotacao sem tracking', 1000);
    action('Aprovar cotacao sem tracking', 'approve_quote', 'awaiting_payment', '');
    transition('Confirmar pagamento sem tracking', 'payment_confirmed');
    transition('Iniciar producao sem tracking', 'in_production');
    transition('Expedir sem tracking', 'shipped');
    transition('Registar entrega sem tracking', 'delivered');
    create('Criar pedido para cancelamento cliente');
    action('Cancelar pedido antes de pagamento', 'cancel', 'cancelled', 'Nao pretendo continuar.');
    create('Criar pedido para rejeicao admin');
    transition('Rejeitar pedido pre-pagamento', 'rejected');
    return items;
}

function buildCollection() {
    const healthChecks = `
pm.test("API e MongoDB saudaveis", function () {
    pm.expect(data.status).to.eql("ok");
    pm.expect(data.database).to.eql("connected");
});`;
    const optional = [
        ['Confirmar email com token real', '/auth/verify-email', 'verificationToken', { token: '{{verificationToken}}' }],
        ['Confirmar novo email com token real', '/users/me/email-change/confirm', 'emailChangeToken', { token: '{{emailChangeToken}}' }, 'emailFlowAccessToken'],
        ['Redefinir senha com token real', '/auth/reset-password', 'passwordResetToken', { token: '{{passwordResetToken}}', password: '{{newPassword}}' }]
    ].map(([name, route, variable, body, token]) => request(name, 'POST', `/api/v1${route}`, {
        writes: true, body, token, checks: messageChecks,
        before: `
if (!pm.variables.get("${variable}")) {
    console.warn("IGNORADO: informe ${variable} com um token real recebido por email (ou log console da API).");
    pm.execution.skipRequest();
}
${token ? `if (pm.variables.get("${variable}") && !pm.variables.get("${token}")) { pm.execution.skipRequest(); throw new Error("Informe ${token} da conta dona do token de alteracao."); }` : ''}
${variable === 'passwordResetToken' ? 'if (pm.variables.get("passwordResetToken") && String(pm.variables.get("newPassword") || "").length < 8) { pm.execution.skipRequest(); throw new Error("Informe newPassword com pelo menos 8 caracteres."); }' : ''}`,
        description: 'OPCIONAL. Token de uso unico, pertencente a uma conta de teste. Execute individualmente; a suite automatica testa a rejeicao de tokens invalidos. Nao reutilize tokens.'
    }));
    return {
        info: {
            name: 'Printoy 3D - Backend completo',
            description: 'Testes ordenados dos endpoints versionados e aliases legados, incluindo pedidos personalizados persistidos, cotacoes, mensagens e transicoes manuais. allowWrites=false executa apenas leituras publicas e erros 401/404. Para a suite completa, use uma base isolada, allowWrites=true e credenciais admin. Cria quatro clientes, tres pedidos (preservados para auditoria) e cria/elimina quatro produtos. Pode enviar emails de autenticacao; pedidos nao enviam notificacoes, cobram pagamentos nem emitem reembolsos. Confirmacoes com tokens reais sao opcionais. Leia postman/README.md. Gerado por generate-collection.cjs.',
            schema: 'https://schema.getpostman.com/json/collection/v2.1.0/collection.json'
        },
        variable: [
            ['baseUrl', 'https://api.printoy3d.com'],
            ['allowWrites', 'false'],
            ['testEmailDomain', 'example.com'],
            ['adminEmail', ''], ['adminPassword', ''],
            ['verificationToken', ''], ['emailChangeToken', ''], ['emailFlowAccessToken', ''],
            ['passwordResetToken', ''], ['newPassword', '']
        ].map(([key, value]) => ({ key, value, type: 'string' })),
        event: [script('prerequest', `
if (pm.info.requestName === "Health e inicializacao da execucao" || !pm.variables.get("runId")) {
    pm.variables.set("runId", pm.variables.replaceIn("{{$guid}}"));
    pm.variables.set("customerPassword", "Pm!" + pm.variables.replaceIn("{{$guid}}"));
}
const baseUrl = pm.variables.get("baseUrl");
if (typeof baseUrl !== "string" || !/^https?:\\/\\/[^\\s/?#]+(?::\\d+)?$/.test(baseUrl)) {
    pm.execution.skipRequest();
    throw new Error("baseUrl deve ser uma origem http(s), sem barra final nem /api/v1.");
}
if (!["true", "false"].includes(pm.variables.get("allowWrites"))) {
    pm.execution.skipRequest();
    throw new Error("allowWrites deve ser a string true ou false.");
}
`)],
        item: [
            {
                name: '00 - Inicializacao e health',
                item: [
                    request('Health e inicializacao da execucao', 'GET', '/health', {
                        before: '',
                        checks: healthChecks
                    }),
                    request('Health versionado', 'GET', '/api/v1/health', { checks: healthChecks })
                ]
            },
            suite('01 - API versionada /api/v1', '/api/v1', '/api/v1', 'v1'),
            {
                name: '02 - Dados da interface',
                item: [
                    request('Navegacao', 'GET', '/api/common/navigation', {
                        checks: 'pm.test("Variantes de navegacao", function () { ["default", "compact", "futuristic", "horizontal"].forEach(key => pm.expect(data[key]).to.be.an("array")); });'
                    }),
                    ...['messages', 'notifications', 'shortcuts'].map(name => request(name, 'GET', `/api/common/${name}`, {
                        checks: 'pm.test("Lista da interface", function () { pm.expect(data).to.be.an("array"); });'
                    }))
                ]
            },
            suite('03 - Aliases /api e /api/clara-rosa', '/api', '/api/clara-rosa', 'legacy'),
            { name: '04 - OPCIONAL - Tokens reais recebidos por email', item: optional }
        ]
    };
}

function environment(name, baseUrl) {
    return {
        name,
        values: [
            { key: 'baseUrl', value: baseUrl, enabled: true },
            { key: 'allowWrites', value: 'false', enabled: true },
            { key: 'adminEmail', value: '', enabled: true },
            { key: 'adminPassword', value: '', enabled: true, type: 'secret' },
            { key: 'testEmailDomain', value: 'example.com', enabled: true },
            ...['verificationToken', 'emailChangeToken', 'emailFlowAccessToken', 'passwordResetToken', 'newPassword']
                .map(key => ({ key, value: '', enabled: true, type: 'secret' }))
        ],
        _postman_variable_scope: 'environment'
    };
}

if (require.main === module) {
    const files = {
        'Printoy3D.postman_collection.json': buildCollection(),
        'Printoy3D.production.postman_environment.json': environment('Printoy 3D - Remoto (somente leitura)', 'https://api.printoy3d.com'),
        'Printoy3D.local.postman_environment.json': environment('Printoy 3D - Local', 'http://localhost:8000')
    };
    for (const [name, data] of Object.entries(files)) {
        fs.writeFileSync(path.join(__dirname, name), JSON.stringify(data, null, 2) + '\n');
    }
}

module.exports = { buildCollection, environment };
