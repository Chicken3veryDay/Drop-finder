from pathlib import Path

path = Path("scripts/cloud_scan.py")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one compatibility anchor, found {count}: {old[:120]!r}")
    text = text.replace(old, new, 1)


extended_record = "def record(sid,vendor,route,name,target,desc='',price=None,stock='',image='',variant='',source_product_id='',source_variant_id='',regular_price=None):\n name=text(name);desc=text(desc);target=url(target,route[1]);combined=f'{name} {desc}'\n if not name or not target or HARD_EXCLUDE.search(combined) or not FLOWER.search(combined) or not (THCA.search(combined) or 'thca' in route[1].lower()):return None\n ambiguous=AMBIGUOUS_FORM.search(combined)\n if ambiguous and FORM_CONTEXT.search(combined) and not EXPLICIT_FLOWER.search(name):return None\n p=num(price);regular=num(regular_price);g,weight_label=weight(combined);pots=[num(x) for x in POTENCY.findall(combined)];pot=max([x for x in pots if x and x<=100],default=None);stock_state=availability(stock)\n stock_method='explicit_boolean' if isinstance(stock,bool) else 'explicit_source_state' if stock_state!='unknown' else 'unknown'\n return {'id':hashlib.sha256(f'{sid}|{target}|{source_variant_id or variant}'.encode()).hexdigest()[:24],'source_id':sid,'vendor':vendor,'name':name,'url':target,'image':url(image,route[1]) if image else '', 'price':p,'original_price':regular if regular and p and regular>p else None,'grams':g,'source_weight_label':weight_label,'weight_provenance':'explicit_text' if weight_label else 'unavailable','price_per_gram':round(p/g,4) if p and g else None,'thca':pot,'availability':stock_state,'availability_raw':stock,'availability_normalization':stock_method,'variant':text(variant),'source_product_id':text(source_product_id),'source_variant_id':text(source_variant_id),'source_type':route[0],'route_url':route[1],'collected_at':now()}\n"
original_record = "def record(sid,vendor,route,name,target,desc='',price=None,stock='',image='',variant=''):\n name=text(name);desc=text(desc);target=url(target,route[1]);combined=f'{name} {desc}'\n if not name or not target or HARD_EXCLUDE.search(combined) or not FLOWER.search(combined) or not (THCA.search(combined) or 'thca' in route[1].lower()):return None\n ambiguous=AMBIGUOUS_FORM.search(combined)\n if ambiguous and FORM_CONTEXT.search(combined) and not EXPLICIT_FLOWER.search(name):return None\n p=num(price);g,weight_label=weight(combined);pots=[num(x) for x in POTENCY.findall(combined)];pot=max([x for x in pots if x and x<=100],default=None);stock_state=availability(stock)\n stock_method='explicit_boolean' if isinstance(stock,bool) else 'explicit_source_state' if stock_state!='unknown' else 'unknown'\n return {'id':hashlib.sha256(f'{sid}|{target}|{variant}'.encode()).hexdigest()[:24],'source_id':sid,'vendor':vendor,'name':name,'url':target,'image':url(image,route[1]) if image else '', 'price':p,'grams':g,'source_weight_label':weight_label,'weight_provenance':'explicit_text' if weight_label else 'unavailable','price_per_gram':round(p/g,4) if p and g else None,'thca':pot,'availability':stock_state,'availability_raw':stock,'availability_normalization':stock_method,'variant':text(variant),'source_type':route[0],'route_url':route[1],'collected_at':now()}\n"
replace_once(extended_record, original_record)

replace_once(
    "def shopify(payload,sid,vendor,route):\n",
    "def record_identity(row,source_product_id='',source_variant_id='',regular_price=None):\n if not row:return None\n row=dict(row);row['source_product_id']=text(source_product_id);row['source_variant_id']=text(source_variant_id);regular=num(regular_price);current=num(row.get('price'));row['original_price']=regular if regular and current and regular>current else None\n if source_variant_id:row['id']=hashlib.sha256(f\"{row.get('source_id')}|{row.get('url')}|{source_variant_id}\".encode()).hexdigest()[:24]\n return row\ndef shopify(payload,sid,vendor,route):\n",
)
replace_once(
    "   r=record(sid,vendor,route,name,f\"{product_url}?variant={v.get('id')}\" if v.get('id') else product_url,item.get('body_html',''),v.get('price'),v.get('available'),image,vt,item.get('id'),v.get('id'),v.get('compare_at_price'))\n",
    "   r=record_identity(record(sid,vendor,route,name,f\"{product_url}?variant={v.get('id')}\" if v.get('id') else product_url,item.get('body_html',''),v.get('price'),v.get('available'),image,vt),item.get('id'),v.get('id'),v.get('compare_at_price'))\n",
)
replace_once(
    "r=record(sid,vendor,route,item.get('name'),item.get('permalink'),f\"{item.get('short_description','')} {item.get('description','')} {cats}\",p,item.get('stock_status') or item.get('is_in_stock'),image,'',item.get('id'),' ',regular)",
    "r=record_identity(record(sid,vendor,route,item.get('name'),item.get('permalink'),f\"{item.get('short_description','')} {item.get('description','')} {cats}\",p,item.get('stock_status') or item.get('is_in_stock'),image,''),item.get('id'),'',regular)",
)
replace_once(
    "r=record(sid,vendor,route,name,target,desc,p,stock,image,label,parent_id,variation_id,regular)",
    "r=record_identity(record(sid,vendor,route,name,target,desc,p,stock,image,label),parent_id,variation_id,regular)",
)

path.write_text(text, encoding="utf-8")
