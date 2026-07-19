from pathlib import Path
import re

p=Path('scripts/catalog_v4/builder.py');t=p.read_text()
t=t.replace('TOTAL_THC_FACTOR = Decimal("0.877")\n','TOTAL_THC_FACTOR = Decimal("0.877")\nMAX_MANIFEST_BYTES=512*1024\nMAX_INDEX_BYTES=24*1024*1024\nMAX_DETAIL_BYTES=2*1024*1024\nMAX_PHYSICAL_DETAIL_SHARDS=4096\n',1)
helper='''\n\ndef _detail_record(p):
 return {k:p[k] for k in ("product_id","vendor_id","strain_name","source_title","canonical_product_url","image_url","effects","grow_environment","total_thc","lineage_provenance","effects_provenance","environment_provenance","rating_provenance","variants","provenance")}

def _detail_payload(shard,rows,generation_id,stamp):
 rows=sorted(rows,key=lambda r:r["product_id"])
 return {"schema_version":DETAIL_SCHEMA_VERSION,"generation_id":generation_id,"generated_at":stamp,"shard":shard,"product_count":len(rows),"products":rows}

def _partition_details(rows,minimum,generation_id,stamp):
 buckets=[[] for _ in range(minimum)];segments={i:[i] for i in range(minimum)};assignment={}
 for row in sorted(rows,key=lambda r:r["product_id"]):
  preferred=int(row["product_id"][:8],16)%minimum;shard=segments[preferred][-1];candidate=[*buckets[shard],row]
  if len(_json_bytes(_detail_payload(shard,candidate,generation_id,stamp)))<=MAX_DETAIL_BYTES:
   buckets[shard]=candidate;assignment[row["product_id"]]=shard;continue
  shard=len(buckets)
  if shard>=MAX_PHYSICAL_DETAIL_SHARDS:raise ValueError("detail shard count exceeds deterministic publication limit")
  encoded=_json_bytes(_detail_payload(shard,[row],generation_id,stamp))
  if len(encoded)>MAX_DETAIL_BYTES:raise ValueError(f"single detail product {row['product_id']} exceeds {MAX_DETAIL_BYTES} byte browser limit ({len(encoded)} bytes)")
  buckets.append([row]);segments[preferred].append(shard);assignment[row["product_id"]]=shard
 encoded={i:_json_bytes(_detail_payload(i,b,generation_id,stamp)) for i,b in enumerate(buckets)}
 if any(len(v)>MAX_DETAIL_BYTES for v in encoded.values()):raise ValueError("detail shard byte budget exceeded after partitioning")
 return buckets,encoded,assignment
'''
t=t.replace('\n\nclass CatalogBuilder:\n',helper+'\n\nclass CatalogBuilder:\n',1)
start=t.index('        generation_basis = {');end=t.index('        index = {',start)
block='''        stamp = _timestamp(generated_at)
        detail_products = [_detail_record(product) for product in products]
        preview, _, _ = _partition_details(detail_products, self.detail_shards, "0" * 32, stamp)
        effective_detail_shards = len(preview)
        generation_basis = {"schema_version": SCHEMA_VERSION, "products": products, "vendors": vendor_payload["vendors"], "detail_shards": effective_detail_shards, "detail_byte_limit": MAX_DETAIL_BYTES}
        generation_id = _sha(_canonical_bytes(generation_basis))[:32]
        detail_buckets, detail_bytes, detail_assignment = _partition_details(detail_products, self.detail_shards, generation_id, stamp)
        if len(detail_buckets) != effective_detail_shards: raise ValueError("detail shard partition changed after generation identity binding")
        index_products = []
        for product in products:
            shard = detail_assignment[product["product_id"]]
            default_variant = select_active_variant(product["variants"])
            index_products.append({"product_id":product["product_id"],"default_variant_id":default_variant["variant_id"] if default_variant else None,"detail_shard":shard,"vendor_id":product["vendor_id"],"vendor_name":product["vendor_name"],"vendor_favicon_url":product["vendor_favicon_url"],"strain_name":product["strain_name"],"lineage":product["lineage"],"total_thc_display_percent":product["total_thc"]["display_percent"],"rating":product["rating"],"review_count":product["review_count"],"search":product["search"],"variants":[{"variant_id":v["variant_id"],"grams":v["grams"],"source_weight_label":v["source_weight_label"],"current_price":v["current_price"],"original_price":v["original_price"],"discount_percent":v["discount_percent"],"price_per_gram":v["price_per_gram"],"product_url":v["variant_url"],"in_stock":True} for v in product["variants"]]})

'''
t=t[:start]+block+t[end:]
pat=re.compile(r'        detail_entries: list\[dict\[str, Any\]\] = \[\]\n        for shard in range\(self\.detail_shards\):.*?detail_entries\.append\([^\n]+\)',re.S)
new='''        detail_entries = []
        for shard, payload_bytes in sorted(detail_bytes.items()):
            path=f"catalog-v4/details/{shard:03d}.json";files[path]=payload_bytes
            detail_entries.append({"path":f"data/{path}","sha256":_sha(payload_bytes),"bytes":len(payload_bytes),"product_count":len(detail_buckets[shard])})'''
t,n=pat.subn(new,t,1)
if n!=1:raise SystemExit(f'detail loop {n}')
t=t.replace('"sha256": _sha(files["catalog-v4/index.json"]),\n            }','"sha256": _sha(files["catalog-v4/index.json"]),\n                "bytes": len(files["catalog-v4/index.json"]),\n            }',1)
t=t.replace('"sha256": _sha(files["catalog-v4/vendors.json"]),\n            }','"sha256": _sha(files["catalog-v4/vendors.json"]),\n                "bytes": len(files["catalog-v4/vendors.json"]),\n            }',1)
t=t.replace('"sha256": _sha(files["catalog-v4/rejections.json"]),\n                "count"','"sha256": _sha(files["catalog-v4/rejections.json"]),\n                "bytes": len(files["catalog-v4/rejections.json"]),\n                "count"',1)
t=t.replace('            "compatibility": {','            "asset_limits":{"schema_version":"dropfinder-asset-limits-v1","manifest_bytes":MAX_MANIFEST_BYTES,"compact_index_bytes":MAX_INDEX_BYTES,"detail_shard_bytes":MAX_DETAIL_BYTES},\n            "compatibility": {',1)
t=t.replace('        files["catalog-v4/manifest.json"] = _json_bytes(manifest)','        if len(files["catalog-v4/index.json"])>MAX_INDEX_BYTES:raise ValueError("compact index exceeds browser byte limit")\n        files["catalog-v4/manifest.json"] = _json_bytes(manifest)\n        if len(files["catalog-v4/manifest.json"])>MAX_MANIFEST_BYTES:raise ValueError("manifest exceeds browser byte limit")',1)
p.write_text(t)
