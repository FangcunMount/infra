"""单用户入口的边界测试；所有账户、权限和目录写入均由 shell mock 接管。"""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/00-server/init-user.sh"

HARNESS = r'''
set -euo pipefail
source "$1"
shift
record() { printf '%s\n' "$*" >>"$CALLS"; }
check_root() { :; }
useradd() { record "useradd $*"; return "${CREATE_STATUS:-0}"; }
usermod() { record "usermod $*"; }
install() { record "install $*"; }
chpasswd() { record chpasswd; }
id() {
    if [[ "$1" == -u || "$1" == -g ]]; then
        printf '2001\n'
        return 0
    fi
    [[ "${EXISTING_USER:-false}" == true ]] || [[ -s "$CALLS" ]]
}
getent() {
    if [[ "$2" == "$INIT_USER" ]]; then
        [[ "${EXISTING_GROUP:-false}" == true ]]
    elif [[ "$2" == "${SUDO_GROUP:-sudo}" ]]; then
        printf '%s:x:27:\n' "$2"
    else
        return 2
    fi
}
setup_user_bashrc() { record "bashrc $1"; }
# 避免误执行批量操作；调用其中任意一个都必须使测试失败。
ensure_root_environment() { exit 90; }
setup_deploy_user() { exit 91; }
setup_runtime_user() { exit 92; }
init_user_main "$@"
'''


class InitUserTest(unittest.TestCase):
    def run_init(self, *args, input_text="", **extra_env):
        with tempfile.TemporaryDirectory() as directory:
            calls = Path(directory) / "calls"
            env = dict(os.environ, CALLS=str(calls), **extra_env)
            result = subprocess.run(
                ["bash", "-c", HARNESS, "test", str(SCRIPT), *args],
                input=input_text, text=True, capture_output=True, env=env,
            )
            return result, calls.read_text() if calls.exists() else ""

    def test_normal_user_has_no_privileged_group(self):
        result, calls = self.run_init("--username", "infra_test_user", "--non-interactive")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("useradd -m -U -d /home/infra_test_user -s /bin/bash -- infra_test_user", calls)
        self.assertIn("/home/infra_test_user/workspace", calls)
        self.assertIn("/home/infra_test_user/bin", calls)
        self.assertIn("bashrc infra_test_user", calls)
        self.assertNotIn("usermod", calls)
        self.assertNotIn("chpasswd", calls)
        self.assertNotIn("docker", calls)

    def test_sudo_and_wheel_are_added_only_when_requested(self):
        for group in ("sudo", "wheel"):
            with self.subTest(group=group):
                result, calls = self.run_init(
                    "--username", "infra_test_user", "--sudo", "--non-interactive",
                    SUDO_GROUP=group,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"usermod -aG {group} infra_test_user", calls)

    def test_invalid_arguments_cannot_mutate_accounts(self):
        for args in ((), ("--username",), ("--username", "../root"),
                     ("--username", "-root"), ("--username", "a" * 33),
                     ("--username", "alice", "--unknown")):
            with self.subTest(args=args):
                result, calls = self.run_init(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, "")

    def test_existing_accounts_groups_and_missing_admin_group_fail_before_creation(self):
        for env in ({"EXISTING_USER": "true"}, {"EXISTING_GROUP": "true"},
                    {"SUDO_GROUP": "missing"}):
            with self.subTest(env=env):
                result, calls = self.run_init(
                    "--username", "infra_test_user", "--sudo", "--non-interactive", **env,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, "")

    def test_declining_confirmation_leaves_accounts_untouched(self):
        result, calls = self.run_init("--username", "infra_test_user", input_text="n\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, "")

    def test_creation_failure_stops_setup(self):
        result, calls = self.run_init(
            "--username", "infra_test_user", "--sudo", "--non-interactive", CREATE_STATUS="9",
        )
        self.assertEqual(result.returncode, 9)
        self.assertEqual(len(calls.splitlines()), 1)

    def test_make_alias_and_options(self):
        for target in ("init-user", "server-init-user"):
            result = subprocess.run(
                ["make", "-n", target, "USERNAME=alice", "INIT_USER_ARGS=--sudo --non-interactive"],
                cwd=ROOT, text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('init-user.sh --username "alice" --sudo --non-interactive', result.stdout)

    def test_make_missing_username_fails_without_sudo(self):
        result = subprocess.run(
            ["make", "init-user", "USERNAME="], cwd=ROOT, text=True, capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("请提供 USERNAME", result.stdout)

    def test_both_scripts_offer_help_without_initialization(self):
        for name in ("init-user.sh", "init-users.sh"):
            result = subprocess.run(
                ["bash", str(SCRIPT.with_name(name)), "--help"], text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("用法:", result.stdout)


if __name__ == "__main__":
    unittest.main()
