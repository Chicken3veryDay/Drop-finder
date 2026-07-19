from pathlib import Path
import re

p=Path('scripts/cloud_scan.py');t=p.read_text()
pattern=re.compile(r'^def html_with_details\(.*?(?=^def dedupe\()',re.M|re.S)
new='''def html_with_details(payload,sid,vendor,route,diagnostics=None):
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
'''
t,count=pattern.subn(new+'\n',t,1)
if count!=1:raise SystemExit(f'html_with_details replacements: {count}')
old="""   else:rows=html_with_details(payload,sid,vendor,route);route_diagnostics={}
   rr.update(route_diagnostics);route_status='degraded' if rr.get('variation_failures') else 'healthy' if rows else 'empty';rr.update(status=route_status,products=len(rows),duration_seconds=round(time.monotonic()-t,3));attempts.append(rr)
   if rows:return dedupe(rows),{'source_id':sid,'name':vendor,'enabled':True,'status':route_status,'health_reason_codes':['woocommerce_variation_incomplete'] if route_status=='degraded' else [],'products':len(rows),'routes_attempted':len(attempts),'active_route':route[1],'route_results':attempts,'duration_seconds':round(time.monotonic()-started,3)}
"""
new_scan="""   else:route_diagnostics={};rows=html_with_details(payload,sid,vendor,route,route_diagnostics)
   rr.update(route_diagnostics);degraded_reasons=[]
   if rr.get('variation_failures'):degraded_reasons.append('woocommerce_variation_incomplete')
   if rr.get('detail_failures'):degraded_reasons.append('html_complementary_discovery_incomplete')
   route_status='degraded' if degraded_reasons else 'healthy' if rows else 'empty';rr.update(status=route_status,products=len(rows),duration_seconds=round(time.monotonic()-t,3));attempts.append(rr)
   if rows:return dedupe(rows),{'source_id':sid,'name':vendor,'enabled':True,'status':route_status,'health_reason_codes':degraded_reasons,'products':len(rows),'routes_attempted':len(attempts),'active_route':route[1],'route_results':attempts,'duration_seconds':round(time.monotonic()-started,3)}
"""
if t.count(old)!=1:raise SystemExit(f'scan block count {t.count(old)}')
t=t.replace(old,new_scan,1)
p.write_text(t)
