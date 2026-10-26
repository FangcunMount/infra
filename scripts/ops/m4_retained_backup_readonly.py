import sys,json,hashlib,stat,tarfile,datetime
from pathlib import Path
a=json.load(sys.stdin);rows=[]
for host,row in a['verified_mini_copies'].items():
 p=Path.home()/row['location'];s=p.lstat();assert p.is_file()and not p.is_symlink()and stat.S_IMODE(s.st_mode)==0o600 and s.st_size==row['mini_copy']['bytes']
 h=hashlib.sha256()
 with p.open('rb')as f:
  for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
 assert h.hexdigest()==row['mini_copy']['sha256']==row['source']['sha256']
 members=regular=read_bytes=0
 with tarfile.open(p,'r|gz')as archive:
  for member in archive:
   members+=1
   if member.isfile():
    regular+=1;f=archive.extractfile(member);assert f is not None
    total=0
    for chunk in iter(lambda:f.read(1048576),b''):total+=len(chunk)
    assert total==member.size;read_bytes+=total
 assert regular>0
 after=p.stat();assert s.st_ino==after.st_ino and s.st_size==after.st_size and s.st_mtime_ns==after.st_mtime_ns
 rows.append(dict(host=host,location=row['location'],bytes=s.st_size,sha256=h.hexdigest(),mode='0600',archive_members=members,regular_files=regular,readable_payload_bytes=read_bytes,extracted=False,original_digest_matches=True))
print(json.dumps(dict(schema='m4-c07-backup-readability/v1',checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),copies=rows,read_only=True,extracted=False,production_changed=False,restore_authorized=False)))
