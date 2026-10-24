package execution

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
	"reflect"
	"strings"
	"testing"
	"time"

	"fangcunmount.infra/rocketmq-native-recovery/internal/authority"
	"fangcunmount.infra/rocketmq-native-recovery/internal/barrier"
	"fangcunmount.infra/rocketmq-native-recovery/internal/checkonly"
	"fangcunmount.infra/rocketmq-native-recovery/internal/connection"
	"fangcunmount.infra/rocketmq-native-recovery/internal/nativeadmin"
	"fangcunmount.infra/rocketmq-native-recovery/internal/preview"
	"fangcunmount.infra/rocketmq-native-recovery/internal/privatefile"
	"fangcunmount.infra/rocketmq-native-recovery/internal/receipt"
	"fangcunmount.infra/rocketmq-native-recovery/internal/review"
	"github.com/FangcunMount/reliable-messaging/transaction"
	"github.com/FangcunMount/reliable-messaging/transport/rocketmq"
)

// All DB, admin and SDK operations below are explicitly fake. The existing
// Python coordinator is real and local; these tests start no DB/MQ or SSH.
type fakeAuthority struct {
	current authority.Snapshot
	calls   int
	err     error
}

func (f *fakeAuthority) Snapshot(context.Context, authority.Locator, [32]byte) (authority.Snapshot, error) {
	f.calls++
	return f.current, f.err
}
func (f *fakeAuthority) CheckStore() (transaction.PreparedStore, error) { return &fakePrepared{}, nil }
func (*fakeAuthority) ResolveNotice(context.Context, authority.Resolution) (authority.ResolutionResult, error) {
	panic("recovery must not resolve governance")
}
func (*fakeAuthority) VerifyResolution(context.Context, authority.Resolution) error {
	panic("recovery must not resolve governance")
}

type fakePrepared struct{ transaction.PreparedStore }
type fakeRuntime struct {
	sink                  checkonly.Sink
	request               review.Request
	authority             *fakeAuthority
	stats                 rocketmq.TransactionStats
	starts, closes, waits int
	err                   error
	badDrain              bool
	noSink                bool
}

func (f *fakeRuntime) Start(ctx context.Context) error {
	f.starts++
	if f.err != nil {
		return f.err
	}
	if !f.noSink {
		at := time.Now().UTC()
		f.authority.current.BeforeFinal = f.request.Expected()
		f.authority.current.BeforeFinalAt = &at
		if err := f.sink(ctx, checkonly.Event{ReferenceSHA256: review.ReferenceSHA(f.request), Outcome: f.request.Expected()}); err != nil {
			return err
		}
		f.stats.RecoveryAuditRecorded = 1
		f.stats.RecoveryCommitConfirmed = 1
		f.stats.CheckCommit = 1
	}
	return nil
}
func (f *fakeRuntime) Close(context.Context) error {
	f.closes++
	if !f.badDrain {
		f.stats.Stopped = true
	}
	return nil
}
func (f *fakeRuntime) Wait(context.Context) error       { f.waits++; return nil }
func (f *fakeRuntime) Stats() rocketmq.TransactionStats { return f.stats }
func (f *fakeRuntime) VerifyDrained() error             { return checkonly.VerifyStats(f.stats) }

type fakeAdmin struct {
	request review.Request
	calls   []string
	errMode string
	outcome string
}

func (f *fakeAdmin) Run(_ context.Context, r review.Request, sha [32]byte, mode, dir string) (nativeadmin.Report, [32]byte, error) {
	f.calls = append(f.calls, mode)
	if f.errMode == mode {
		return nativeadmin.Report{}, [32]byte{}, errors.New("explicit fake native failure")
	}
	s, _ := r.Snapshot.Authority()
	no, yes := false, true
	unique := sha256.Sum256([]byte(r.Index.BrokerMessageID))
	outcome := "NotAttempted"
	if mode == "resume" {
		outcome = f.outcome
	}
	p := nativeadmin.Report{Schema: "m3-managed-native-recheck/v1", Mode: mode, RequestSHA: review.Hex(sha), Nonce: r.Nonce, SourceSHA: r.SourceSHA, IndexSHA: r.Snapshot.Index, Outcome: outcome, BodyExported: &no, ReferenceSHA: review.Hex(review.ReferenceSHA(r)), WireSHA: review.Hex(s.Reference.WireHash), UniqueSHA: review.Hex(unique), Retention: 48, Remaining: 3600, BodyBytes: 3, Shutdown: &yes, ObservedAt: time.Now().UTC()}
	sum, err := review.Write(filepath.Join(dir, "native-"+mode+"-report.json"), p)
	return p, sum, err
}

