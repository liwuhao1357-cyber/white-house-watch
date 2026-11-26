const SOURCE = 'https://raw.githubusercontent.com/liwuhao1357-cyber/white-house-watch/main/feed.json';
export async function onRequest({request}) {
  const headers = {'Content-Type':'application/json; charset=utf-8','X-Content-Type-Options':'nosniff','Cache-Control':'public, max-age=60'};
  if (request.method !== 'GET' && request.method !== 'HEAD') return new Response('{"error":"method"}',{status:405,headers});
  try {
    const upstream = await fetch(SOURCE, {headers:{Accept:'application/json'}});
    if (!upstream.ok) throw new Error('upstream unavailable');
    const data = await upstream.json();
    if (!Array.isArray(data.items) || !data.updated) throw new Error('invalid feed');
    return new Response(request.method==='HEAD'?null:JSON.stringify(data),{headers});
  } catch (_) {
    return new Response('{"error":"source temporarily unavailable"}',{status:503,headers:{...headers,'Cache-Control':'no-store'}});
  }
}
