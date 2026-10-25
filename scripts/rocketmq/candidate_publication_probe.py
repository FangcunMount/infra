"""GitHub-hosted loopback registry transport test; never reads production credentials."""
import io
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tarfile
import tempfile
import time
import urllib.request

from final_image_candidate import ci_guard, saved_config
from publish_candidates import Registry, command, require


def main():
    ci_guard(os.environ)
    context = json.loads(command(['docker','context','inspect']))
    require(context[0]['Endpoints']['docker']['Host']=='unix:///var/run/docker.sock','owned_local_daemon_required')
    before = command(['docker','ps','-aq']).split()
    name = 'm3-publication-probe-' + secrets.token_hex(6)
    with socket.socket() as server:
        server.bind(('127.0.0.1',0));port=server.getsockname()[1]
    repository = f'127.0.0.1:{port}/owned/probe'
    report = dict(production=False, production_credentials_used=False, passed=0, failed=1, skipped=0)
    try:
        command(['docker','run','-d','--name',name,'--memory','128m','--cpus','0.25',
                 '-p',f'127.0.0.1:{port}:5000','registry:2.8.3'])
        for _ in range(30):
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/v2/',timeout=2) as response:
                    require(response.status==200,'owned_registry_unavailable')
                break
            except OSError: time.sleep(1)
        else: raise ValueError('owned_registry_ready_timeout')
        with tempfile.TemporaryDirectory(prefix='m3-publish-probe-') as temp:
            directory=Path(temp);auth=directory/'auth.json';auth.write_text('{"auths":{}}');auth.chmod(0o600)
            archive=directory/'probe.tar.gz';tag='m3-final-probe:0123456789ab'
            config=json.dumps(dict(os='linux',architecture='amd64',config=dict(User='2000'),
                rootfs=dict(type='layers',diff_ids=[]))).encode()
            manifest=json.dumps([dict(Config='config.json',RepoTags=[tag],Layers=[])]).encode()
            with tarfile.open(archive,'w:gz') as output:
                for path,raw in (('manifest.json',manifest),('config.json',config)):
                    entry=tarfile.TarInfo(path);entry.size=len(raw);output.addfile(entry,io.BytesIO(raw))
            config_id=saved_config(archive,tag)[0]
            backend=Registry(auth,tls=False)
            backend.copy(archive,repository+':seed')
            require(backend.tags(repository)==['seed'],'actual_authenticated_tag_list_required')
            backend.copy(archive,repository+':candidate')
            reference=backend.verify(repository+':candidate',config_id)
            require('@sha256:' in reference,'actual_immutable_digest_required')
            try:backend.verify(repository+':candidate','sha256:'+'0'*64)
            except ValueError: pass
            else: raise ValueError('wrong_config_not_rejected')
            report.update(passed=4,failed=0,config_id=config_id,reference=reference,
                          compressed_archive_transport_verified=True,application_started=False)
    finally:
        subprocess.run(['docker','rm','-f',name],capture_output=True,check=False)
        report['cleanup']={'owned_container_absent':name not in command(['docker','ps','-a','--format','{{.Names}}']).decode().split(),
                           'existing_containers_unchanged':sorted(before)==sorted(command(['docker','ps','-aq']).split())}
        Path('candidate-publication-probe.json').write_text(json.dumps(report,indent=2)+'\n')
    require(all(report['cleanup'].values()),'owned_probe_cleanup_incomplete')


if __name__=='__main__': main()
