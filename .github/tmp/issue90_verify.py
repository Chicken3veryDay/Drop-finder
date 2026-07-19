from pathlib import Path

p=Path('scripts/catalog_v4/verify.py');t=p.read_text()
t=t.replace('class VerificationError(RuntimeError):','MAX_MANIFEST_BYTES=512*1024\nMAX_INDEX_BYTES=24*1024*1024\nMAX_DETAIL_BYTES=2*1024*1024\n\n\nclass VerificationError(RuntimeError):',1)
t=t.replace('def _resolve_data_path(output_root: Path, declared: str) -> Path:','''def _verify_bytes(path:Path,meta:dict[str,Any],*,label:str,maximum:int|None=None,required:bool=False)->int:
    actual=path.stat().st_size;declared=meta.get("bytes")
    if required and (not isinstance(declared,int) or declared<0):raise VerificationError(f"{label} missing declared bytes: {path}")
    if declared is not None and declared!=actual:raise VerificationError(f"{label} byte count mismatch: {path}")
    if maximum is not None and actual>maximum:raise VerificationError(f"{label} exceeds browser byte limit: {path}")
    return actual


def _resolve_data_path(output_root: Path, declared: str) -> Path:''',1)
t=t.replace('    manifest = _load(manifest_path)','    _verify_bytes(manifest_path,{},label="manifest",maximum=MAX_MANIFEST_BYTES)\n    manifest = _load(manifest_path)',1)
t=t.replace('    index_path = _resolve_data_path(output_root, str(index_meta.get("path") or ""))','''    index_path = _resolve_data_path(output_root, str(index_meta.get("path") or ""))
    size_contract=manifest.get("asset_limits") or {};required=size_contract.get("schema_version")=="dropfinder-asset-limits-v1"
    _verify_bytes(index_path,index_meta,label="compact index",maximum=MAX_INDEX_BYTES,required=required)''',1)
t=t.replace('    vendors_path = _resolve_data_path(output_root, str(vendors_meta.get("path") or ""))','    vendors_path = _resolve_data_path(output_root, str(vendors_meta.get("path") or ""))\n    _verify_bytes(vendors_path,vendors_meta,label="vendor profile",required=required)',1)
t=t.replace('    rejections_path = _resolve_data_path(output_root, str(rejections_meta.get("path") or ""))','    rejections_path = _resolve_data_path(output_root, str(rejections_meta.get("path") or ""))\n    _verify_bytes(rejections_path,rejections_meta,label="rejections",required=required)',1)
t=t.replace('        path = _resolve_data_path(output_root, str(entry.get("path") or ""))','        path = _resolve_data_path(output_root, str(entry.get("path") or ""))\n        _verify_bytes(path,entry,label="detail shard",maximum=MAX_DETAIL_BYTES,required=required)',1)
p.write_text(t)
