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
GRAM=re.compile(r'(?<![\d.])(0\.5|1|2|3\.5|4|7|14|28|56|112)\s*(?:g|grams?)\b',re.I)
POUND=re.compile(r'(?<![\d.])(1/4|1/2|1|2|4)\s*(?:lb|lbs|pounds?)\b',re.I)
WORD_POUND=re.compile(r'\b(quarter|half|one|two|four)\s+pounds?\b',re.I)
OUNCE=re.compile(r'(?<![\d.])(1/8|1/4|1/2|1|2|4)(?:st|nd|rd|th)?\s*(?:oz|ounces?)\b',re.I)
BARE_FRACTION_OUNCE=re.compile(r'(?<![\d.])(1/8|1/4|1/2)(?:st|nd|rd|th)?\b',re.I)
WORD_WEIGHT=re.compile(r'\b(eighth|quarter|half\s+ounce|half[- ]?oz|ounce|one\s+ounce|zip)\b(?!\s*(?:lb|lbs|pounds?)\b)',re.I)
POTENCY=re.compile(r'\bTHC-?A\s*[:\-]?\s*(\d{1,2}(?:\.\d+)?)\s*%',re.I)
LD=re.compile(r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',re.I|re.S); TAG=re.compile(r'<[^>]+>'); WS=re.compile(r'\s+')
ANCHOR=re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',re.I|re.S)
META=re.compile(r'<meta\b([^>]+)>',re.I); ATTR=re.compile(r'([:\w-]+)\s*=\s*["\']([^"\']*)["\']',re.I)
TITLE=re.compile(r'<title\b[^>]*>(.*?)</title>',re.I|re.S)
STOCK_SEPARATOR=re.compile(r'[_\-/]+')
NEGATIVE_STOCK=re.compile(r'\b(?:out\s+of\s+stock|outofstock|sold\s+out|unavailable|not(?:\s+\w+){0,2}\s+(?:available|in\s+stock))\b',re.I)
POSITIVE_STOCK=re.compile(r'\b(?:in\s+stock|instock|available(?:\s+for\s+order)?)\b',re.I)
WOO_VARIATION_RETRY_DELAYS=(0.0,1.0,3.0);WOO_VARIATION_MAX_PAGES=5;WOO_RETRYABLE_HTTP={408,425,429,500,502,503,504}

def now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def text(v): return WS.sub(' ',TAG.sub(' ',html.unescape(str(v or '')))).strip()
def num(v):
 try: n=float(str(v).replace(',','').replace('$','').strip())
 except (TypeError,ValueError): return None
 return round(n,4) if math.isfinite(n) and 0<n<100000 else None
def weight(s):
 m=GRAM.search(s)
 if m:return num(m.group(1)),text(m.group(0))
 m=POUND.search(s)
 if m:return {'1/4':112.0,'1/2':224.0,'1':448.0,'2':896.0,'4':1792.0}[m.group(1)],text(m.group(0))
 m=WORD_POUND.search(s)
 if m:return {'quarter':112.0,'half':224.0,'one':448.0,'two':896.0,'four':1792.0}[m.group(1).lower()],text(m.group(0))
 m=OUNCE.search(s) or BARE_FRACTION_OUNCE.search(s)
 if m:return round({'1/8':3.5437,'1/4':7.0874,'1/2':14.1748}.get(m.group(1),(num(m.group(1)) or 0)*28.3495),3),text(m.group(0))
 m=WORD_WEIGHT.search(s)
 if m:return {'eighth':3.5437,'quarter':7.0874,'half ounce':14.1748,'half-oz':14.1748,'half oz':14.1748,'ounce':28.3495,'one ounce':28.3495,'zip':28.3495}.get(m.group(1).lower()),text(m.group(0))
 return None,''
def grams(s):return weight(s)[0]
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
 if isinstance(v,bool):return 'in_stock' if v else 'out_of_stock'
 s=WS.sub(' ',STOCK_SEPARATOR.sub(' ',str(v or '').casefold())).strip()
 if not s:return 'unknown'
 if s=='false' or NEGATIVE_STOCK.search(s):return 'out_of_stock'
 if s=='true' or POSITIVE_STOCK.search(s):return 'in_stock'
 return 'unknown'
def record(sid,vendor,route,name,target,desc='',price=None,stock='',image='',variant=''):
 name=text(name);desc=text(desc);target=url(target,route[1]);combined=f'{name} {desc}'
 if not name or not target or HARD_EXCLUDE.search(combined) or not FLOWER.search(combined) or not (THCA.search(combined) or 'thca' in route[1].lower()):return None
 ambiguous=AMBIGUOUS_FORM.search(combined)
 if ambiguous and FORM_CONTEXT.search(combined) and not EXPLICIT_FLOWER.search(name):return None
 p=num(price);g,weight_label=weight(combined);pots=[num(x) for x in POTENCY.findall(combined)];pot=max([x for x in pots if x and x<=100],default=None);stock_state=availability(stock)
 stock_method='explicit_boolean' if isinstance(stock,bool) else 'explicit_source_state' if stock_state!='unknown' else 'unknown'
 return {'id':hashlib.sha256(f'{sid}|{target}|{variant}'.encode()).hexdigest()[:24],'source_id':sid,'vendor':vendor,'name':name,'url':target,'image':url(image,route[1]) if image else '', 'price':p,'grams':g,'source_weight_label':weight_label,'weight_provenance':'explicit_text' if weight_label else 'unavailable','price_per_gram':round(p/g,4) if p and g else None,'thca':pot,'availability':stock_state,'availability_raw':stock,'availability_normalization':stock_method,'variant':text(variant),'source_type':route[0],'route_url':route[1],'collected_at':now()}
def record_identity(row,source_product_id='',source_variant_id='',regular_price=None):
 if not row:return None
 row=dict(row);row['source_product_id']=text(source_product_id);row['source_variant_id']=text(source_variant_id);regular=num(regular_price);current=num(row.get('price'));row['original_price']=regular if regular and current and regular>current else None
 if source_variant_id:row['id']=hashlib.sha256(f"{row.get('source_id')}|{row.get('url')}|{source_variant_id}".encode()).hexdigest()[:24]
 return row
def shopify(payload,sid,vendor,route):
 data=json.loads(payload);rows=[];base=route[1].split('/collections/',1)[0].split('/products.json',1)[0]
 for item in data.get('products',[]) if isinstance(data,dict) else []:
  if not isinstance(item,dict):continue
  product_url=f"{base}/products/{item.get('handle')}";images=item.get('images') or [];image=(images[0].get('src','') if images and isinstance(images[0],dict) else '')
  variants=item.get('variants') or [{}]
  for v in variants:
   if not isinstance(v,dict):continue
   vt=text(v.get('title'));name=item.get('title');name=f'{name} {vt}' if vt and vt.lower()!='default title' else name
   r=record_identity(record(sid,vendor,route,name,f"{product_url}?variant={v.get('id')}" if v.get('id') else product_url,item.get('body_html',''),v.get('price'),v.get('available'),image,vt),item.get('id'),v.get('id'),v.get('compare_at_price'))
   if r:rows.append(r)
 return rows
def woo_price(item):
 prices=item.get('prices') or {};minor=int(prices.get('currency_minor_unit',2) or 2)
 current=next((num(prices.get(k)) for k in ('sale_price','price','regular_price') if num(prices.get(k))),None);regular=num(prices.get('regular_price'))
 return (round(current/(10**minor),4) if current else None,round(regular/(10**minor),4) if regular else None)
def woo_variant_label(item,parent=None):
 raw=text(item.get('variation'))
 if raw:return raw
 attrs=[]
 for value in item.get('attributes',[]) if isinstance(item.get('attributes'),list) else []:
  if isinstance(value,dict):
   label=text(value.get('value') or value.get('term') or value.get('option'))
   if label:attrs.append(label)
 if attrs:return ' / '.join(attrs)
 name=text(item.get('name'));parent_name=text((parent or {}).get('name'))
 if parent_name and name.lower().startswith(parent_name.lower()):name=name[len(parent_name):].lstrip(' -–—:')
 return name
def woo_variant_endpoint(route_url,parent_id,page):
 parsed=urllib.parse.urlsplit(route_url);query={'type':'variation','parent':str(parent_id),'per_page':'100','page':str(page)}
 return urllib.parse.urlunsplit((parsed.scheme,parsed.netloc,parsed.path,'&'.join(f'{urllib.parse.quote(k)}={urllib.parse.quote(v)}' for k,v in query.items()),''))
def woo_fetch_variations(parent,route):
 diagnostics={'variation_requests':0,'variation_retries':0,'variation_failures':0,'variation_failure_reasons':{}};rows=[]
 parent_id=parent.get('id')
 if parent_id in (None,''):
  diagnostics['variation_failures']=1;diagnostics['variation_failure_reasons']={'variation_parent_id_missing':1};return rows,diagnostics
 for page in range(1,WOO_VARIATION_MAX_PAGES+1):
  target=woo_variant_endpoint(route[1],parent_id,page);page_rows=None;terminal=''
  for attempt,delay in enumerate(WOO_VARIATION_RETRY_DELAYS,1):
   if delay:time.sleep(delay)
   diagnostics['variation_requests']+=1
   try:raw,ctype,status=fetch(target)
   except urllib.error.HTTPError as e:
    terminal=f'variation_http_{e.code}'
    if e.code in WOO_RETRYABLE_HTTP and attempt<len(WOO_VARIATION_RETRY_DELAYS):diagnostics['variation_retries']+=1;continue
    break
   except Exception as e:
    terminal=f'variation_{type(e).__name__.lower()}'
    if isinstance(e,(TimeoutError,urllib.error.URLError)) and attempt<len(WOO_VARIATION_RETRY_DELAYS):diagnostics['variation_retries']+=1;continue
    break
   if status!=200:
    terminal=f'variation_http_{status}'
    if status in WOO_RETRYABLE_HTTP and attempt<len(WOO_VARIATION_RETRY_DELAYS):diagnostics['variation_retries']+=1;continue
    break
   if ctype not in {'application/json','text/json'}:terminal='variation_invalid_content_type';break
   try:decoded=json.loads(raw)
   except json.JSONDecodeError:terminal='variation_invalid_json';break
   page_rows=decoded if isinstance(decoded,list) else decoded.get('products',[]) if isinstance(decoded,dict) else []
   break
  if page_rows is None:
   diagnostics['variation_failures']+=1;diagnostics['variation_failure_reasons'][terminal or 'variation_fetch_failed']=diagnostics['variation_failure_reasons'].get(terminal or 'variation_fetch_failed',0)+1;break
  rows.extend(item for item in page_rows if isinstance(item,dict))
  if len(page_rows)<100:break
 else:
  diagnostics['variation_failures']+=1;diagnostics['variation_failure_reasons']['variation_page_limit']=1
 return rows,diagnostics
def woo(payload,sid,vendor,route):
 data=json.loads(payload);data=data if isinstance(data,list) else data.get('products',[]);rows=[];diagnostics={'variable_parents':0,'variation_requests':0,'variation_retries':0,'variation_failures':0,'variation_failure_reasons':{},'variation_rejections':0,'variation_rejection_reasons':{}}
 def merge_diag(extra):
  for key in ('variation_requests','variation_retries','variation_failures'):diagnostics[key]+=int(extra.get(key) or 0)
  for reason,count in (extra.get('variation_failure_reasons') or {}).items():diagnostics['variation_failure_reasons'][reason]=diagnostics['variation_failure_reasons'].get(reason,0)+int(count)
 def reject(reason):diagnostics['variation_rejections']+=1;diagnostics['variation_rejection_reasons'][reason]=diagnostics['variation_rejection_reasons'].get(reason,0)+1
 for item in data:
  if not isinstance(item,dict):continue
  is_variation=str(item.get('type') or '').lower()=='variation' or bool(item.get('parent'))
  if is_variation:
   parent={};variations=[item]
  elif item.get('has_options') is True or str(item.get('type') or '').lower()=='variable':
   diagnostics['variable_parents']+=1;variations,extra=woo_fetch_variations(item,route);merge_diag(extra);parent=item
  else:
   p,regular=woo_price(item);images=item.get('images') or [];image=images[0].get('src','') if images and isinstance(images[0],dict) else '';cats=' '.join(text(x.get('name')) for x in item.get('categories',[]) if isinstance(x,dict));r=record_identity(record(sid,vendor,route,item.get('name'),item.get('permalink'),f"{item.get('short_description','')} {item.get('description','')} {cats}",p,item.get('stock_status') or item.get('is_in_stock'),image,''),item.get('id'),'',regular)
   if r:rows.append(r)
   continue
  for variation in variations:
   stock=variation.get('stock_status') if variation.get('stock_status') not in (None,'') else variation.get('is_in_stock')
   if availability(stock)!='in_stock':reject('variation_not_explicitly_in_stock');continue
   label=woo_variant_label(variation,parent)
   if not label or grams(label) is None:reject('variation_weight_missing');continue
   p,regular=woo_price(variation);parent_name=parent.get('name') or variation.get('name');parent_id=parent.get('id') or variation.get('parent');variation_id=variation.get('id');parent_url=parent.get('permalink') or variation.get('permalink');target=f"{parent_url}{'&' if '?' in str(parent_url) else '?'}variant={variation_id}" if variation_id else parent_url;images=variation.get('images') or parent.get('images') or [];image=images[0].get('src','') if images and isinstance(images[0],dict) else '';cats=' '.join(text(x.get('name')) for x in parent.get('categories',[]) if isinstance(x,dict));desc=f"{variation.get('description','')} {cats}";name=f'{parent_name} {label}'
   r=record_identity(record(sid,vendor,route,name,target,desc,p,stock,image,label),parent_id,variation_id,regular)
   if r:rows.append(r)
 return dedupe(rows),diagnostics
def objects(v):
 if isinstance(v,dict):
  yield v
  for k in ('@graph','itemListElement','mainEntity','item','offers','hasVariant'):
   if isinstance(v.get(k),(dict,list)):yield from objects(v[k])
 elif isinstance(v,list):
  for x in v:yield from objects(x)
def product_identity(target):
 try:parsed=urllib.parse.urlsplit(str(target or ''))
 except ValueError:return ''
 if parsed.scheme not in {'http','https'} or not parsed.netloc:return ''
 return urllib.parse.urlunsplit((parsed.scheme,parsed.netloc.lower(),parsed.path.rstrip('/') or '/','',''))
def structured_types(value):
 raw=value.get('@type') if isinstance(value,dict) else None
 return {str(item).lower() for item in (raw if isinstance(raw,list) else [raw]) if item}
def structured_image(value):
 if isinstance(value,list):value=value[0] if value else ''
 if isinstance(value,dict):value=value.get('url') or value.get('contentUrl') or ''
 return value or ''
def structured_offers(value):
 if isinstance(value,dict):return [value]
 if isinstance(value,list):return [item for item in value if isinstance(item,dict)]
 return []
def offer_price(offer):
 specification=offer.get('priceSpecification')
 if isinstance(specification,list):specification=next((item for item in specification if isinstance(item,dict)),{})
 if not isinstance(specification,dict):specification={}
 return offer.get('price') or offer.get('lowPrice') or specification.get('price') or specification.get('lowPrice')
def offer_label(offer):
 for key in ('name','size','sku','description'):
  label=text(offer.get(key))
  if label and grams(label) is not None:return label
 return text(offer.get('name') or offer.get('sku') or '')
def offer_identity(offer):
 return text(offer.get('sku') or offer.get('serialNumber') or offer.get('@id') or offer.get('url') or offer.get('name'))
def offer_authority(offer,product_target):
 target=offer.get('url') or product_target
 return (
  0 if product_identity(target)==product_identity(product_target) else 1,
  0 if availability(offer.get('availability'))=='in_stock' else 1,
  0 if num(offer_price(offer)) is not None else 1,
  offer_identity(offer),
  json.dumps(offer,sort_keys=True,default=str),
 )
def product_offer_rows(product,sid,vendor,route):
 product_name=text(product.get('name'));product_desc=text(product.get('description'));product_target=product.get('url') or product.get('@id');product_image=structured_image(product.get('image'));product_id=product.get('productID') or product.get('sku') or product.get('@id') or product_target
 offers=structured_offers(product.get('offers'))
 if not offers:
  row=record_identity(record(sid,vendor,route,product_name,product_target,product_desc,None,'',product_image,''),product_id,'')
  return [row] if row else []
 package_by_weight={}
 for offer in offers:
  label=offer_label(offer);package_grams=grams(label)
  if package_grams is None or availability(offer.get('availability'))=='out_of_stock':continue
  key=round(float(package_grams),6);current=package_by_weight.get(key)
  if current is None or offer_authority(offer,product_target)<offer_authority(current,product_target):package_by_weight[key]=offer
 if package_by_weight:
  rows=[]
  for key in sorted(package_by_weight):
   offer=package_by_weight[key];label=offer_label(offer);target=offer.get('url') or product_target;variant_id=offer_identity(offer) or label;name=product_name if label.lower() in product_name.lower() else f'{product_name} {label}'.strip();desc=f"{product_desc} {text(offer.get('description'))}".strip();image=structured_image(offer.get('image')) or product_image
   row=record_identity(record(sid,vendor,route,name,target,desc,offer_price(offer),offer.get('availability'),image,label),product_id,variant_id)
   if row:rows.append(row)
  return rows
 if len(offers)!=1:return []
 offer=offers[0]
 if availability(offer.get('availability'))=='out_of_stock':return []
 label=offer_label(offer);target=offer.get('url') or product_target;variant=label if grams(label) is not None else '';variant_id=offer_identity(offer) or variant;name=product_name if not variant or variant.lower() in product_name.lower() else f'{product_name} {variant}'.strip();desc=f"{product_desc} {text(offer.get('description'))}".strip();image=structured_image(offer.get('image')) or product_image
 row=record_identity(record(sid,vendor,route,name,target,desc,offer_price(offer),offer.get('availability'),image,variant),product_id,variant_id)
 return [row] if row else []
def html_products(payload,sid,vendor,route):
 rows=[]
 for raw in LD.findall(payload):
  try:data=json.loads(html.unescape(raw.strip()))
  except json.JSONDecodeError:continue
  for product in objects(data):
   if 'product' not in structured_types(product):continue
   rows.extend(product_offer_rows(product,sid,vendor,route))
 return dedupe(rows)
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
def html_with_details(payload,sid,vendor,route,diagnostics=None):
 diagnostics=diagnostics if isinstance(diagnostics,dict) else {}
 structured=html_products(payload,sid,vendor,route);links=product_links(payload,route);covered={product_identity(row.get('url')) for row in structured if product_identity(row.get('url'))};out=list(structured)
 diagnostics.update(structured_products=len(structured),discovered_product_links=len(links),covered_product_links=0,detail_requests=0,detail_failures=0,detail_failure_reasons={})
 def failure(reason):
  diagnostics['detail_failures']+=1;diagnostics['detail_failure_reasons'][reason]=diagnostics['detail_failure_reasons'].get(reason,0)+1
 for target in links:
  identity=product_identity(target)
  if identity and identity in covered:
   diagnostics['covered_product_links']+=1;continue
  diagnostics['detail_requests']+=1
  try:detail,ctype,status=fetch(target)
  except urllib.error.HTTPError as exc:failure(f'detail_http_{exc.code}');continue
  except Exception as exc:failure(f'detail_{type(exc).__name__.lower()}');continue
  if status!=200:failure(f'detail_http_{status}');continue
  if ctype not in {'text/html','application/xhtml+xml'}:failure('detail_invalid_content_type');continue
  detail_rows=html_detail(detail,sid,vendor,route,target)
  if not detail_rows:failure('detail_no_product_rows');continue
  out.extend(detail_rows);covered.update(product_identity(row.get('url')) for row in detail_rows if product_identity(row.get('url')))
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
   if route[0]=='shopify':rows=shopify(payload,sid,vendor,route);route_diagnostics={}
   elif route[0]=='woo':rows,route_diagnostics=woo(payload,sid,vendor,route)
   else:
    route_diagnostics={};rows=html_with_details(payload,sid,vendor,route,route_diagnostics)
   rr.update(route_diagnostics);health_reason_codes=[]
   if rr.get('variation_failures'):health_reason_codes.append('woocommerce_variation_incomplete')
   if rr.get('detail_failures'):health_reason_codes.append('html_detail_discovery_incomplete')
   route_status='degraded' if health_reason_codes else 'healthy' if rows else 'empty';rr.update(status=route_status,health_reason_codes=health_reason_codes,products=len(rows),duration_seconds=round(time.monotonic()-t,3));attempts.append(rr)
   if rows:return dedupe(rows),{'source_id':sid,'name':vendor,'enabled':True,'status':route_status,'health_reason_codes':health_reason_codes,'products':len(rows),'routes_attempted':len(attempts),'active_route':route[1],'route_results':attempts,'duration_seconds':round(time.monotonic()-started,3)}
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
 assert grams('1/8th ounce')==3.544;assert grams('quarter oz')==7.0874;assert grams('Quarter Pound')==112.0
 assert all(grams(value) is None for value in ('Tier 1','Type 1','4 pack','THCA 24.1%','THCA 18.2%','THCA 22.4%'))
 assert all(availability(value)=='out_of_stock' for value in ('unavailable','currently unavailable','not available','not yet available','not in stock','sold out'))
 assert all(availability(value)=='in_stock' for value in (True,'available','currently available','available for order','in_stock'))
 assert availability('availability pending')=='unknown'
 route=('shopify','https://example.com/collections/thca-flower/products.json','thca_flower');payload=json.dumps({'products':[{'title':'Blue Dream THCA Flower','handle':'blue','body_html':'3.5g THCA 24.1%','variants':[{'id':1,'title':'3.5g','price':'35','available':True}]},{'title':'THCA Pre-Rolls','handle':'rolls','variants':[{'id':2,'price':'20'}]}]});rows=shopify(payload,'fixture','Fixture',route);assert len(rows)==1 and rows[0]['price_per_gram']==10;print('cloud scanner self-test passed');return 0
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=DEFAULT);p.add_argument('--shard',type=int);p.add_argument('--shards',type=int,default=6);p.add_argument('--merge',type=Path);p.add_argument('--previous-catalog',type=Path);p.add_argument('--self-test',action='store_true');a=p.parse_args()
 if a.self_test:return selftest()
 if a.merge:return merge(a.merge,a.output,a.previous_catalog)
 if a.shard is None or not 0<=a.shard<a.shards:p.error('--shard is required')
 return run_shard(a.output,a.shard,a.shards)
if __name__=='__main__':raise SystemExit(main())