func executionFixture(t *testing.T) (Input, review.Request, *fakeAuthority, func()) {
	t.Helper()
	root := t.TempDir()
	if err := os.Chmod(root, 0700); err != nil {
		t.Fatal(err)
	}
	write := func(name string, value any) preview.File {
		t.Helper()
		p := filepath.Join(root, name)
		sum, err := review.Write(p, value)
		if err != nil {
			t.Fatal(err)
		}
		return preview.File{Path: p, SHA256: sum}
	}
	manifestRaw, err := os.ReadFile("../../../../components/rocketmq/serverd-routes-m3-v2.json")
	if err != nil {
		t.Fatal(err)
	}
	mp := filepath.Join(root, "manifest.json")
	ms, err := privatefile.Write(mp, manifestRaw)
	if err != nil {
		t.Fatal(err)
	}
	routes, err := connection.Routes(mp, ms, "iam.mysql")
	if err != nil {
		t.Fatal(err)
	}
	c := connection.Config{Schema: "m3-native-recovery-config/v1", Owner: "iam.mysql", StoreID: "original", WriterEpoch: "epoch-1", DatabaseKind: "mysql", DatabaseURI: "unit:private@tcp(127.0.0.1:1)/original", DatabaseName: "original", Endpoint: "127.0.0.1:1", AccessKey: "unit", SecretKey: "private"}
	cf := write("config.json", c)
	export := map[string]any{"topic": review.NativeTopic, "key_sha256": strings.Repeat("1", 64), "records": []map[string]any{{"broker_message_id": strings.Repeat("A", 32), "queue_id": 0, "queue_offset": 1, "commitlog_offset": 2, "index_hour": 3}}, "raw_admin_sha256": strings.Repeat("2", 64), "read_only": true, "body_exported": false, "truncated_possible": false, "alert": "native_transaction_check_limit_reached", "severity": "critical"}
	ef := write("export.json", export)
	ib, _ := hex.DecodeString("c17eef089ffe8dcd195b09d54c8d7af26283362fc173a6226b964a4a4c0968d3")
	var index [32]byte
	copy(index[:], ib)
	row, err := review.SelectExport(ef.Path, ef.SHA256, index)
	if err != nil {
		t.Fatal(err)
	}
	ref := transaction.Reference{Owner: c.Owner, Scope: "org:7", OperationID: "original-op", BranchID: "fact", MessageID: "original", LogicalTopic: routes[0].LogicalTopic, PhysicalTopic: routes[0].PhysicalTopic, RouteRevision: "m3-1", WriterEpoch: c.WriterEpoch, Fence: 1, PlanDigest: [32]byte{1}, WireHash: [32]byte{2}, MessageFingerprint: [32]byte{3}}
	b := c.Binding()
	snapshot := authority.Snapshot{Binding: b, Reference: ref, DatabaseIdentitySHA256: [32]byte{4}, Decision: transaction.Commit, Half: transaction.HalfPrepared, BeforeFinal: transaction.FinalUnknown, Notice: authority.Notice{Key: authority.NoticeKey(b, index), IndexSHA256: index, FirstEvidenceSHA256: ef.SHA256, Status: "blocked"}}
	request, err := review.New(snapshot, row, review.Inputs{SourceSHA: strings.Repeat("1", 40), BinarySHA: [32]byte{5}, SourceBundleSHA: [32]byte{6}, ConfigSHA: cf.SHA256, ManifestSHA: ms, ExportSHA: ef.SHA256, DataOwner: "unit-data", RecoveryOwner: "unit-recovery", Now: time.Now().UTC().Add(-time.Second)})
	if err != nil {
		t.Fatal(err)
	}
	rf := write("request.json", request)
	dir := filepath.Join(root, "operation")
	host, err := os.Hostname()
	if err != nil {
		t.Fatal(err)
	}
	bf := write("binding-input.json", map[string]any{"schema": "m3-start-boundary/v1", "operation_id": "unit-recovery", "directory": dir, "scope_sha256": strings.Repeat("2", 64), "protection_sha256": strings.Repeat("3", 64), "restore_receipt_sha256": strings.Repeat("4", 64), "source_bundle_sha256": request.SourceBundleSHA, "data_owner": request.DataOwner, "recovery_owner": request.RecoveryOwner})
	script := []byte("#!/bin/bash\nexit 0\n")
	sp := filepath.Join(root, "frozen.sh")
	ss, err := privatefile.Write(sp, script)
	if err != nil {
		t.Fatal(err)
	}
	pf := write("step-input.json", map[string]any{"schema": "m3-cutover-step/v1", "directory": dir, "binding_sha256": review.Hex(bf.SHA256), "host": host, "step": "recover-native", "kind": "runtime-start", "script": sp, "script_sha256": review.Hex(ss), "cwd": root, "timeout_seconds": 240})
	// Match the canonical JSON bytes required by the actual Python producer.
	program := `import sys,json
sys.path.insert(0,sys.argv[1])
from start_boundary import initialize,Boundary,_publish
from cutover_step import _encoded,load_step
b=json.load(open(sys.argv[2]));p=json.load(open(sys.argv[4]))
import pathlib,hashlib
# The input helpers use JSON field order, while the actual coordinator requires
# its own canonical bytes. Return the actual canonical hashes to the Go caller.
braw=_encoded(b);p['binding_sha256']=hashlib.sha256(braw).hexdigest();praw=_encoded(p)
pathlib.Path(sys.argv[2]).write_bytes(braw);pathlib.Path(sys.argv[4]).write_bytes(praw)
bs=hashlib.sha256(braw).hexdigest();ps=hashlib.sha256(praw).hexdigest()
initialize(b['directory'],b,bs)
with Boundary(b['directory'],bs) as op:
 _publish(op.fd,'reviewed-step-'+ps+'.json',p)
 def hold():
  print(bs+' '+ps,flush=True);sys.stdin.buffer.read()
 op.start(p['step'],hold)
`
	cwd, e := os.Getwd()
	if e != nil {
		t.Fatal(e)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	cmd := exec.CommandContext(ctx, "python3", "-c", program, filepath.Clean(filepath.Join(cwd, "../../../../scripts/rocketmq")), bf.Path, review.Hex(bf.SHA256), pf.Path)
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
			_ = stdin.Close()
			e := cmd.Wait()
			cancel()
			if e != nil {
				t.Error("owned real coordinator failed to drain", e)
			}
		}
	}
	t.Cleanup(stop)
	line, e := bufio.NewReader(stdout).ReadString('\n')
	if e != nil {
		stop()
		t.Fatal("real coordinator did not issue runtime step")
	}
	hashes := strings.Fields(line)
	if len(hashes) != 2 {
		t.Fatal("missing actual coordinator hashes")
	}
	bs, e := review.Digest(hashes[0])
	if e != nil {
		t.Fatal(e)
	}
	ps, e := review.Digest(hashes[1])
	if e != nil {
		t.Fatal(e)
	}
	af := write("recover-approval.json", review.Approval{Schema: "m3-native-recovery-approval/v1", Action: "recover", RequestSHA: review.Hex(rf.SHA256), CoordinatorBindingSHA: review.Hex(bs), SourceBundleSHA: request.SourceBundleSHA, DataOwner: request.DataOwner, RecoveryOwner: request.RecoveryOwner, ExpiresAt: request.ExpiresAt})
	return Input{Config: cf, Manifest: preview.File{Path: mp, SHA256: ms}, Export: ef, Request: rf, Approval: af, Barrier: barrier.Context{Directory: dir, BindingSHA256: bs, StepPlanSHA256: ps, Step: "recover-native"}, SourceSHA: request.SourceSHA, BinarySHA: [32]byte{5}}, request, &fakeAuthority{current: snapshot}, stop
}

