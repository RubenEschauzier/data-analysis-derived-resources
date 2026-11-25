// Scan vs pure bind join for q16's vendor and review blocks (chain-first), against the local Virtuoso
// endpoints directly. Measures wall time, client CPU, requests, rows and bytes.
// usage: node bench.mjs <proxy-run.json> <productType> <concurrency,...>
import fs from 'node:fs';
import http from 'node:http';
import http from 'node:http';

const [ mapPath, productType = '155', concArg = '16,64,256' ] = process.argv.slice(2);
const map = JSON.parse(fs.readFileSync(mapPath, 'utf8'));
const PREFIXES = `PREFIX bsbm: <http://www4.wiwiss.fu-berlin.de/bizer/bsbm/v01/vocabulary/>
PREFIX fs: <http://fedshop.example.org/vocab#>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
`;
const BLOCKS = {
  vendor: { group: 'vendor', body: p => `?listing fs:listingOf ${p} . ?offer bsbm:product ?listing . ?offer bsbm:price ?price . ?offer bsbm:vendor ?vendor .` },
  review: { group: 'ratingsite', body: p => `?page fs:listingOf ${p} . ?review bsbm:reviewFor ?page . ?review bsbm:rating1 ?rating1 . ?review dc:publisher ?site .` },
};
const endpointsOf = group => map.services
  .filter(s => s.publisher.replace(/\d+$/u, '') === group)
  .map(s => `http://${s.host}:${s.target}/${s.publisher}/sparql`);

// Virtuoso defines each publisher's endpoint on its own port, matched on the Host header (as the proxy sets it)
function post(url, query) {
  const target = new URL(url);
  const body = new URLSearchParams({ query }).toString();
  return new Promise((resolve, reject) => {
    const req = http.request({
      host: target.hostname, port: target.port, path: target.pathname, method: 'POST', agent: false,
      headers: {
        host: `localhost:${target.port}`, 'content-type': 'application/x-www-form-urlencoded',
        accept: 'application/sparql-results+json', 'content-length': Buffer.byteLength(body),
      },
    }, (res) => {
      const chunks = [];
      res.on('data', chunk => chunks.push(chunk));
      res.on('end', () => resolve({ status: res.statusCode, text: Buffer.concat(chunks).toString('utf8') }));
      res.on('error', reject);
    });
    req.on('error', reject);
    req.end(body);
  });
}

async function select(url, query) {
  const started = performance.now();
  const { status, text } = await post(url, query);
  if (status !== 200) {
    throw new Error(`${status} ${url}: ${text.slice(0, 200)}`);
  }
  const rows = JSON.parse(text).results.bindings.length;
  return { rows, bytes: text.length, ms: performance.now() - started };
}

async function pool(tasks, concurrency) {
  const results = [];
  let next = 0;
  await Promise.all(Array.from({ length: Math.min(concurrency, tasks.length) }, async() => {
    while (next < tasks.length) {
      const i = next++;
      results[i] = await tasks[i]();
    }
  }));
  return results;
}

async function measure(label, tasks, concurrency) {
  const cpu0 = process.cpuUsage();
  const t0 = performance.now();
  const results = await pool(tasks, concurrency);
  const wall = performance.now() - t0;
  const cpu = process.cpuUsage(cpu0);
  const lat = results.map(r => r.ms).sort((a, b) => a - b);
  const sum = key => results.reduce((acc, r) => acc + r[key], 0);
  console.log(JSON.stringify({
    label, concurrency, requests: results.length, rows: sum('rows'), kb: Math.round(sum('bytes') / 1024),
    wall_ms: Math.round(wall), client_cpu_ms: Math.round((cpu.user + cpu.system) / 1000),
    lat_p50: Math.round(lat[Math.floor(lat.length / 2)]), lat_p95: Math.round(lat[Math.floor(lat.length * 0.95)]),
  }));
}

const products = (await (await fetch('http://fedshop-virtuoso:8890/sparql', {
  method: 'POST',
  headers: { 'content-type': 'application/x-www-form-urlencoded', accept: 'application/sparql-results+json' },
  body: new URLSearchParams({ query: `${PREFIXES}SELECT DISTINCT ?p WHERE { ?p rdf:type <http://fedshop-proxy:3000/taxonomy/ProductType${productType}#it> }` }),
})).json()).results.bindings.map(b => `<${b.p.value}>`);
console.log(JSON.stringify({ productType, products: products.length }));

for (const [ name, block ] of Object.entries(BLOCKS)) {
  const endpoints = endpointsOf(block.group);
  const scan = () => endpoints.map(url => () => select(url, `${PREFIXES}SELECT * WHERE { ${block.body('?product')} }`));
  const bind = () => endpoints.flatMap(url => products.map(p => () => select(url, `${PREFIXES}SELECT * WHERE { ${block.body(p)} }`)));
  // Warm Virtuoso's caches for both forms before measuring
  await measure(`${name}:scan:warmup`, scan(), 64);
  await measure(`${name}:bind:warmup`, bind(), 64);
  await measure(`${name}:scan`, scan(), 64);
  // Reference: all values in one request per endpoint (VALUES)
  const values = () => endpoints.map(url => () => select(url, `${PREFIXES}SELECT * WHERE { VALUES ?product { ${products.join(' ')} } ${block.body('?product')} }`));
  await measure(`${name}:values:warmup`, values(), 64);
  await measure(`${name}:values`, values(), 64);
  for (const c of concArg.split(',').map(Number)) {
    await measure(`${name}:bind`, bind(), c);
  }
}
