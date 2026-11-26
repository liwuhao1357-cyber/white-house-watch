#!/usr/bin/env python3
import os, json, time, threading, sqlite3, re, hashlib, logging, tempfile
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse, parse_qs, urlencode
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parent
DB=Path(os.getenv('WATCH_DB',str(ROOT/'watch.sqlite3')))
SOURCES={'trump':('https://www.trumpstruth.org/feed',60),'trump_cnn':('https://ix.cnn.io/data/truth-social/truth_archive.json',300),'whitehouse':('https://www.whitehouse.gov/releases/feed/',120),'actions':('https://www.whitehouse.gov/presidential-actions/feed/',120)}
TRANSLATE=os.getenv('WATCH_TRANSLATE','0')=='1'
LOCK=threading.Lock()
class Plain(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True); self.parts=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'): self.skip+=1
        elif tag in ('p','br','div','li'): self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
        elif tag in ('p','div','li'): self.parts.append('\n')
    def handle_data(self,data):
        if not self.skip: self.parts.append(data)
def plain(s):
    p=Plain(); p.feed(s or ''); return re.sub(r'\n\s*\n+', '\n\n',''.join(p.parts)).strip()
def now(): return datetime.now(timezone.utc).isoformat()
def timestamp(s):
    try: d=parsedate_to_datetime(s)
    except (TypeError, ValueError): d=datetime.fromisoformat(s.replace('Z','+00:00'))
    if d.tzinfo is None: raise ValueError('Missing timezone')
    return d.astimezone(timezone.utc).isoformat(timespec="milliseconds")
def safeurl(s):
    p=urlparse(s or ''); return s if p.scheme=='https' and p.netloc else ''
def fetch(url):
    with urlopen(Request(url,headers={'User-Agent':'WhiteHouseWatch/0.1 (RSS reader)','Accept':'application/rss+xml, application/xml, application/json, */*'}),timeout=15) as r:
        b=r.read(96_000_001)
        if len(b)>96_000_000: raise ValueError('Response too large')
        return b
def item_key(source,url):
    p=urlparse(url)
    path=p.path.rstrip('/')
    host=p.netloc.lower().removeprefix('www.')
    return hashlib.sha256((source+'|'+host+path).encode()).hexdigest()
def parse_cnn(raw):
    data=json.loads(raw)
    if not isinstance(data,list): raise ValueError('Unexpected CNN archive format')
    items=[]
    for e in data:
        if not isinstance(e,dict): continue
        try: published=timestamp(e.get('created_at',''))
        except (TypeError,ValueError,AttributeError): continue
        url=safeurl(e.get('url',''))
        if not url or urlparse(url).netloc.lower() not in ('truthsocial.com','www.truthsocial.com'): continue
        content=plain(e.get('content') or '')[:500]
        if not content and not e.get('media'): continue
        title='' if content else '（含媒体附件，请查看来源）'
        items.append((item_key('trump',url),'trump','trump',published,title,content,url))
    if not items: raise ValueError('CNN archive contains no valid posts')
    return sorted(items,key=lambda x:x[3],reverse=True)[:1000]
def parse_rss(raw,source):
    root=ET.fromstring(raw)
    if root.tag!='rss' or root.find('channel') is None: raise ValueError('Not RSS')
    items=[]
    for e in root.findall('./channel/item'):
        def get(k): return e.findtext(k) or ''
        try: published=timestamp(get('pubDate'))
        except (TypeError,ValueError,AttributeError): continue
        url=safeurl(get('link'))
        if not url: continue
        title=plain(get('title')); content=plain(get('{http://purl.org/rss/1.0/modules/content/}encoded') or get('description'))[:500]
        if not title and not content: continue
        group='trump' if source=='trump' else 'whitehouse'
        key=item_key(group,url)
        cats=' '.join(x.text or '' for x in e.findall('category'))
        kind='order' if group=='whitehouse' and (source=='actions' or '/presidential-actions/' in url or 'presidential actions' in cats.lower() or 'executive order' in title.lower()) else group
        items.append((key,group,kind,published,title,content,url))
    if not items: raise ValueError('Feed contains no valid dated items')
    return items
def conn():
    c=sqlite3.connect(DB,timeout=15); c.row_factory=sqlite3.Row; return c
def init():
    with conn() as c:
        c.executescript('''PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY,source TEXT,kind TEXT,published TEXT,title TEXT,content TEXT,url TEXT,zh TEXT DEFAULT ''); CREATE INDEX IF NOT EXISTS item_time ON items(published DESC); CREATE TABLE IF NOT EXISTS status(source TEXT PRIMARY KEY,checked TEXT,success TEXT,error TEXT);''')
