import { createServer as createHttpServer, type Server } from 'node:http';
import { afterEach, expect, test } from 'vitest';
import { createServer as createViteServer, type ViteDevServer } from 'vite';
import { createApiProxy } from '../vite.config';

const opened: (Server | ViteDevServer)[] = [];
afterEach(async () => {
  for (const server of opened.splice(0).reverse()) {
    if ('httpServer' in server) await server.close();
    else await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  }
});

async function backend(name: string) {
  const server = createHttpServer(async (request, response) => {
    let body = '';
    for await (const chunk of request) body += chunk;
    response.setHeader('Content-Type', 'application/json');
    response.end(JSON.stringify({ name, url: request.url, method: request.method, body,
      cookie: request.headers.cookie, idempotency: request.headers['idempotency-key'] }));
  });
  opened.push(server);
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  if (!address || typeof address === 'string') throw new Error('missing HTTP port');
  return `http://127.0.0.1:${address.port}`;
}

test('forwards ads and common APIs to separate hosts without losing request context', async () => {
  const recommendation = await backend('recommendation');
  const ads = await backend('ads');
  const vite = await createViteServer({ configFile: false, logLevel: 'silent',
    server: { host: '127.0.0.1', port: 0, proxy: createApiProxy({
      VITE_RECOMMENDATION_API_TARGET: recommendation, VITE_ADS_API_TARGET: ads,
    }) },
  });
  opened.push(vite);
  await vite.listen();
  const address = vite.httpServer?.address();
  if (!address || typeof address === 'string') throw new Error('missing Vite port');
  for (const [path, name] of [
    ['/api/ads?placement=top', 'ads'], ['/api/ad-events', 'ads'],
    ['/api/ad-deliveries/example/image', 'ads'], ['/api/admin/ads/summary', 'ads'],
    ['/api/admin/ad-assets/example', 'ads'], ['/api/recommendation-jobs', 'recommendation'],
    ['/api/weather?region_id=example', 'recommendation'], ['/api/auth/me', 'recommendation'],
    ['/api/admin/music/reviews', 'recommendation'], ['/api/ads-options', 'recommendation'],
  ]) {
    const response = await fetch(`http://127.0.0.1:${address.port}${path}`, { method: 'POST',
      headers: { 'Content-Type': 'application/json', Cookie: 'session=example', 'Idempotency-Key': 'test-key' },
      body: '{"test":true}',
    });
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ name, url: path, method: 'POST', body: '{"test":true}',
      cookie: 'session=example', idempotency: 'test-key' });
  }
}, 20000);
