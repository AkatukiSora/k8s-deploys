addEventListener('fetch', event => {
  event.respondWith(
    new Response(
      '<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>503 Service Unavailable</title><style>body{display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;font-family:sans-serif;background:#f5f5f5;color:#333}.container{text-align:center;padding:2rem}h1{font-size:2rem;margin-bottom:0.5rem}p{font-size:1.1rem;color:#666}</style></head><body><div class="container"><h1>503 Service Unavailable</h1><p>現在メンテナンス中です。しばらく経ってから再度お試しください。</p></div></body></html>',
      {
        status: 503,
        headers: {
          'Content-Type': 'text/html; charset=utf-8',
          'Retry-After': '3600'
        }
      }
    )
  );
});