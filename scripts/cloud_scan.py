#!/usr/bin/env python3
"""Credential-free, bounded DropFinder snapshot scanner for GitHub Actions."""
from __future__ import annotations
import argparse, hashlib, html, json, math, os, re, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]; DEFAULT=ROOT/'cloud_pages'/'data'
UA='DropFinderCloud/9.0 (+https://github.com/Chicken3veryDay/Drop-finder)'; LIMIT=8_000_000; TIMEOUT=18
SOURCES=[
('arete','Arete',[('html','https://arete.shop/l/national/products/category/thca-flower','mixed_flower')]),
('black_tie_cbd','Black Tie CBD',[('html','https://www.blacktiecbd.net/collections/thca-flower','mixed_flower')]),
('crysp','Crysp',[('html','https://crysp.co/thca-flower/','thca_flower'),('woo','https://crysp.co/wp-json/wc/store/v1/products?per_page=100&search=flower','mixed_flower')]),
('five_leaf_wellness','Five Leaf Wellness',[('woo','https://fiveleafwellness.com/wp-json/wc/store/v1/products?per_page=100&search=flower','mixed_flower'),('woo','https://fiveleafwellness.com/wp-json/wc/store/v1/products?per_page=100','storewide'),('html','https://fiveleafwellness.com/shop/','storewide')]),
('green_unicorn_farms','Green Unicorn Farms',[('html','https://greenunicornfarms.com/category/thca-flower/','thca_flower'),('woo','https://greenunicornfarms.com/wp-json/wc/store/v1/products?per_page=100&search=thca','mixed_flower')]),
('hello_mary','Hello Mary',[('html','https://shophellomary.com/category/flower/','mixed_flower'),('woo','https://shophellomary.com/wp-json/wc/store/v1/products?per_page=100&search=flower','mixed_flower')]),
('holy_city_farms','Holy City Farms',[('woo','https://holycityfarms.com/wp-json/wc/store/v1/products?per_page=100&search=flower','mixed_flower'),('html','https://holycityfarms.com/product-category/smokeables/flower/','mixed_flower')]),
('loud_house_hemp','Loud House Hemp',[('woo','https://loudhempproducts.com/wp-json/wc/store/v1/products?per_page=100','storewide')]),
('lucky_elk','Lucky Elk',[('shopify','https://luckyelk.com/collections/thca-flower/products.json?limit=250','thca_flower')]),
('preston_herb_co','Preston Herb Co.',[('html','https://www.prestonherbco.com/categories/flower','mixed_flower')]),
('pure_roots_botanicals','Pure Roots Botanicals',[('html','https://purerootsbotanicals.com/product-category/thca-flower/','thca_flower'),('woo','https://purerootsbotanicals.com/wp-json/wc/store/v1/products?per_page=100&search=flower','mixed_flower')]),
('quantum_exotics','Quantum Exotics',[('html','https://www.quantumexotics.com/category/flower','mixed_flower')]),
('secret_nature','Secret Nature',[('shopify','https://secretnature.com/collections/thca-products/products.json?limit=250','thca_flower')]),
('sherlocks_glass','Sherlocks Glass & Dispensary',[('woo','https://sherlocksglass.com/wp-json/wc/store/v1/products?per_page=100&search=flower','mixed_flower')]),
('smoky_mountain_cbd','Smoky Mountain CBD',[('woo','https://www.smokymountaincbd.com/wp-json/wc/store/v1/products?per_page=100&search=flower','mixed_flower')]),
('stoney_branch_farms','Stoney Branch Farms',[('shopify','https://stoneybranch.com/collections/thca/products.json?limit=250','storewide')]),
('wnc_cbd','WNC CBD',[('html','https://wnc-cbd.com/high-thca-flower','mixed_flower')]),
]
HARD_EXCLUDE=re.compile(r'\b(pre[- ]?rolls?|prerolls?|vapes?|cartridges?|carts?|disposables?|gumm(?:y|ies)|edibles?|tinctures?|capsules?|beverages?|drinks?|seltzers?|concentrates?|rosin|badder|budder|crumble|isolate|dabs?|seeds?|clones?|incense|topicals?|salves?|balms?|creams?|lotions?|apparel|shirts?|hoodies?|hats?|posters?|fertilizer|accessories?|grinders?|trays?|glass|mushrooms?|amanita|pets?|gift cards?)\b',re.I)
AMBIGUOUS_FORM=re.compile(r'\b(joints?|blunts?|cones?|diamonds?|sauce|wax|resin|hash|batter|caviar|moon\s*rocks?|snow\s*caps?)\b',re.I)
FORM_CONTEXT=re.compile(r'\b(pack|piece|infused|coated|dusted|sprayed|extract|dab|concentrate|ready[- ]?to[- ]?smoke|filled|rolled|1\s*g)\b',re.I)
EXPLICIT_FLOWER=re.compile(r'\b(?:thca|hemp|high\s+thca)\s+flower\b',re.I)
FLOWER=re.compile(r'\b(thca\s+flower|hemp\s+flower|flower|buds?|smalls|shake)\b',re.I); THCA=re.compile(r'\b(thca|thc-a|high\s+thca|type\s+[i1])\b',re.I)
GRAM=re.compile(r'(?<!\d)(0\.5|1|2|3\.5|4|7|14|28|56|112)\s*(?:g|grams?)\b',re.I)
OUNCE=re.compile(r'(?<!\d)(1/8|1/4|1/2|1|2|4)(?:st|nd|rd|th)?\s*(?:oz|ounces?)\b',re.I)
WORD_WEIGHT=re.compile(r'\b(eighth|quarter|half\s+ounce|half[- ]?oz|ounce|one\s+ounce|zip)\b',re.I)
POTENCY=re.compile(r'\bTHC-?A\s*[:\-]?\s*(\d{1,2}(?:\.\d+)?)\s*%',re.I)
LD=re.compile(r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',re.I|re.S); TAG=re.compile(r'<[^>]+>'); WS=re.compile(r'\s+')
ANCHOR=re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',re.I|re.S)
META=re.compile(r'<meta\b([^>]+)>',re.I); ATTR=re.compile(r'([:\w-]+)\s*=\s*["\']([^"\']*)["\']',re.I)
TITLE=re.compile(r'<title\b[^>]*>(.*?)</title>',re.I|re.S)

def now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def text(v): return WS.sub(' ',TAG.sub(' ',html.unescape(str(v or '')))).strip()
def num(v):
 try: n=float(str(v).replace(',','').replace('$','').strip())
 except (TypeError,ValueError): return None
 return round(n,4) if math.isfinite(n) and 0<n<100000 else None
def grams(s):
 m=GRAM.search(s)
 if m:return num(m.group(1))
 m=OUNCE.search(s)
 if m:return round({'1/8':3.5437,'1/4':7.0874,'1/2':14.1748}.get(m.group(1),(num(m.group(1)) or 0)*28.3495),3)
 m=WORD_WEIGHT.search(s)
 return {'eighth':3.5437,'quarter':7.0874,'half ounce':14.1748,'half-oz':14.1748,'half oz':14.1748,'ounce':28.3495,'one ounce':28.3495,'zip':28.3495}.get(m.group(1).lower()) if m else None
def url(v,base):
 try:p=urllib.parse.urlsplit(urllib.parse.urljoin(base,str(v or '')))
 except ValueError:return ''
 if p.scheme not in {'http','https'} or not p.netloc:return ''
 q=[x for x in urllib.parse.parse_qsl(p.query) if x[0].lower()=='variant']
 return urllib.parse.urlunsplit((p.scheme,p.netloc.lower(),p.path.rstrip('/') or '/',urllib.parse.urlencode(q),''))
def fetch(target):
 req=urllib.request.Request(target,headers={'User-Agent':UA,'Accept':'application/json,text/html,application/xml;q=.8,*/*;q=.1','Accept-Encoding':'identity'})
 with urllib.request.urlopen(req,timeout=TIMEOUT) as r:
  raw=r.read(LIMIT+1)
  if len(raw)>LIMIT:raise ValueError('response too large')
  return raw.decode(r.headers.get_content_charset() or 'utf-8','replace'),str(r.headers.get('Content-Type') or '').split(';')[0].lower(),int(getattr(r,'status',200))
def availability(v):
 s=str(v or '').lower()
 if any(x in s for x in ('instock','in_stock','in stock','available','true')):return 'in_stock'
 if any(x in s for x in ('outofstock','out_of_stock','out of stock','sold out','false')):return 'out_of_stock'
 return 'unknown'
def record(sid,vendor,route,name,target,desc='',price=None,stock='',image='',variant=''):
 name=text(name);desc=text(desc);target=url(target,route[1]);combined=f'{name} {desc}'
 if not name or not target or HARD_EXCLUDE.search(combined) or not FLOWER.search(combined) or not (THCA.search(combined) or 'thca' in route[1].lower()):return None
 ambiguous=AMBIGUOUS_FORM.search(combined)
 if ambiguous and FORM_CONTEXT.search(combined) and not EXPLICIT_FLOWER.search(name):return None
 p=num(price);g=grams(combined);pots=[num(x) for x in POTENCY.findall(combined)];pot=max([x for x in pots if x and x<=100],default=None)
 return {'id':hashlib.sha256(f'{sid}|{target}|{variant}'.encode()).hexdigest()[:24],'source_id':sid,'vendor':vendor,'name':name,'url':target,'image':url(image,route[1]) if image else '', 'price':p,'grams':g,'price_per_gram':round(p/g,4) if p and g else None,'thca':pot,'availability':availability(stock),'variant':text(variant),'source_type':route[0],'route_url':route[1],'collected_at':now()}
def shopify(payload,sid,vendor,route):
 data=json.loads(payload);rows=[];base=route[1].split('/collections/',1)[0].split('/products.json',1)[0]
 for item in data.get('products',[]) if isinstance(data,dict) else []:
  if not isinstance(item,dict):continue
  product_url=f"{base}/products/{item.get('handle')}";images=item.get('images') or [];image=(images[0].get('src','') if images and isinstance(images[0],dict) else '')
  variants=item.get('variants') or [{}]
  for v in variants:
   if not isinstance(v,dict):continue
   vt=text(v.get('title'));name=item.get('title');name=f'{name} {vt}' if vt and vt.lower()!='default title' else name
   r=record(sid,vendor,route,name,f"{product_url}?variant={v.get('id')}" if v.get('id') else product_url,item.get('body_html',''),v.get('price'),v.get('available'),image,vt)
   if r:rows.append(r)
 return rows
def woo(payload,sid,vendor,route):
 data=json.loads(payload);data=data if isinstance(data,list) else data.get('products',[]);rows=[]
 for item in data:
  if not isinstance(item,dict):continue
  prices=item.get('prices') or {};minor=int(prices.get('currency_minor_unit',2) or 2);p=next((num(prices.get(k)) for k in ('sale_price','price','regular_price') if num(prices.get(k))),None);p=round(p/(10**minor),4) if p else None
  images=item.get('images') or [];image=images[0].get('src','') if images and isinstance(images[0],dict) else ''
  cats=' '.join(text(x.get('name')) for x in item.get('categories',[]) if isinstance(x,dict))
  r=record(sid,vendor,route,item.get('name'),item.get('permalink'),f"{item.get('short_description','')} {item.get('description','')} {cats}",p,item.get('stock_status') or item.get('is_in_stock'),image)
  if r:rows.append(r)
 return rows
def objects(v):
 if isinstance(v,dict):
  yield v
  for k in ('@graph','itemListElement','mainEntity','item','offers','hasVariant'):
   if isinstance(v.get(k),(dict,list)):yield from objects(v[k])
 elif isinstance(v,list):
  for x in v:yield from objects(x)
def html_products(payload,sid,vendor,route):
 rows=[]
 for raw in LD.findall(payload):
  try:data=json.loads(html.unescape(raw.strip()))
  except json.JSONDecodeError:continue
  for o in objects(data):
   t=o.get('@type');types={str(x).lower() for x in (t if isinstance(t,list) else [t])}
   if 'product' not in types:continue
   offers=o.get('offers');offers=offers[0] if isinstance(offers,list) and offers else offers;offers=offers if isinstance(offers,dict) else {}
   image=o.get('image');image=image[0] if isinstance(image,list) and image else image;image=(image.get('url') or image.get('contentUrl')) if isinstance(image,dict) else image
   r=record(sid,vendor,route,o.get('name'),o.get('url') or o.get('@id'),o.get('description'),offers.get('price') or offers.get('lowPrice'),offers.get('availability'),image)
   if r:rows.append(r)
 return rows
def meta_values(payload):
 values={}
 for raw in META.findall(payload):
  attrs={k.lower():html.unescape(v) for k,v in ATTR.findall(raw)};key=(attrs.get('property') or attrs.get('name') or '').lower();value=attrs.get('content','')
  if key and value:values.setdefault(key,value)
 return values
def html_detail(payload,sid,vendor,route,target):
 rows=html_products(payload,sid,vendor,route)
 if rows:return rows
 meta=meta_values(payload);title=meta.get('og:title') or meta.get('twitter:title');m=TITLE.search(payload)
 if not title and m:title=text(m.group(1)).split('|')[0].strip()
 desc=meta.get('og:description') or meta.get('description') or '';price=meta.get('product:price:amount') or meta.get('og:price:amount');stock=meta.get('product:availability') or '';image=meta.get('og:image') or meta.get('twitter:image') or ''
 row=record(sid,vendor,route,title,target,desc,price,stock,image)
 return [row] if row else []
def product_links(payload,route):
 base=urllib.parse.urlsplit(route[1]);seen=[]
 for href,label in ANCHOR.findall(payload):
  target=url(href,route[1]);parsed=urllib.parse.urlsplit(target);label=text(label);path=parsed.path.lower()
  if not target or parsed.netloc!=base.netloc.lower() or target==url(route[1],route[1]):continue
  if not any(marker in path for marker in ('/product/','/products/','/shop/','/l/national/products/')):continue
  signal=f'{label} {path.replace("-"," ")}'
  if not FLOWER.search(signal) or not (THCA.search(signal) or 'thca' in route[1].lower()):continue
  if target not in seen:seen.append(target)
  if len(seen)>=12:break
 return seen
def html_with_details(payload,sid,vendor,route):
 rows=html_products(payload,sid,vendor,route)
 if rows:return rows
 links=product_links(payload,route);out=[]
 for target in links:
  try:detail,ctype,status=fetch(target)
  except Exception:continue
  if status==200 and ctype in {'text/html','application/xhtml+xml'}:out.extend(html_detail(detail,sid,vendor,route,target))
 return dedupe(out)
def dedupe(rows):
 out={}
 for r in rows:out[(r['source_id'],r['url'],r.get('variant',''))]=r
 return sorted(out.values(),key=lambda r:(r['vendor'],r['name'],r.get('price') or 1e12))
def scan(source):
 sid,vendor,routes=source;started=time.monotonic();attempts=[]
 for idx,route in enumerate(routes,1):
  rr={'route_id':f'{sid}-{idx}','url':route[1],'source_type':route[0]};t=time.monotonic()
  try:
   payload,ctype,status=fetch(route[1]);rr.update(http_status=status,content_type=ctype)
   rows=shopify(payload,sid,vendor,route) if route[0]=='shopify' else woo(payload,sid,vendor,route) if route[0]=='woo' else html_with_details(payload,sid,vendor,route)
   rr.update(status='healthy' if rows else 'empty',products=len(rows),duration_seconds=round(time.monotonic()-t,3));attempts.append(rr)
   if rows:return dedupe(rows),{'source_id':sid,'name':vendor,'enabled':True,'status':'healthy','products':len(rows),'routes_attempted':len(attempts),'active_route':route[1],'route_results':attempts,'duration_seconds':round(time.monotonic()-started,3)}
  except urllib.error.HTTPError as e:rr.update(status='http_error',http_status=e.code,error=f'HTTP {e.code}')
  except Exception as e:rr.update(status='error',error=f'{type(e).__name__}: {text(e)[:220]}')
  if not attempts or attempts[-1] is not rr:
   rr['duration_seconds']=round(time.monotonic()-t,3);attempts.append(rr)
 return [],{'source_id':sid,'name':vendor,'enabled':True,'status':'degraded','products':0,'routes_attempted':len(attempts),'active_route':'','route_results':attempts,'duration_seconds':round(time.monotonic()-started,3)}
def write(path,payload):
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');os.replace(tmp,path)
def run_shard(out,shard,shards):
 selected=[s for i,s in enumerate(SOURCES) if i%shards==shard];products=[];statuses=[]
 with ThreadPoolExecutor(max_workers=2) as pool:
  jobs={pool.submit(scan,s):s for s in selected}
  for f in as_completed(jobs):
   try:p,s=f.result()
   except Exception as e:
    src=jobs[f];p=[];s={'source_id':src[0],'name':src[1],'enabled':True,'status':'error','products':0,'error':f'{type(e).__name__}: {text(e)[:220]}'}
   products+=p;statuses.append(s);print(f"[{s['status']}] {s['source_id']}: {len(p)}")
 write(out/f'shard-{shard}.json',{'generated_at':now(),'shard':shard,'products':dedupe(products),'sources':statuses});return 0
def merge(inp,out,previous=None):
 files=sorted(inp.rglob('shard-*.json'))
 if not files:raise SystemExit('no shard outputs')
 products=[];statuses=[]
 for p in files:
  d=json.loads(p.read_text());products+=d.get('products',[]);statuses+=d.get('sources',[])
 products=dedupe(products);current={x['source_id'] for x in products};by={x['source_id']:x for x in statuses}
 if previous and previous.is_file():
  try:old=json.loads(previous.read_text()).get('products',[])
  except Exception:old=[]
  for r in old:
   sid=r.get('source_id')
   if sid and sid not in current and by.get(sid,{}).get('status')!='healthy':r=dict(r);r.update(stale=True,stale_reason='latest scan failed');products.append(r)
 products=dedupe(products);stamp=now();healthy=sum(x.get('status')=='healthy' for x in statuses)
 write(out/'catalog.json',{'schema_version':'dropfinder-cloud-catalog-v1','generated_at':stamp,'product_count':len(products),'products':products})
 write(out/'status.json',{'schema_version':'dropfinder-cloud-status-v1','generated_at':stamp,'version':'9.0.0-cloud','mode':'credential_free_github_pages','source_count':35,'enabled_sources':len(SOURCES),'healthy_sources':healthy,'degraded_sources':len(SOURCES)-healthy,'healthy_routes':healthy,'product_count':len(products),'sources':sorted(statuses,key=lambda x:x['source_id']),'limitations':['Read-only static snapshot; GitHub Pages cannot run the FastAPI/TUI worker service.','Only normalized public fields are published; raw responses, headers, cookies, databases and evidence are never uploaded.','Cloud scan health is not equivalent to full v9 live-source certification.']});print(f'merged {len(products)} products, {healthy}/{len(SOURCES)} healthy');return 0
def selftest():
 assert grams('1/8th ounce')==3.544;assert grams('quarter oz')==7.0874
 for label,expected in (('1 oz',28.349),('2 ounces',56.699),('4 oz',113.398),('1/4 oz',7.087),('1/2 ounce',14.175),('3.5 grams',3.5)):assert grams(label)==expected
 for label in ('Tier 1','Type 2','4 pack','After 8th Mark 1','THCA 24.1%','THCA 18.2%','THCA 22.4%'):assert grams(label) is None
 assert grams('Blue Dream THCA Flower THCA 24.1% 3.5g')==3.5
 route=('shopify','https://example.com/collections/thca-flower/products.json','thca_flower');payload=json.dumps({'products':[{'title':'Blue Dream THCA Flower','handle':'blue','body_html':'3.5g THCA 24.1%','variants':[{'id':1,'title':'3.5g','price':'35','available':True}]},{'title':'THCA Pre-Rolls','handle':'rolls','variants':[{'id':2,'price':'20'}]}]});rows=shopify(payload,'fixture','Fixture',route);assert len(rows)==1 and rows[0]['price_per_gram']==10;print('cloud scanner self-test passed');return 0
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=DEFAULT);p.add_argument('--shard',type=int);p.add_argument('--shards',type=int,default=6);p.add_argument('--merge',type=Path);p.add_argument('--previous-catalog',type=Path);p.add_argument('--self-test',action='store_true');a=p.parse_args()
 if a.self_test:return selftest()
 if a.merge:return merge(a.merge,a.output,a.previous_catalog)
 if a.shard is None or not 0<=a.shard<a.shards:p.error('--shard is required')
 return run_shard(a.output,a.shard,a.shards)
if __name__=='__main__':raise SystemExit(main())
