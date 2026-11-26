import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('sources', Path(__file__).parents[1] / 'prepare-ai-log-source.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def item(name, identity='a'*64):
    return {'Name':name, 'Id':identity, 'HostConfig':{'LogConfig':{'Type':'json-file'}},
            'LogPath':f'/var/lib/docker/containers/{identity}/{identity}-json.log'}

class SourceTests(unittest.TestCase):
    def test_exact_allowlist(self):
        rows=[item('/qs-ai'),item('/qs-ai-m5-restore-mysql'),item('/qs-apiserver-other')]
        self.assertEqual(module.paths_for(rows), ['/logs/'+ 'a'*64+'/'+ 'a'*64+'-json.log*'])
    def test_missing_sources_fail_closed(self):
        with self.assertRaises(ValueError): module.paths_for([item('/other')])
    def test_nonstandard_path_rejected(self):
        row=item('/qs-ai');row['LogPath']='/secret'
        with self.assertRaises(ValueError): module.paths_for([row])
    def test_driver_rejected(self):
        row=item('/qs-ai');row['HostConfig']['LogConfig']['Type']='local'
        with self.assertRaises(ValueError): module.paths_for([row])

if __name__ == '__main__': unittest.main()