def save(source,items):
    with conn() as c:
        for item in items:
            key,group,kind,published,title,content,url=item
            # RSS mirror and original post can use different URLs. Match only identical text in the same minute.
            if group=='trump' and content:
                duplicate=c.execute("SELECT id FROM items WHERE source='trump' AND substr(published,1,16)=substr(?,1,16) AND content=? LIMIT 1",(published,content)).fetchone()
                if duplicate: continue
            c.execute('INSERT OR IGNORE INTO items(id,source,kind,published,title,content,url) VALUES(?,?,?,?,?,?,?)',item)
            if kind=='order': c.execute("UPDATE items SET kind='order' WHERE id=?",(key,))
        c.execute("INSERT INTO status VALUES(?,?,?, '') ON CONFLICT(source) DO UPDATE SET checked=excluded.checked,success=excluded.success,error=''",(source,now(),now()))
def fail(source,err):
    with conn() as c: c.execute("INSERT INTO status VALUES(?,?,'',?) ON CONFLICT(source) DO UPDATE SET checked=excluded.checked,error=excluded.error",(source,now(),str(err)[:220]))
def translate_batch(usage):
    if not TRANSLATE: return usage
    today=datetime.now(timezone.utc).date().isoformat()
    if usage.get('date')!=today: usage={'date':today,'chars':0}
    with LOCK:
        with conn() as c: rows=c.execute("SELECT id,title,content FROM items WHERE zh='' ORDER BY published DESC LIMIT 20").fetchall()
        for r in rows:
            try:
                original=r['title'] or r['content']; snippet=original[:220]
                if not snippet or usage['chars']+len(snippet)>4000: break
                u='https://api.mymemory.translated.net/get?'+urlencode({'q':snippet,'langpair':'en|zh-CN'})
                j=json.loads(fetch(u)); zh=j.get('responseData',{}).get('translatedText','')
                if j.get('quotaFinished') or str(j.get('responseStatus'))!='200' or not zh: break
                with conn() as c: c.execute('UPDATE items SET zh=? WHERE id=?',(zh,r['id']))
                usage['chars']+=len(snippet)
            except Exception: logging.exception('Optional translation failed'); break
    return usage

# One short execution per scheduled job; no always-on server.
def run_once(previous):
    errors.clear()
    init()
    with conn() as c:
        for x in previous.get('items', []):
            c.execute('INSERT OR IGNORE INTO items VALUES(?,?,?,?,?,?,?,?)', tuple(x.get(k,'') for k in ('id','source','kind','published','title','content','url','zh')))
        for key,r in previous.get('status',{}).items():
            c.execute('INSERT OR IGNORE INTO status VALUES(?,?,?,?)',(key,r.get('checked',''),r.get('success',''),r.get('error','')))
    # CNN is a fallback only when RSS fails; avoid unnecessary large downloads.
    for source in ('trump','whitehouse','actions'):
        if source=='trump_cnn' and not errors.get('trump'):
            continue
        try:
            raw=fetch(SOURCES[source][0]); save(source,parse_cnn(raw) if source=='trump_cnn' else parse_rss(raw,source))
        except Exception as exc:
            errors[source]=True; fail(source,exc)
    usage=translate_batch(previous.get('translation_usage',{}))
    with conn() as c:
        items=[dict(r) for r in c.execute('SELECT * FROM items ORDER BY published DESC LIMIT 500')]
        status={r['source']:dict(r) for r in c.execute('SELECT * FROM status')}
    # Keep bounded excerpts and canonical source links; no fabricated content.
    for x in items:
        x['title']=x['title'][:280]
        x['content']=x['content'][:280]
    return {'items':items,'status':status,'translate':TRANSLATE,'translation_usage':usage,'updated':now()}
errors={}
if __name__=='__main__':
    archive=ROOT/'feed.json'
    previous=json.loads(archive.read_text()) if archive.exists() else {'items':[], 'status':{}}
    if not isinstance(previous.get('items'),list): raise ValueError('Invalid archive; refusing overwrite')
    with tempfile.TemporaryDirectory() as tmp:
        DB=Path(tmp)/'watch.sqlite3'
        result=run_once(previous)
    if all(errors.get(s) for s in ('trump','whitehouse','actions')):
        raise RuntimeError('All sources failed; preserving existing archive')
    # Bound both record count and encoded size. Only short excerpts are stored.
    raw=json.dumps(result,ensure_ascii=False,separators=(',',':')).encode()
    while len(raw)>850000 and result['items']:
        result['items'].pop()
        raw=json.dumps(result,ensure_ascii=False,separators=(',',':')).encode()
    temporary=archive.with_suffix('.tmp')
    temporary.write_bytes(raw)
    temporary.replace(archive)
    print('Real records:', len(result['items']), 'bytes:', len(raw))
