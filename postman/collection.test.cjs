const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const { buildCollection, environment } = require('./generate-collection.cjs');

const collection = buildCollection();
const flatten = node => node.item ? node.item.flatMap(flatten) : [node];
const requests = flatten(collection);
const source = (node, listen) => (node.event || [])
    .filter(event => event.listen === listen)
    .map(event => event.script.exec.join('\n')).join('\n');

function preRequest(item, overrides = {}) {
    const values = new Map(collection.variable.map(({ key, value }) => [key, value]));
    Object.entries(overrides).forEach(([key, value]) => values.set(key, value));
    let skipped = false;
    let body = item.request.body?.raw;
    const context = {
        console: { warn() {} },
        pm: {
            info: { requestName: item.name },
            variables: {
                get: key => values.get(key),
                set: (key, value) => values.set(key, value),
                replaceIn: () => '00000000-0000-4000-8000-000000000001'
            },
            request: { body: { get raw() { return body; }, update(value) { body = value; } } },
            execution: { skipRequest() { skipped = true; } }
        }
    };
    vm.runInNewContext(source(collection, 'prerequest'), context);
    vm.runInNewContext(source(item, 'prerequest'), context);
    return { values, skipped, body };
}

test('generated collection and environments match their sources', () => {
    assert.deepEqual(JSON.parse(fs.readFileSync(path.join(__dirname, 'Printoy3D.postman_collection.json'))), collection);
    for (const [file, name, url] of [
        ['production', 'Printoy 3D - Remoto (somente leitura)', 'https://api.printoy3d.com'],
        ['local', 'Printoy 3D - Local', 'http://localhost:8000']
    ]) {
        assert.deepEqual(
            JSON.parse(fs.readFileSync(path.join(__dirname, `Printoy3D.${file}.postman_environment.json`))),
            environment(name, url)
        );
    }
});

