from pathlib import Path

path = Path("scripts/cloud_scan.py")
text = path.read_text(encoding="utf-8")
replacements = [
    (
        "    rows=shopify(payload,sid,vendor,route) if route[0]=='shopify' else woo(payload,sid,vendor,route) if route[0]=='woo' else html_with_details(payload,sid,vendor,route)\n",
        "    if route[0]=='shopify':rows=shopify(payload,sid,vendor,route);route_diagnostics={}\n"
        "    elif route[0]=='woo':rows,route_diagnostics=woo(payload,sid,vendor,route)\n"
        "    else:rows=html_with_details(payload,sid,vendor,route);route_diagnostics={}\n",
    ),
    (
        "    rr.update(status='healthy' if rows else 'empty',products=len(rows),duration_seconds=round(time.monotonic()-t,3));attempts.append(rr)\n",
        "    rr.update(route_diagnostics);route_status='degraded' if rr.get('variation_failures') else 'healthy' if rows else 'empty';rr.update(status=route_status,products=len(rows),duration_seconds=round(time.monotonic()-t,3));attempts.append(rr)\n",
    ),
    (
        "    if rows:return dedupe(rows),{'source_id':sid,'name':vendor,'enabled':True,'status':'healthy','products':len(rows),'routes_attempted':len(attempts),'active_route':route[1],'route_results':attempts,'duration_seconds':round(time.monotonic()-started,3)}\n",
        "    if rows:return dedupe(rows),{'source_id':sid,'name':vendor,'enabled':True,'status':route_status,'health_reason_codes':['woocommerce_variation_incomplete'] if route_status=='degraded' else [],'products':len(rows),'routes_attempted':len(attempts),'active_route':route[1],'route_results':attempts,'duration_seconds':round(time.monotonic()-started,3)}\n",
    ),
]
for old, new in replacements:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one scan-router anchor, found {count}: {old[:100]!r}")
    text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
