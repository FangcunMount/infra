import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import venv

from published_runtime import interpreter_path


class PublishedRuntimeTest(unittest.TestCase):
    def test_real_symlinked_venv_keeps_its_installed_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = Path(directory)/'installed'
            venv.EnvBuilder(with_pip=False, symlinks=True).create(environment)
            executable = environment/'bin/python'
            self.assertTrue(executable.is_symlink())
            def prefix(path):
                return Path(json.loads(subprocess.check_output(
                    [str(path), '-I', '-c', 'import sys,json;print(json.dumps(sys.prefix))'],
                    text=True))).resolve()
            self.assertNotEqual(prefix(executable.resolve()), environment.resolve())
            self.assertEqual(prefix(interpreter_path(executable)), environment.resolve())
