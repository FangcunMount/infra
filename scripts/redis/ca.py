#!/usr/bin/env python3
"""Install/verify the pinned public Redis CA; never installs keys or disables TLS."""
import argparse,hashlib,json,os
from pathlib import Path
DEST=Path('/data/infra/ssl/redis/ca-chain.pem')
def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('command',choices=['install','verify']);args=a.parse_args();root=Path(__file__).parents[2];manifest=json.loads((root/'components/redis-client/manifest.json').read_text());source=root/manifest['ca_file'];data=source.read_bytes()
 if b'PRIVATE KEY'in data or hashlib.sha256(data).hexdigest()!=manifest['ca_sha256']:raise ValueError('CA source mismatch')
 if args.command=='install':
  DEST.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
  if DEST.is_symlink():raise ValueError('CA destination may not be a symlink')
  if not DEST.exists():
   with os.fdopen(os.open(DEST,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644),'wb')as f:f.write(data);f.flush();os.fsync(f.fileno())
  if DEST.read_bytes()!=data:raise ValueError('Existing CA differs; review before replacing')
  DEST.chmod(0o644)
 if DEST.is_symlink()or hashlib.sha256(DEST.read_bytes()).hexdigest()!=manifest['ca_sha256']or DEST.stat().st_mode & 0o022:raise ValueError('Installed CA not pinned or writable by others')
 print(json.dumps({'redis_ca':'verified','sha256':manifest['ca_sha256']}))
if __name__=='__main__':
 try:main()
 except Exception as e:print(json.dumps({'redis_ca':'failed','error_type':type(e).__name__}));raise SystemExit(1)from None
