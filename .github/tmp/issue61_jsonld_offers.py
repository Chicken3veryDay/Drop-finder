from pathlib import Path
import re

p=Path('scripts/cloud_scan.py');t=p.read_text()
pattern=re.compile(r'^def html_products\(.*?(?=^def meta_values\()',re.M|re.S)
new='''def _structured_offers(value):
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
   parent_url=product.get('url') or product.get('@id');parent_id=text(product.get('sku') or product.get('productID') or product.get('@id') or parent_url)
   offers=_structured_offers(product.get('offers'));package=[]
   for offer in offers:
    label=text(offer.get('name') or offer.get('size') or offer.get('sku'));identity=_offer_identifier(offer);target=offer.get('url') or parent_url
    signal=f"{label} {text(offer.get('description'))} {urllib.parse.unquote(str(target or ''))}";package_grams=grams(signal)
    if package_grams is None or availability(offer.get('availability'))!='in_stock':continue
    if not target and identity and parent_url:target=f"{parent_url}{'&' if '?' in str(parent_url) else '?'}variant={urllib.parse.quote(identity)}"
    offer_host=urllib.parse.urlsplit(url(target,route[1])).netloc;parent_host=urllib.parse.urlsplit(url(parent_url,route[1])).netloc
    if offer_host and parent_host and offer_host!=parent_host:continue
    name=f"{text(product.get('name'))} {label}".strip();desc=f"{text(product.get('description'))} {text(offer.get('description'))}".strip()
    row=record_identity(record(sid,vendor,route,name,target,desc,offer.get('price') or offer.get('lowPrice'),offer.get('availability'),offer.get('image') or image,label),parent_id,identity)
    if row:row['discovery_method']='json_ld_product_offer';package.append(row)
   if package:
    chosen={}
    for row in sorted(package,key=lambda r:(float(r.get('grams') or 0),str(r.get('source_variant_id') or ''),str(r.get('url') or ''))):chosen.setdefault(round(float(row['grams']),4),row)
    rows.extend(chosen.values());continue
   candidates=offers or [{}];selected=min(candidates,key=lambda o:(_offer_identifier(o),str(o.get('url') or '')))
   target=selected.get('url') or parent_url;identity=_offer_identifier(selected)
   row=record_identity(record(sid,vendor,route,product.get('name'),target,product.get('description'),selected.get('price') or selected.get('lowPrice'),selected.get('availability'),selected.get('image') or image,''),parent_id,identity)
   if row:row['discovery_method']='json_ld_product';rows.append(row)
 return dedupe(rows)
'''
t,count=pattern.subn(new+'\n',t,1)
if count!=1:raise SystemExit(f'html_products replacements: {count}')
p.write_text(t)