func fakeDependencies(r review.Request, a *fakeAuthority) (dependencies, *fakeRuntime, *fakeAdmin, *int) {
	rt := &fakeRuntime{request: r, authority: a}
	ad := &fakeAdmin{request: r, outcome: "RecheckEnqueued"}
	opens := new(int)
	return dependencies{open: func(context.Context, connection.Config) (connection.Opened, error) {
		*opens++
		return connection.Opened{Authority: a}, nil
	}, native: func(connection.Config) (admin, error) { return ad, nil }, runtime: func(_ rocketmq.TransactionConfig, _ transaction.PreparedStore, _ transaction.Reference, _ transaction.FinalOutcome, s checkonly.Sink) (runtime, error) {
		rt.sink = s
		return rt, nil
	}}, rt, ad, opens
}

func TestReviewedRecoveryCompositionUsesActualBarrierButExplicitFakeRPC(t *testing.T) {
	in, r, a, _ := executionFixture(t)
	deps, rt, ad, opens := fakeDependencies(r, a)
	result, err := recoverWith(context.Background(), in, deps)
	if err != nil || result.Final != transaction.FinalCommitConfirmed || result.Governance != authority.GovernanceNotAttempted || result.ReceiptSHA == "" || *opens != 1 || rt.starts != 1 || rt.closes != 1 || !reflect.DeepEqual(ad.calls, []string{"inspect", "resume"}) {
		t.Fatal("fake orchestration failed", err, result)
	}
	sum, err := review.Digest(result.ReceiptSHA)
	if err != nil {
		t.Fatal(err)
	}
	sealed, event, err := receipt.Load(result.ReceiptPath, sum, r, in.Request.SHA256, time.Now().UTC())
	if err != nil || event.Outcome != transaction.FinalCommitConfirmed || sealed.Nonce != r.Nonce {
		t.Fatal("private fake receipt did not validate", err)
	}
	if _, err = recoverWith(context.Background(), in, deps); err == nil || *opens != 1 {
		t.Fatal("reused consumed request")
	}
}

