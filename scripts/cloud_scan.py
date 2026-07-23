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
DESCRIPTION_LIMIT=2400
THCA_PATTERNS=(
 re.compile(r'\b(?:total\s+)?thc-?a(?:\s+(?:content|potency))?\s*[:\-]?\s*(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)(?!\w)',re.I),
 re.compile(r'\b(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)\s*(?:total\s+)?thc-?a\b',re.I),
)
DELTA9_PATTERNS=(
 re.compile(r'\b(?:delta\s*[- ]?9|d9)(?:\s*thc)?(?:\s+(?:content|potency))?\s*[:\-]?\s*(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)(?!\w)',re.I),
 re.compile(r'\b(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)\s*(?:delta\s*[- ]?9|d9)(?:\s*thc)?\b',re.I),
)
TOTAL_THC_PATTERNS=(
 re.compile(r'\btotal\s+thc(?!-?a)(?:\s+(?:content|potency))?\s*[:\-]?\s*(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)(?!\w)',re.I),
 re.compile(r'\b(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)\s*total\s+thc(?!-?a)\b',re.I),
)
POTENCY=THCA_PATTERNS[0]
LD=re.compile(r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',re.I|re.S); TAG=re.compile(r'<[^>]+>'); WS=re.compile(r'\s+')
ANCHOR=re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',re.I|re.S)
ANCHOR_FULL=re.compile(r'<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>',re.I|re.S)
OPEN_TAG=re.compile(r'<[^>]{1,1800}>',re.I|re.S)
DOCUMENT_SIGNAL=re.compile(r'\b(?:coa|certificate\s+of\s+analysis|download\s+(?:the\s+)?coa|view\s+(?:the\s+)?coa|lab\s+(?:report|results?)|full\s+panel|test\s+results?)\b',re.I)
DOCUMENT_PATH_SIGNAL=re.compile(r'(?:coa|certificate|lab[-_ ]?(?:report|result)|full[-_ ]?panel|test[-_ ]?result)',re.I)
LINEAGE_FIELD=re.compile(r'\b(?:strain\s+(?:family|type|profile)|lineage)\s*[:\-]?\s*(indica(?:[- ](?:dominant|leaning)(?:[- ]hybrid)?)?|sativa(?:[- ](?:dominant|leaning)(?:[- ]hybrid)?)?|balanced[- ]hybrid|hybrid)\b',re.I)
ENVIRONMENT_FIELD=re.compile(r'\b(?:grow(?:n|\s+method|\s+environment)?|cultivation|environment)\s*[:\-]?\s*(indoor|outdoor|greenhouse|mixed[- ]light|sun[- ]grown)\b',re.I)
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

def bounded_number(v,minimum,maximum):
 try:n=float(str(v).replace(',','').replace('$','').strip())
 except (TypeError,ValueError):return None
 return round(n,4) if math.isfinite(n) and minimum<=n<=maximum else None
def percent_number(v):return bounded_number(v,0.0001,100)
def percent_from_text(value,patterns):
 source=text(value);values=[]
 for pattern in patterns:
  values.extend(percent_number(match) for match in pattern.findall(source))
 return max((value for value in values if value is not None),default=None)
def rating_pair(score,count):
 score_value=bounded_number(score,0.01,5);count_value=bounded_number(count,1,100000000)
 if score_value is None or count_value is None or not float(count_value).is_integer():return None,None
 return score_value,int(count_value)
def joined_text(value):
 if isinstance(value,dict):return ' '.join(text(item) for item in value.values() if item not in (None,''))
 if isinstance(value,(list,tuple,set)):return ' '.join(joined_text(item) for item in value if item not in (None,''))
 return text(value)
def structured_rating(value):
 candidates=value if isinstance(value,list) else [value]
 for item in candidates:
  if not isinstance(item,dict):continue
  score=item.get('ratingValue') if item.get('ratingValue') not in (None,'') else item.get('rating')
  count=next((item.get(key) for key in ('reviewCount','ratingCount','count') if item.get(key) not in (None,'')),None)
  pair=rating_pair(score,count)
  if pair!=(None,None):return pair
 return None,None
def metadata_text(value):
 if not isinstance(value,dict):return ''
 parts=[]
 for item in value.get('additionalProperty',[]) if isinstance(value.get('additionalProperty'),list) else [value.get('additionalProperty')]:
  if isinstance(item,dict):parts.append(f"{joined_text(item.get('name'))} {joined_text(item.get('value'))}")
 for key in ('category','keywords','material','slogan'):
  if value.get(key) not in (None,''):parts.append(joined_text(value.get(key)))
 return text(' '.join(parts))
def first_percent_from_text(value,patterns):
 source=text(value)
 candidates=[]
 for pattern in patterns:
  for match in pattern.finditer(source):
   parsed=percent_number(match.group(1))
   if parsed is not None:candidates.append((match.start(),parsed))
 return min(candidates,key=lambda item:item[0])[1] if candidates else None
def asset_url(value,base):
 try:parsed=urllib.parse.urlsplit(urllib.parse.urljoin(base,str(value or '')))
 except ValueError:return ''
 if parsed.scheme not in {'http','https'} or not parsed.netloc:return ''
 return urllib.parse.urlunsplit((parsed.scheme.lower(),parsed.netloc.lower(),parsed.path or '/',parsed.query,''))
def target_context(payload,target):
 source=str(payload or '')[:LIMIT].replace('\\/','/')
 try:handle=urllib.parse.unquote(urllib.parse.urlsplit(str(target or '')).path.rstrip('/').split('/')[-1]).casefold()
 except ValueError:handle=''
 if not handle:return source[:240000]
 lowered=source.casefold();positions=[];start=0
 while len(positions)<16:
  index=lowered.find(handle,start)
  if index<0:break
  positions.append(index);start=index+len(handle)
 if not positions:return source[:240000]
 return '\n'.join(source[max(0,index-6000):min(len(source),index+9000)] for index in positions)
def embedded_rating_pair(payload):
 source=str(payload or '')[:500000]
 pairs=(
  re.compile(r'["\'](?:ratingValue|average_rating|averageRating|rating)["\']\s*:\s*["\']?([0-5](?:\.\d+)?)["\']?.{0,500}?["\'](?:reviewCount|ratingCount|review_count|reviews_count)["\']\s*:\s*["\']?(\d{1,8})',re.I|re.S),
  re.compile(r'["\'](?:reviewCount|ratingCount|review_count|reviews_count)["\']\s*:\s*["\']?(\d{1,8})["\']?.{0,500}?["\'](?:ratingValue|average_rating|averageRating|rating)["\']\s*:\s*["\']?([0-5](?:\.\d+)?)',re.I|re.S),
 )
 for index,pattern in enumerate(pairs):
  match=pattern.search(source)
  if match:
   score,count=(match.group(1),match.group(2)) if index==0 else (match.group(2),match.group(1))
   pair=rating_pair(score,count)
   if pair!=(None,None):return pair
 for raw_tag in OPEN_TAG.findall(source):
  attrs={key.casefold():html.unescape(value) for key,value in ATTR.findall(raw_tag)}
  score=next((attrs.get(key) for key in ('data-rating','data-average-rating','data-rating-value') if attrs.get(key)),None)
  count=next((attrs.get(key) for key in ('data-review-count','data-reviews-count','data-rating-count') if attrs.get(key)),None)
  pair=rating_pair(score,count)
  if pair!=(None,None):return pair
 visible=text(source)
 for pattern in (
  re.compile(r'\b([0-5](?:\.\d+)?)\s*(?:out\s+of\s+5|/\s*5|stars?)\b.{0,160}?\b(\d{1,8})\s+(?:customer\s+)?reviews?\b',re.I|re.S),
  re.compile(r'\brated\s+([0-5](?:\.\d+)?)\b.{0,160}?\b(?:based\s+on\s+)?(\d{1,8})\s+(?:customer\s+)?reviews?\b',re.I|re.S),
 ):
  match=pattern.search(visible)
  if match:
   pair=rating_pair(match.group(1),match.group(2))
   if pair!=(None,None):return pair
 return None,None
def explicit_lineage(value):
 source=text(value)
 match=LINEAGE_FIELD.search(source)
 if match:return text(match.group(1))
 for pattern in (
  re.compile(r'\b(indica|sativa)[- ](?:dominant|leaning)(?:[- ]hybrid)?\b',re.I),
  re.compile(r'\bbalanced[- ]hybrid\b',re.I),
 ):
  match=pattern.search(source)
  if match:return text(match.group(0))
 return ''
def explicit_environment(value):
 match=ENVIRONMENT_FIELD.search(text(value))
 return text(match.group(1)) if match else ''
def detail_documents(payload,base,source_id,source_page):
 output=[];seen=set();handle=urllib.parse.unquote(urllib.parse.urlsplit(str(source_page or '')).path.rstrip('/').split('/')[-1]).casefold()
 for match in ANCHOR_FULL.finditer(str(payload or '')[:LIMIT]):
  attrs={key.casefold():html.unescape(value) for key,value in ATTR.findall(match.group('attrs'))}
  href=attrs.get('href','');label=text(f"{match.group('body')} {attrs.get('title','')} {attrs.get('aria-label','')}")
  target=asset_url(href,base);signal=f'{label} {href}'
  if not target:continue
  path=urllib.parse.urlsplit(target).path
  strong=bool(DOCUMENT_SIGNAL.search(signal));file_hint=path.casefold().endswith('.pdf') or bool(DOCUMENT_PATH_SIGNAL.search(path))
  if not strong and not file_hint:continue
  generic=label.casefold().strip() in {'lab results','lab reports','test results'}
  if generic and not file_hint and handle and handle not in target.casefold():continue
  if target in seen:continue
  seen.add(target);kind='terpene' if 'terpene' in signal.casefold() and 'coa' not in signal.casefold() else 'coa'
  output.append({'kind':kind,'url':target,'public_url':target,'mime_type':'application/pdf' if path.casefold().endswith('.pdf') else '', 'scope':'product','source_id':source_id,'vendor_id':source_id,'source_page':asset_url(source_page,base),'label':label,'discovered_label':label,'provenance':{'method':'first_party_product_detail_anchor','source_page':asset_url(source_page,base)}})
  if len(output)>=12:break
 return output
def enrich_detail_rows(rows,payload,target,source_id):
 if not rows:return rows
 context=target_context(payload,target);thca=first_percent_from_text(context,THCA_PATTERNS);delta9=first_percent_from_text(context,DELTA9_PATTERNS);total=first_percent_from_text(context,TOTAL_THC_PATTERNS);score,count=embedded_rating_pair(context);lineage_value=explicit_lineage(context);environment_value=explicit_environment(context);documents=detail_documents(payload,target,source_id,target)
 enriched=[]
 for original in rows:
  row=dict(original)
  if row.get('thca') in (None,'') and thca is not None:row['thca']=thca;row['thca_source_path']=target;row['thca_confidence']='source_exposed_product_detail'
  if row.get('delta9_thc') in (None,'') and delta9 is not None:row['delta9_thc']=delta9;row['delta9_thc_source_path']=target;row['delta9_thc_confidence']='source_exposed_product_detail'
  if row.get('direct_total_thc') in (None,'') and total is not None:row['direct_total_thc']=total;row['total_thc_source_path']=target;row['total_thc_confidence']='source_exposed_product_detail'
  if (row.get('rating') in (None,'') or row.get('review_count') in (None,'')) and score is not None and count is not None:row['rating']=score;row['review_count']=count;row['rating_source_path']=target;row['review_count_source_path']=target
  if row.get('strain_type') in (None,'') and lineage_value:row['strain_type']=lineage_value;row['lineage_source_path']=target
  if row.get('grow_environment') in (None,'') and environment_value:row['grow_environment']=environment_value;row['environment_source_path']=target
  if documents:
   existing=[item for item in row.get('documents',[]) if isinstance(item,dict)];known={str(item.get('url') or item.get('public_url') or '') for item in existing};row['documents']=[*existing,*[item for item in documents if str(item.get('url') or '') not in known]]
  enriched.append(row)
 return enriched
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
def record(sid,vendor,route,name,target,desc='',price=None,stock='',image='',variant='',rating=None,review_count=None,delta9_thc=None,direct_total_thc=None):
 name=text(name);desc=text(desc)[:DESCRIPTION_LIMIT];target=url(target,route[1]);combined=f'{name} {desc}'
 if not name or not target or HARD_EXCLUDE.search(combined) or not FLOWER.search(combined) or not (THCA.search(combined) or 'thca' in route[1].lower()):return None
 ambiguous=AMBIGUOUS_FORM.search(combined)
 if ambiguous and FORM_CONTEXT.search(combined) and not EXPLICIT_FLOWER.search(name):return None
 p=num(price);g,weight_label=weight(combined);thca=percent_from_text(combined,THCA_PATTERNS);delta9=percent_number(delta9_thc) or percent_from_text(combined,DELTA9_PATTERNS);total=percent_number(direct_total_thc) or percent_from_text(combined,TOTAL_THC_PATTERNS);rating_value,review_value=rating_pair(rating,review_count);stock_state=availability(stock)
 stock_method='explicit_boolean' if isinstance(stock,bool) else 'explicit_source_state' if stock_state!='unknown' else 'unknown'
 return {'id':hashlib.sha256(f'{sid}|{target}|{variant}'.encode()).hexdigest()[:24],'source_id':sid,'vendor':vendor,'name':name,'description':desc,'url':target,'image':url(image,route[1]) if image else '', 'price':p,'grams':g,'source_weight_label':weight_label,'weight_provenance':'explicit_text' if weight_label else 'unavailable','price_per_gram':round(p/g,4) if p and g else None,'thca':thca,'delta9_thc':delta9,'direct_total_thc':total,'rating':rating_value,'review_count':review_value,'availability':stock_state,'availability_raw':stock,'availability_normalization':stock_method,'variant':text(variant),'source_type':route[0],'route_url':route[1],'collected_at':now()}
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
  description=f"{item.get('body_html','')} {joined_text(item.get('tags'))} {joined_text(item.get('product_type'))} {joined_text(item.get('vendor'))}"
  rating_value=next((item.get(key) for key in ('average_rating','rating') if item.get(key) not in (None,'')),None);review_value=next((item.get(key) for key in ('review_count','reviews_count','rating_count') if item.get(key) not in (None,'')),None)
  variants=item.get('variants') or [{}]
  for v in variants:
   if not isinstance(v,dict):continue
   vt=text(v.get('title'));name=item.get('title');name=f'{name} {vt}' if vt and vt.lower()!='default title' else name
   r=record_identity(record(sid,vendor,route,name,f"{product_url}?variant={v.get('id')}" if v.get('id') else product_url,description,v.get('price'),v.get('available'),image,vt,rating_value,review_value),item.get('id'),v.get('id'),v.get('compare_at_price'))
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
   p,regular=woo_price(item);images=item.get('images') or [];image=images[0].get('src','') if images and isinstance(images[0],dict) else '';cats=' '.join(text(x.get('name')) for x in item.get('categories',[]) if isinstance(x,dict));tags=' '.join(text(x.get('name')) for x in item.get('tags',[]) if isinstance(x,dict));attrs=' '.join(f"{text(x.get('name'))} {joined_text(x.get('terms') or x.get('value'))}" for x in item.get('attributes',[]) if isinstance(x,dict));desc=f"{item.get('short_description','')} {item.get('description','')} {cats} {tags} {attrs}";r=record_identity(record(sid,vendor,route,item.get('name'),item.get('permalink'),desc,p,item.get('stock_status') or item.get('is_in_stock'),image,'',item.get('average_rating') or item.get('rating'),item.get('review_count') or item.get('rating_count')),item.get('id'),'',regular)
   if r:rows.append(r)
   continue
  for variation in variations:
   stock=variation.get('stock_status') if variation.get('stock_status') not in (None,'') else variation.get('is_in_stock')
   if availability(stock)!='in_stock':reject('variation_not_explicitly_in_stock');continue
   label=woo_variant_label(variation,parent)
   if not label or grams(label) is None:reject('variation_weight_missing');continue
   p,regular=woo_price(variation);parent_name=parent.get('name') or variation.get('name');parent_id=parent.get('id') or variation.get('parent');variation_id=variation.get('id');parent_url=parent.get('permalink') or variation.get('permalink');target=f"{parent_url}{'&' if '?' in str(parent_url) else '?'}variant={variation_id}" if variation_id else parent_url;images=variation.get('images') or parent.get('images') or [];image=images[0].get('src','') if images and isinstance(images[0],dict) else '';cats=' '.join(text(x.get('name')) for x in parent.get('categories',[]) if isinstance(x,dict));tags=' '.join(text(x.get('name')) for x in parent.get('tags',[]) if isinstance(x,dict));attrs=' '.join(f"{text(x.get('name'))} {joined_text(x.get('terms') or x.get('value'))}" for x in parent.get('attributes',[]) if isinstance(x,dict));desc=f"{parent.get('short_description','')} {parent.get('description','')} {variation.get('description','')} {cats} {tags} {attrs}";name=f'{parent_name} {label}';rating_value=variation.get('average_rating') or variation.get('rating') or parent.get('average_rating') or parent.get('rating');review_value=variation.get('review_count') or variation.get('rating_count') or parent.get('review_count') or parent.get('rating_count')
   r=record_identity(record(sid,vendor,route,name,target,desc,p,stock,image,label,rating_value,review_value),parent_id,variation_id,regular)
   if r:rows.append(r)
 return dedupe(rows),diagnostics
def objects(v):
 if isinstance(v,dict):
  yield v
  for k in ('@graph','itemListElement','mainEntity','item','offers','hasVariant'):
   if isinstance(v.get(k),(dict,list)):yield from objects(v[k])
 elif isinstance(v,list):
  for x in v:yield from objects(x)
def _structured_offers(value):
 if isinstance(value,list):
  out=[]
  for item in value:out.extend(_structured_offers(item))
  return out
 if not isinstance(value,dict):return []
 types={str(x).lower() for x in (value.get('@type') if isinstance(value.get('@type'),list) else [value.get('@type')])}
 nested=value.get('offers')
 if 'aggregateoffer' in types and isinstance(nested,(dict,list)):
  expanded=_structured_offers(nested)
  if expanded:return expanded
 return [value]

def _base_product_target(value,base):
 target=url(value,base)
 if not target:return ''
 parsed=urllib.parse.urlsplit(target)
 return urllib.parse.urlunsplit((parsed.scheme,parsed.netloc,parsed.path,'',''))

def _offer_identifier(offer):
 value=offer.get('sku') or offer.get('productID') or offer.get('identifier') or offer.get('@id')
 if isinstance(value,dict):value=value.get('value') or value.get('@value')
 return text(value)

def html_products(payload,sid,vendor,route):
 rows=[]
 for raw in LD.findall(payload):
  try:data=json.loads(html.unescape(raw.strip()))
  except json.JSONDecodeError:continue
  for product in objects(data):
   kind=product.get('@type');types={str(x).lower() for x in (kind if isinstance(kind,list) else [kind])}
   if 'product' not in types:continue
   image=product.get('image');image=image[0] if isinstance(image,list) and image else image;image=(image.get('url') or image.get('contentUrl')) if isinstance(image,dict) else image
   parent_url=product.get('url') or product.get('@id');parent_id=text(product.get('sku') or product.get('productID') or product.get('@id') or parent_url);rating_value,review_value=structured_rating(product.get('aggregateRating'));product_desc=f"{text(product.get('description'))} {metadata_text(product)}".strip()
   offers=_structured_offers(product.get('offers'));package=[]
   for offer in offers:
    label=text(offer.get('name') or offer.get('size') or offer.get('sku'));identity=_offer_identifier(offer);target=offer.get('url') or parent_url
    signal=f"{label} {text(offer.get('description'))} {urllib.parse.unquote(str(target or ''))}";package_grams=grams(signal)
    if package_grams is None or availability(offer.get('availability'))!='in_stock':continue
    if not target and identity and parent_url:target=f"{parent_url}{'&' if '?' in str(parent_url) else '?'}variant={urllib.parse.quote(identity)}"
    offer_host=urllib.parse.urlsplit(url(target,route[1])).netloc;parent_host=urllib.parse.urlsplit(url(parent_url,route[1])).netloc
    if offer_host and parent_host and offer_host!=parent_host:continue
    name=f"{text(product.get('name'))} {label}".strip();desc=f"{product_desc} {text(offer.get('description'))} {metadata_text(offer)}".strip()
    row=record_identity(record(sid,vendor,route,name,target,desc,offer.get('price') or offer.get('lowPrice'),offer.get('availability'),offer.get('image') or image,label,rating_value,review_value),parent_id,identity)
    if row:row['discovery_method']='json_ld_product_offer';package.append(row)
   if package:
    chosen={}
    for row in sorted(package,key=lambda r:(float(r.get('grams') or 0),str(r.get('source_variant_id') or ''),str(r.get('url') or ''))):chosen.setdefault(round(float(row['grams']),4),row)
    rows.extend(chosen.values());continue
   candidates=offers or [{}];selected=min(candidates,key=lambda o:(_offer_identifier(o),str(o.get('url') or '')))
   target=selected.get('url') or parent_url;identity=_offer_identifier(selected)
   row=record_identity(record(sid,vendor,route,product.get('name'),target,f"{product_desc} {metadata_text(selected)}",selected.get('price') or selected.get('lowPrice'),selected.get('availability'),selected.get('image') or image,'',rating_value,review_value),parent_id,identity)
   if row:row['discovery_method']='json_ld_product';rows.append(row)
 return dedupe(rows)

def meta_values(payload):
 values={}
 for raw in META.findall(payload):
  attrs={k.lower():html.unescape(v) for k,v in ATTR.findall(raw)};key=(attrs.get('property') or attrs.get('name') or '').lower();value=attrs.get('content','')
  if key and value:values.setdefault(key,value)
 return values
def html_detail(payload,sid,vendor,route,target):
 rows=html_products(payload,sid,vendor,route)
 if rows:return enrich_detail_rows(rows,payload,target,sid)
 meta=meta_values(payload);title=meta.get('og:title') or meta.get('twitter:title');m=TITLE.search(payload)
 if not title and m:title=text(m.group(1)).split('|')[0].strip()
 desc=meta.get('og:description') or meta.get('description') or '';price=meta.get('product:price:amount') or meta.get('og:price:amount');stock=meta.get('product:availability') or '';image=meta.get('og:image') or meta.get('twitter:image') or '';rating_value=next((meta.get(key) for key in ('product:rating:value','rating','og:rating') if meta.get(key)),None);review_value=next((meta.get(key) for key in ('product:rating:count','review_count','rating_count') if meta.get(key)),None)
 row=record(sid,vendor,route,title,target,desc,price,stock,image,'',rating_value,review_value)
 return enrich_detail_rows([row],payload,target,sid) if row else []
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
 structured=html_products(payload,sid,vendor,route);links=product_links(payload,route)
 covered={_base_product_target(row.get('url'),route[1]) for row in structured if row.get('url')}
 uncovered=[target for target in links if _base_product_target(target,route[1]) not in covered]
 failures={};detail_rows=[]
 for target in uncovered:
  try:detail,ctype,status=fetch(target)
  except Exception as exc:
   reason='timeout_error' if isinstance(exc,TimeoutError) else type(exc).__name__.lower();failures[reason]=failures.get(reason,0)+1;continue
  if status!=200:
   reason=f'http_{status}';failures[reason]=failures.get(reason,0)+1;continue
  if ctype not in {'text/html','application/xhtml+xml'}:
   failures['invalid_content_type']=failures.get('invalid_content_type',0)+1;continue
  found=html_detail(detail,sid,vendor,route,target)
  if not found:failures['detail_without_product']=failures.get('detail_without_product',0)+1
  for row in found:row['discovery_method']=row.get('discovery_method') or 'html_product_detail'
  detail_rows.extend(found)
 diagnostics.update(structured_rows=len(structured),discovered_links=len(links),uncovered_links=len(uncovered),detail_requests=len(uncovered),detail_failures=sum(failures.values()),detail_failure_reasons=dict(sorted(failures.items())),coverage_status='partial' if failures else 'complete')
 return dedupe([*detail_rows,*structured])

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
   else:route_diagnostics={};rows=html_with_details(payload,sid,vendor,route,route_diagnostics)
   rr.update(route_diagnostics);degraded_reasons=[]
   if rr.get('variation_failures'):degraded_reasons.append('woocommerce_variation_incomplete')
   if rr.get('detail_failures'):degraded_reasons.append('html_complementary_discovery_incomplete')
   route_status='degraded' if degraded_reasons else 'healthy' if rows else 'empty';rr.update(status=route_status,products=len(rows),duration_seconds=round(time.monotonic()-t,3));attempts.append(rr)
   if rows:return dedupe(rows),{'source_id':sid,'name':vendor,'enabled':True,'status':route_status,'health_reason_codes':degraded_reasons,'products':len(rows),'routes_attempted':len(attempts),'active_route':route[1],'route_results':attempts,'duration_seconds':round(time.monotonic()-started,3)}
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
