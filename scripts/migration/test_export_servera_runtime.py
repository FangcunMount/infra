import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from export_servera_runtime import EXPECTED, database_url_at_proxy, escape_interpolation, export_runtime


def fixture():
    return [{
        "Name": "/" + name, "Image": "sha256:" + "a" * 64,
        "Config": {"Env": ["PASSWORD=literal$token", "QS_AI_DATABASE_URL=mysql+asyncmy://u:p%40ss@old:3306/db?charset=utf8mb4"],
                   "Labels": {}, "Healthcheck": {"Test": ["CMD", "true"]}},
        "HostConfig": {"RestartPolicy": {"Name": "unless-stopped"}},
        "Mounts": [{"Type": "bind", "Source": "/data/cert", "Destination": "/run/cert", "RW": False}],
        "NetworkSettings": {"Networks": {"infra-network": {"Aliases": [name]}}},
    } for name in sorted(EXPECTED)]


class ExportTest(unittest.TestCase):
    def test_credentials_and_database_options_survive_host_change(self):
        self.assertEqual(database_url_at_proxy("mysql+asyncmy://u:p%40ss@old:3306/db?charset=utf8mb4"),
                         "mysql+asyncmy://u:p%40ss@mysql-rds-proxy:3306/db?charset=utf8mb4")

    def test_secret_dollars_are_not_interpreted_by_compose(self):
        self.assertEqual(escape_interpolation({"password": "a${HOME}$$b"}), {"password": "a$${HOME}$$$$b"})

    def test_pinned_images_and_bind_mounts_fail_closed(self):
        services = export_runtime(fixture())["services"]
        for service in services.values():
            self.assertEqual(service["pull_policy"], "never")
            self.assertTrue(service["image"].startswith("sha256:"))
            self.assertEqual(service["volumes"][0]["bind"], {"create_host_path": False})
            self.assertTrue(service["volumes"][0]["read_only"])

    def test_changed_scope_or_persistent_volume_needs_review(self):
        with self.assertRaises(ValueError):
            export_runtime(fixture()[:-1])
        containers = copy.deepcopy(fixture())
        containers[0]["Mounts"][0]["Type"] = "volume"
        with self.assertRaises(ValueError):
            export_runtime(containers)

    def test_tmpfs_uses_compose_list_syntax(self):
        containers = fixture()
        next(c for c in containers if c["Name"] == "/qs-ai")["HostConfig"]["Tmpfs"] = {
            "/tmp": "rw,noexec,nosuid,size=64m"
        }
        self.assertEqual(export_runtime(containers)["services"]["qs-ai"]["tmpfs"],
                         ["/tmp:rw,noexec,nosuid,size=64m"])

    @unittest.skipUnless(shutil.which("docker"), "Docker CLI required for Compose roundtrip")
    def test_compose_accepts_export_with_literal_credentials(self):
        containers = fixture()
        next(c for c in containers if c["Name"] == "/qs-ai")["HostConfig"]["Tmpfs"] = {
            "/tmp": "rw,noexec,nosuid,size=64m"
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "compose.json"
            path.write_text(json.dumps(export_runtime(containers)))
            result = subprocess.run(["docker", "compose", "-f", str(path), "config", "--format", "json"],
                                    capture_output=True, text=True, check=True)
            rendered = json.loads(result.stdout)
        for service in rendered["services"].values():
            # `config` retains the escape; Compose unescapes it at container
            # creation. A real synthetic runtime probe is also recorded.
            self.assertEqual(service["environment"]["PASSWORD"], "literal$$token")
        self.assertIn("/tmp:rw,noexec,nosuid,size=64m", rendered["services"]["qs-ai"]["tmpfs"])


if __name__ == "__main__":
    unittest.main()