func TestReviewOrBarrierFailuresReachNoFakeDatabaseNativeOrRuntime(t *testing.T) {
	for _, name := range []string{"ended-coordinator", "wrong-binding", "wrong-step", "wrong-source", "wrong-binary", "wrong-config-sha", "wrong-request-sha", "wrong-approval-sha", "wrong-owner-name"} {
		t.Run(name, func(t *testing.T) {
			in, r, a, stop := executionFixture(t)
			deps, rt, ad, opens := fakeDependencies(r, a)
			switch name {
			case "ended-coordinator":
				stop()
			case "wrong-binding":
				in.Barrier.BindingSHA256[0] ^= 1
			case "wrong-step":
				in.Barrier.Step = "different"
			case "wrong-source":
				in.SourceSHA = strings.Repeat("2", 40)
			case "wrong-binary":
				in.BinarySHA[0] ^= 1
			case "wrong-config-sha":
				in.Config.SHA256[0] ^= 1
			case "wrong-request-sha":
				in.Request.SHA256[0] ^= 1
			case "wrong-approval-sha":
				in.Approval.SHA256[0] ^= 1
			case "wrong-owner-name":
				r.DataOwner = "other"
				p := filepath.Join(filepath.Dir(in.Request.Path), "other-request.json")
				sum, e := review.Write(p, r)
				if e != nil {
					t.Fatal(e)
				}
				in.Request = preview.File{Path: p, SHA256: sum}
			}
			if _, err := recoverWith(context.Background(), in, deps); err == nil || *opens != 0 || rt.starts != 0 || len(ad.calls) != 0 {
				t.Fatal("invalid approval reached external effects")
			}
		})
	}
}

func TestFailedOrUndrainedRecoveryNeverSealsSuccessOrResolvesGovernance(t *testing.T) {
	for _, name := range []string{"wrong-primary", "inspect-fails", "start-fails", "resume-fails", "undrained", "invalid-stats", "unknown-admin-positive-sdk"} {
		t.Run(name, func(t *testing.T) {
			in, r, a, _ := executionFixture(t)
			deps, rt, ad, _ := fakeDependencies(r, a)
			switch name {
			case "wrong-primary":
				a.current.DatabaseIdentitySHA256 = [32]byte{9}
			case "inspect-fails":
				ad.errMode = "inspect"
			case "start-fails":
				rt.err = errors.New("explicit fake start failure")
			case "resume-fails":
				ad.errMode = "resume"
			case "undrained":
				rt.badDrain = true
			case "invalid-stats":
				rt.stats.CompletedResults = 1
			case "unknown-admin-positive-sdk":
				ad.outcome = "Unknown"
			}
			result, err := recoverWith(context.Background(), in, deps)
			if name == "unknown-admin-positive-sdk" {
				if err != nil || result.NativeOutcome != "Unknown" || result.Final != transaction.FinalCommitConfirmed {
					t.Fatal("conflated native enqueue response with actual SDK final", err)
				}
				return
			}
			if err == nil || result.ReceiptSHA != "" || result.ReceiptPath != "" || result.Governance != authority.GovernanceNotAttempted {
				t.Fatal("false complete receipt", err, result)
			}
			claims, e := filepath.Glob(filepath.Join(in.Barrier.Directory, "native-recovery-claim-*.json"))
			if e != nil || len(claims) != 1 {
				t.Fatal("lost one-use claim or permitted implicit retry")
			}
		})
	}
}

