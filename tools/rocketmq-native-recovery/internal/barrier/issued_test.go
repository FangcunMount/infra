package barrier

import (
	"bufio"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestIssuedProofRetainsActualNamedOwnersAndSourceBundle(t *testing.T) {
	c, _ := issuedFixture(t, "runtime-start")
	p, err := RequireIssued(c)
	if err != nil || !p.Matches("unit-data-owner", "unit-recovery-owner", strings.Repeat("4", 64)) || p.TimeoutSeconds() != 30 {
		t.Fatal("lost actual coordinator review context", err)
	}
	if p.Matches("other", "unit-recovery-owner", strings.Repeat("4", 64)) || p.Matches("unit-data-owner", "other", strings.Repeat("4", 64)) || p.Matches("unit-data-owner", "unit-recovery-owner", strings.Repeat("5", 64)) {
		t.Fatal("foreign named review matched issued proof")
	}
}

// Uses the actual infra Python coordinator producer and its live lock. It
// starts no service, database, MQ or SSH connection.
func issuedFixture(t *testing.T, kind string) (Context, func()) {
	t.Helper()
	root := t.TempDir()
	directory := filepath.Join(root, "operation")
	host, err := os.Hostname()
	if err != nil {
		t.Fatal(err)
	}
	write := func(name string, value any) (string, [32]byte) {
		raw, e := json.Marshal(value)
		if e != nil {
			t.Fatal(e)
		}
		path := filepath.Join(root, name)
		if e = os.WriteFile(path, raw, 0600); e != nil {
			t.Fatal(e)
		}
		return path, sha256.Sum256(raw)
	}
	b := map[string]any{"schema": "m3-start-boundary/v1", "operation_id": "unit-recovery", "directory": directory, "scope_sha256": strings.Repeat("1", 64), "protection_sha256": strings.Repeat("2", 64), "restore_receipt_sha256": strings.Repeat("3", 64), "source_bundle_sha256": strings.Repeat("4", 64), "data_owner": "unit-data-owner", "recovery_owner": "unit-recovery-owner"}
	bPath, bSHA := write("binding-input.json", b)
	script := filepath.Join(root, "immutable.sh")
	scriptBytes := []byte("#!/bin/bash\nexit 0\n")
	if err = os.WriteFile(script, scriptBytes, 0600); err != nil {
		t.Fatal(err)
	}
	scriptSHA := sha256.Sum256(scriptBytes)
	step := map[string]any{"schema": "m3-cutover-step/v1", "directory": directory, "binding_sha256": hex.EncodeToString(bSHA[:]), "host": host, "step": "native-check", "kind": kind, "script": script, "script_sha256": hex.EncodeToString(scriptSHA[:]), "cwd": root, "timeout_seconds": 30}
	pPath, pSHA := write("step-input.json", step)
	cwd, e := os.Getwd()
	if e != nil {
		t.Fatal(e)
	}
	scripts := filepath.Clean(filepath.Join(cwd, "../../../..", "scripts/rocketmq"))
	program := `import sys,json
sys.path.insert(0,sys.argv[1])
from start_boundary import initialize,Boundary,_publish
from cutover_step import load_step
b=json.load(open(sys.argv[2])); p,script=load_step(__import__('pathlib').Path(sys.argv[4]),sys.argv[5])
initialize(b['directory'],b,sys.argv[3])
with Boundary(b['directory'],sys.argv[3]) as op:
 _publish(op.fd,'reviewed-step-'+sys.argv[5]+'.json',p)
 def callback():
  print('held',flush=True)
  sys.stdin.buffer.read()
 if p['kind']=='runtime-start':op.start(p['step'],callback)
 else:
  op.start('prior-runtime',lambda:None)
  op.forward_repair(p['step'],sys.argv[5],callback)
`
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	cmd := exec.CommandContext(ctx, "python3", "-c", program, scripts, bPath, hex.EncodeToString(bSHA[:]), pPath, hex.EncodeToString(pSHA[:]))
	cmd.WaitDelay = time.Second
	stdin, e := cmd.StdinPipe()
	if e != nil {
		cancel()
		t.Fatal(e)
	}
	stdout, e := cmd.StdoutPipe()
	if e != nil {
		cancel()
		t.Fatal(e)
	}
	if e = cmd.Start(); e != nil {
		cancel()
		t.Fatal(e)
	}
	stopped := false
	stop := func() {
		if !stopped {
			stopped = true
			_ = os.Chmod(directory, 0700)
			_ = stdin.Close()
			e := cmd.Wait()
			cancel()
			if e != nil {
				t.Errorf("owned coordinator failed or did not drain: %v", e)
			}
		}
	}
	t.Cleanup(stop)
	ready, e := bufio.NewReader(stdout).ReadString('\n')
	if e != nil || ready != "held\n" {
		stop()
		t.Fatal("real coordinator did not issue its step")
	}
	return Context{directory, bSHA, pSHA, "native-check"}, stop
}

func TestRealCoordinatorIssuedRuntimeAndForwardRepairAreRecognized(t *testing.T) {
	for _, kind := range []string{"runtime-start", "forward-repair"} {
		t.Run(kind, func(t *testing.T) {
			c, stop := issuedFixture(t, kind)
			proof, err := RequireIssued(c)
			if err != nil || !proof.Valid() {
				t.Fatal("real issued coordinator rejected", err)
			}
			stop()
			if _, err = RequireIssued(c); !errors.Is(err, ErrIssued) {
				t.Fatal("returned command history treated as current authorization")
			}
			if _, err = os.Stat(filepath.Join(c.Directory, "first-runtime-start.json")); err != nil {
				t.Fatal("reader removed irreversible start marker")
			}
		})
	}
}

func TestIssuedReaderRejectsCorruptForeignOrUnissuedContext(t *testing.T) {
	for _, scenario := range []string{"binding-sha", "step-sha", "step-name", "missing-marker", "marker-binding", "state-phase", "state-mode", "directory-mode", "missing-repair"} {
		t.Run(scenario, func(t *testing.T) {
			kind := "runtime-start"
			if scenario == "missing-repair" {
				kind = "forward-repair"
			}
			c, _ := issuedFixture(t, kind)
			write := func(name string, value any) {
				raw, e := json.Marshal(value)
				if e != nil {
					t.Fatal(e)
				}
				if e = os.WriteFile(filepath.Join(c.Directory, name), raw, 0600); e != nil {
					t.Fatal(e)
				}
			}
			switch scenario {
			case "missing-repair":
				if err := os.Remove(filepath.Join(c.Directory, "repair-approval-"+hex.EncodeToString(c.StepPlanSHA256[:])+".json")); err != nil {
					t.Fatal(err)
				}
			case "binding-sha":
				c.BindingSHA256[0] ^= 1
			case "step-sha":
				c.StepPlanSHA256[0] ^= 1
			case "step-name":
				c.Step = "different"
			case "missing-marker":
				if err := os.Remove(filepath.Join(c.Directory, "first-runtime-start.json")); err != nil {
					t.Fatal(err)
				}
			case "marker-binding":
				write("first-runtime-start.json", map[string]any{"binding_sha256": strings.Repeat("9", 64), "first_step": c.Step})
			case "state-phase":
				write("state.json", map[string]any{"binding_sha256": hex.EncodeToString(c.BindingSHA256[:]), "phase": "maintenance_issued", "step": c.Step})
			case "state-mode":
				if err := os.Chmod(filepath.Join(c.Directory, "state.json"), 0644); err != nil {
					t.Fatal(err)
				}
			case "directory-mode":
				if err := os.Chmod(c.Directory, 0755); err != nil {
					t.Fatal(err)
				}
			}
			if _, err := RequireIssued(c); !errors.Is(err, ErrIssued) {
				t.Fatal("corrupt or foreign context accepted")
			}
		})
	}
}