test('all embedded scripts are valid JavaScript; every request has a status assertion', () => {
    function visit(node) {
        for (const event of node.event || []) new vm.Script(event.script.exec.join('\n'));
        for (const child of node.item || []) visit(child);
    }
    visit(collection);
    for (const item of requests) {
        assert.match(item.request.url, /^\{\{baseUrl\}\}\//);
        assert.match(source(item, 'test'), /pm\.response\.to\.have\.status\(\d+\)/);
        if (item.request.body) JSON.parse(item.request.body.raw);
    }
});

test('safe default skips every mutation and every authenticated flow', () => {
    const safe = [];
    for (const item of requests) {
        const result = preRequest(item);
        if (!result.skipped) {
            safe.push(item);
            assert.equal(item.request.method, 'GET', item.name);
            assert.equal(item.request.auth.type, 'noauth', item.name);
            assert.doesNotMatch(item.request.url, /\{\{(?:productId|legacyProductId|productSlug|printRequestId)\}\}/);
        }
    }
    assert.equal(safe.length, 18);
});

test('writes require explicit enablement and administrator credentials', () => {
    const signup = requests.find(item => item.name === 'Cadastrar cliente');
    assert.equal(preRequest(signup).skipped, true);
    assert.throws(() => preRequest(signup, { allowWrites: 'true' }), /adminEmail/);
    assert.equal(preRequest(signup, {
        allowWrites: 'true', adminEmail: 'test@example.com', adminPassword: 'test-only'
    }).skipped, false);
    assert.throws(() => preRequest(signup, { allowWrites: 'TRUE' }), /allowWrites/);
});

test('base URL is configurable and rejects path prefixes or trailing slashes', () => {
    const health = requests[0];
    for (const baseUrl of ['https://api.printoy3d.com', 'http://localhost:8000']) {
        assert.equal(preRequest(health, { baseUrl }).values.get('baseUrl'), baseUrl);
    }
    for (const baseUrl of ['', 'https://api.printoy3d.com/', 'http://localhost:8000/api/v1']) {
        assert.throws(() => preRequest(health, { baseUrl }), /baseUrl/);
    }
});

test('email success flows are optional; deletion without a created ID is blocked', () => {
    const config = { allowWrites: 'true', adminEmail: 'test@example.com', adminPassword: 'test-only' };
    for (const item of collection.item.at(-1).item) {
        assert.equal(preRequest(item, config).skipped, true);
    }
    for (const item of requests.filter(item => item.request.method === 'DELETE')) {
        assert.throws(() => preRequest(item, config), /eliminacao bloqueada/);
    }
});

test('initialization refreshes run IDs/passwords and clears stale resource IDs', () => {
    const health = requests[0];
    const initialized = preRequest(health, { runId: 'previous-run', customerPassword: 'old-password' }).values;
    assert.notEqual(initialized.get('runId'), 'previous-run');
    assert.notEqual(initialized.get('customerPassword'), 'old-password');
    for (const folder of [collection.item[1], collection.item[3]]) {
        const initializedSuite = preRequest(folder.item[0], {
            productId: 'existing-product', legacyProductId: 'existing-legacy-product'
        }).values;
        assert.equal(initializedSuite.get('productId'), '');
        assert.equal(initializedSuite.get('legacyProductId'), '');
    }
});

test('test scripts do not collide with the legacy Postman data global', () => {
    for (const item of requests) {
        new vm.Script(`const data = {};\n${source(item, 'test')}`);
    }
});

test('every mounted backend operation is represented in the collection', () => {
    const apiDir = path.join(__dirname, '..');
    const main = fs.readFileSync(path.join(apiDir, 'main.py'), 'utf8');
    const operations = [];
    const mounts = /app\.include_router\((\w+)\.(\w*router)(?:, prefix=(?:"([^"]+)"|(settings\.API_V1_STR)))?\)/g;
    for (const [, module, routerName, literalPrefix, versioned] of main.matchAll(mounts)) {
        const router = fs.readFileSync(path.join(apiDir, 'app', 'routers', `${module}.py`), 'utf8');
        const routerPrefix = router.match(new RegExp(`${routerName} = APIRouter\\(prefix="([^"]+)"`))?.[1] || '';
        const prefix = literalPrefix || (versioned ? '/api/v1' : '');
        for (const [, method, route] of router.matchAll(new RegExp(`@${routerName}\\.(get|post|patch|delete)\\(\\s*"([^"]*)"`, 'g'))) {
            operations.push({ method: method.toUpperCase(), route: prefix + routerPrefix + route });
        }
    }
    assert.equal(operations.length, 78, 'Review coverage/docs when the API adds or removes operations');
    for (const operation of operations) {
        const pattern = new RegExp('^' + operation.route.replace(/\{[^}]+\}/g, '[^/]+') + '$');
        assert.ok(requests.some(item =>
            item.request.method === operation.method &&
            pattern.test(item.request.url.replace('{{baseUrl}}', '').split('?')[0])
        ), `${operation.method} ${operation.route} is missing`);
    }
});

test('request workflow shares run credentials and guards captured IDs and numeric versions', () => {
    const workflow = requests.filter(item => item.request.url.includes('/print-requests'));
    const config = {
        allowWrites: 'true', adminEmail: 'test@example.com', adminPassword: 'test-only',
        printRequestId: 'created-in-this-run', printRequestVersion: 9, printQuoteVersion: 2,
        createdPrintRequestIds: JSON.stringify(['created-in-this-run'])
    };
    assert.equal(workflow.filter(item => item.request.method === 'GET' && item.request.auth.type === 'noauth').length, 2);
    for (const item of workflow.filter(item => item.request.auth.type === 'bearer')) {
        assert.equal(preRequest(item).skipped, true, item.name);
        const result = preRequest(item, config);
        assert.equal(result.skipped, false, item.name);
        const token = item.request.auth.bearer[0].value;
        assert.ok(['{{customerToken}}', '{{adminToken}}', '{{aliasCustomerToken}}'].includes(token));
        if (item.request.body) {
            const body = JSON.parse(result.body);
            if ('version' in body) assert.equal(body.version, item.name.includes('obsoleta') ? 8 : 9);
            if ('quoteVersion' in body) assert.equal(body.quoteVersion, 2);
            if ('validUntil' in body) assert.ok(new Date(body.validUntil).getTime() > Date.now());
        }
        if (item.request.url.includes('{{printRequestId}}')) {
            assert.throws(() => preRequest(item, { ...config, printRequestId: 'unrelated-existing-id' }), /operacao bloqueada/);
        }
    }
    const approve = workflow.find(item => item.name === 'Aprovar cotacao atual sem mensagem');
    assert.equal(JSON.parse(preRequest(approve, config).body).message, '');
});

test('request flow runs before logout and covers all workflow categories', () => {
    const versioned = flatten(collection.item[1]);
    const index = name => versioned.findIndex(item => item.name === name);
    for (const name of [
        'Criar pedido personalizado', 'Mensagem cliente preserva estado', 'Mensagem admin preserva estado',
        'Publicar primeira cotacao', 'Solicitar alteracoes da cotacao', 'Publicar segunda cotacao',
        'Aprovar cotacao atual sem mensagem', 'Confirmar pagamento manualmente com motivo',
        'Iniciar producao apos pagamento', 'Expedir com tracking', 'Registar entrega',
        'Cancelar pedido antes de pagamento', 'Rejeitar pedido pre-pagamento'
    ]) {
        assert.ok(index(name) > index('Login administrador'), name);
        assert.ok(index(name) < index('Logout revoga refresh token'), name);
    }
    assert.ok(index('Publicar segunda cotacao') > index('Solicitar alteracoes da cotacao'));
});

test('both environments remain read-only without credentials or captured resource/session data', () => {
    for (const baseUrl of ['http://localhost:8000', 'https://api.printoy3d.com']) {
        const generated = environment('test', baseUrl);
        const values = Object.fromEntries(generated.values.map(({ key, value }) => [key, value]));
        assert.equal(values.allowWrites, 'false');
        assert.equal(values.adminEmail, '');
        assert.equal(values.adminPassword, '');
        assert.equal(generated.values.find(value => value.key === 'adminPassword').type, 'secret');
        for (const key of [
            'customerToken', 'adminToken', 'aliasCustomerToken', 'printRequestId',
            'printRequestVersion', 'printQuoteVersion', 'createdPrintRequestIds'
        ]) assert.ok(!(key in values), key);
    }
});

test('generated account emails stay within the 64-character local-part limit', () => {
    for (const folder of [collection.item[1], collection.item[3]]) {
        const values = preRequest(folder.item[0]).values;
        for (const item of flatten(folder).filter(item => item.request.body)) {
            const body = JSON.parse(item.request.body.raw);
            for (const template of [body.email, body.newEmail].filter(Boolean)) {
                const email = template.replace(/\{\{(\w+)\}\}/g, (_, key) => values.get(key));
                assert.ok(email.split('@')[0].length <= 64, `${item.name}: ${email}`);
            }
        }
    }
});