func TestSealedReceiptRejectsReplayTruncationAndRuntimeCounterForgery(t *testing.T) {
	in, r, a, _ := executionFixture(t)
	deps, _, _, _ := fakeDependencies(r, a)
	result, err := recoverWith(context.Background(), in, deps)
	if err != nil {
		t.Fatal(err)
	}
	sum, err := review.Digest(result.ReceiptSHA)
	if err != nil {
		t.Fatal(err)
	}
	base, _, err := receipt.Load(result.ReceiptPath, sum, r, in.Request.SHA256, time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"nonce", "source", "binary", "request", "binding", "native-sha", "old-start", "future-end", "missing-observation", "reordered-observation", "wrong-observation-sha", "unfinished-sdk", "negative-sdk-counter", "sdk-json-alias", "sdk-json-duplicate", "sdk-json-unknown", "unlisted-file"} {
		t.Run(name, func(t *testing.T) {
			s := base
			s.Observations = append(s.Observations[:0:0], base.Observations...)
			switch name {
			case "nonce":
				s.Nonce = strings.Repeat("2", 64)
			case "source":
				s.SourceSHA = strings.Repeat("2", 40)
			case "binary":
				s.BinarySHA = strings.Repeat("2", 64)
			case "request":
				s.RequestSHA = strings.Repeat("2", 64)
			case "binding":
				s.CoordinatorBindingSHA = "bad"
			case "native-sha":
				s.NativeSHA = "bad"
			case "old-start":
				s.StartedAt = r.CreatedAt.Add(-time.Second)
			case "future-end":
				s.CompletedAt = time.Now().Add(2 * time.Minute)
			case "missing-observation":
				s.Observations = nil
			case "reordered-observation":
				s.Observations[0].Name = "rpc-02.json"
			case "wrong-observation-sha":
				s.Observations[0].SHA256 = strings.Repeat("2", 64)
			case "unfinished-sdk", "negative-sdk-counter":
				var stats rocketmq.TransactionStats
				if json.Unmarshal([]byte(s.RuntimeStats), &stats) != nil {
					t.Fatal("fixture stats")
				}
				if name == "unfinished-sdk" {
					stats.RunningChecks = 1
					stats.Stopped = false
				} else {
					stats.CheckUnknown = -1
				}
				raw, e := json.Marshal(stats)
				if e != nil {
					t.Fatal(e)
				}
				s.RuntimeStats = string(raw)
			case "sdk-json-alias":
				s.RuntimeStats = strings.Replace(s.RuntimeStats, `"Stopped":true`, `"stopped":true`, 1)
			case "sdk-json-duplicate":
				s.RuntimeStats = strings.Replace(s.RuntimeStats, `"Stopped":true`, `"Stopped":true,"Stopped":true`, 1)
			case "sdk-json-unknown":
				s.RuntimeStats = strings.Replace(s.RuntimeStats, `"Stopped":true`, `"Stopped":true,"unknown":true`, 1)
			case "unlisted-file":
				p := filepath.Join(s.ObservationDirectory, "rpc-02.json")
				if _, e := privatefile.Write(p, []byte("incomplete")); e != nil {
					t.Fatal(e)
				}
				defer os.Remove(p)
			}
			if _, e := s.Validate(r, in.Request.SHA256, time.Now().UTC()); e == nil {
				t.Fatal("accepted corrupt/replayed receipt")
			}
		})
	}
}
