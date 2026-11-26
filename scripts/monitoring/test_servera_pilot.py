import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


SOURCE = Path(__file__).resolve().parents[2] / "deploy/serverA/monitoring-pilot/pilot.sh"


class ServerAPilotTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.log = self.root / "events"
        self.state = self.root / "state"
        self.script = self.root / "pilot.sh"
        self.script.write_text(SOURCE.read_text().replace(
            "/run/lock/qlume-servera-monitoring-pilot.lock", str(self.root / "pilot.lock"),
        ))
        self.env = {
            **os.environ, "PATH": f"{self.root}:{os.environ['PATH']}", "PILOT_LOG": str(self.log),
            "PILOT_STATE": str(self.state), "PILOT_FAILURE": "",
        }
        self.command("date", '''
            case "$*" in
                --date=*) echo 1000 ;;
                *)
                    if [[ "$PILOT_FAILURE" == deadline && -f "$PILOT_STATE" ]]; then
                        echo 1000
                    else
                        echo 900
                    fi
                    ;;
            esac
        ''')
        self.command("python3", 'printf "discover\n" >> "$PILOT_LOG"')
        self.command("systemd-run", '''
            printf 'systemd-run %s\n' "$*" >> "$PILOT_LOG"
            case "$*" in
                *pilot-expire*) touch "$PILOT_STATE.timer" ;;
                *pilot-refresh*) [[ "$PILOT_FAILURE" != refresh ]] ;;
            esac
        ''')
        self.command("systemctl", '''
            printf 'systemctl %s\n' "$*" >> "$PILOT_LOG"
            case "$*" in
                'is-active --quiet '*-expire.timer) [[ -f "$PILOT_STATE.timer" ]] ;;
                'is-active --quiet '*) exit 1 ;;
                'stop '*-expire.timer)
                    [[ -f "$PILOT_STATE.timer" ]] || exit 1
                    rm -f "$PILOT_STATE.timer"
                    ;;
                'stop '*-refresh.service) [[ "$PILOT_FAILURE" != service-stop ]] ;;
                'show '*-refresh.service) echo loaded ;;
                'show '*-expire.timer) echo not-found ;;
            esac
        ''')
        self.command("docker", '''
            printf 'docker %s\n' "$*" >> "$PILOT_LOG"
            case "$*" in
                *' up '*) echo running > "$PILOT_STATE"; [[ "$PILOT_FAILURE" != start ]] ;;
                *' stop '*) echo exited > "$PILOT_STATE" ;;
                *' ps '*) echo fixture-container ;;
                'inspect '*) cat "$PILOT_STATE" ;;
            esac
        ''')
        for tool in ("flock", "timeout"):
            if not shutil.which(tool):
                self.command(tool, '''
                    case "$1" in -x) exit 0;; --kill-after=*) shift 2;; esac
                    exec "$@"
                ''')

    def command(self, name, code):
        target = self.root / name
        target.write_text("#!/bin/bash\n" + textwrap.dedent(code).strip() + "\n")
        target.chmod(0o700)

    def run_pilot(self, *args, failure=""):
        return subprocess.run(
            ["/bin/bash", str(self.script), *args], text=True, capture_output=True,
            env={**self.env, "PILOT_FAILURE": failure}, timeout=10,
        )

    def test_start_failure_after_container_created_stops_and_checks_state(self):
        result = self.run_pilot("start", "2099-01-01 00:00:00 UTC", "offline", failure="start")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state.read_text().strip(), "exited")
        self.assertTrue(self.state.with_suffix(".timer").exists())
        log = self.log.read_text()
        self.assertIn("withdraw offline", log)
        self.assertIn("offline.override.yml stop -t 15 prometheus", log)
        self.assertIn("inspect --format {{.State.Status}} fixture-container", log)
        self.assertNotIn("--unit=qlume-servera-monitoring-pilot-refresh", log)

    def test_refresh_start_failure_also_stops_the_container(self):
        result = self.run_pilot("start", "2099-01-01 00:00:00 UTC", failure="refresh")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state.read_text().strip(), "exited")

    def test_elapsed_deadline_after_start_triggers_stop_before_refresh(self):
        result = self.run_pilot("start", "2099-01-01 00:00:00 UTC", failure="deadline")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state.read_text().strip(), "exited")
        self.assertNotIn("--unit=qlume-servera-monitoring-pilot-refresh", self.log.read_text())

    def test_automatic_and_manual_stop_use_same_offline_compose(self):
        start = self.run_pilot("start", "2099-01-01 00:00:00 UTC", "offline")
        self.assertEqual(start.returncode, 0, start.stderr)
        self.assertEqual(self.state.read_text().strip(), "running")
        withdraw = self.run_pilot("withdraw", "offline")
        self.assertEqual(withdraw.returncode, 0, withdraw.stderr)
        self.assertEqual(self.state.read_text().strip(), "exited")
        self.assertTrue(self.state.with_suffix(".timer").exists())
        stop = self.run_pilot("stop", "offline")
        self.assertEqual(stop.returncode, 0, stop.stderr)
        self.assertFalse(self.state.with_suffix(".timer").exists())
        repeated = self.run_pilot("stop", "offline")
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(self.log.read_text().count("offline.override.yml stop -t 15 prometheus"), 3)

    def test_unverified_refresh_stop_leaves_expiry_timer(self):
        self.state.write_text("running\n")
        self.state.with_suffix(".timer").touch()
        result = self.run_pilot("stop", failure="service-stop")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.state.with_suffix(".timer").exists())
        self.assertEqual(self.state.read_text().strip(), "exited")
