from pathlib import Path

path = Path("scripts/cloud_scan.py")
text = path.read_text(encoding="utf-8")


def replace_between(start_marker: str, end_marker: str, replacement: str) -> None:
    global text
    start = text.find(start_marker)
    if start < 0:
        raise SystemExit(f"missing start marker: {start_marker}")
    end = text.find(end_marker, start)
    if end < 0:
        raise SystemExit(f"missing end marker: {end_marker}")
    text = text[:start] + replacement.rstrip() + "\n" + text[end:]


replace_between(
    "def html_products(payload,sid,vendor,route):",
    "def meta_values(payload):",
    '''def product_identity(target):
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
''',
)

replace_between(
    "def html_with_details(payload,sid,vendor,route):",
    "def dedupe(rows):",
    '''def html_with_details(payload,sid,vendor,route,diagnostics=None):
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
''',
)

old = """    if route[0]=='shopify':rows=shopify(payload,sid,vendor,route);route_diagnostics={}
    elif route[0]=='woo':rows,route_diagnostics=woo(payload,sid,vendor,route)
    else:rows=html_with_details(payload,sid,vendor,route);route_diagnostics={}
    rr.update(route_diagnostics);route_status='degraded' if rr.get('variation_failures') else 'healthy' if rows else 'empty';rr.update(status=route_status,products=len(rows),duration_seconds=round(time.monotonic()-t,3));attempts.append(rr)
    if rows:return dedupe(rows),{'source_id':sid,'name':vendor,'enabled':True,'status':route_status,'health_reason_codes':['woocommerce_variation_incomplete'] if route_status=='degraded' else [],'products':len(rows),'routes_attempted':len(attempts),'active_route':route[1],'route_results':attempts,'duration_seconds':round(time.monotonic()-started,3)}"""
new = """    if route[0]=='shopify':rows=shopify(payload,sid,vendor,route);route_diagnostics={}
    elif route[0]=='woo':rows,route_diagnostics=woo(payload,sid,vendor,route)
    else:
     route_diagnostics={};rows=html_with_details(payload,sid,vendor,route,route_diagnostics)
    rr.update(route_diagnostics);health_reason_codes=[]
    if rr.get('variation_failures'):health_reason_codes.append('woocommerce_variation_incomplete')
    if rr.get('detail_failures'):health_reason_codes.append('html_detail_discovery_incomplete')
    route_status='degraded' if health_reason_codes else 'healthy' if rows else 'empty';rr.update(status=route_status,health_reason_codes=health_reason_codes,products=len(rows),duration_seconds=round(time.monotonic()-t,3));attempts.append(rr)
    if rows:return dedupe(rows),{'source_id':sid,'name':vendor,'enabled':True,'status':route_status,'health_reason_codes':health_reason_codes,'products':len(rows),'routes_attempted':len(attempts),'active_route':route[1],'route_results':attempts,'duration_seconds':round(time.monotonic()-started,3)}"""
if text.count(old) != 1:
    raise SystemExit(f"scan routing replacements: {text.count(old)}")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
