package nativeadmin

import (
	"context"
	"crypto/sha256"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"fangcunmount.infra/rocketmq-native-recovery/internal/authority"
	"fangcunmount.infra/rocketmq-native-recovery/internal/connection"
	"fangcunmount.infra/rocketmq-native-recovery/internal/privatefile"
	"fangcunmount.infra/rocketmq-native-recovery/internal/review"
	"github.com/FangcunMount/reliable-messaging/transaction"
	"github.com/FangcunMount/reliable-messaging/transport"
)

// The child is a clearly synthetic Python report writer, NOT an MQ admin.
const fakeScript = `#!/bin/bash
exec python3 - "$1" <<'PY'
import json,sys,datetime
r=json.load(open(sys.argv[1]))
p=dict(schema='m3-managed-native-recheck/v1',mode=r['mode'],request_sha256=r['request_sha256'],invocation_nonce=r['invocation_nonce'],source_sha=r['source_sha'],native_index_sha256=r['native_index_sha256'],outcome='NotAttempted' if r['mode']=='inspect' else 'RecheckEnqueued',body_exported=False,reference_sha256=r['expected_reference_sha256'],wire_sha256=r['expected_wire_sha256'],unique_id_sha256=r['expected_unique_id_sha256'],retention_hours=48,remaining_seconds=3600,body_bytes=3,admin_shutdown_returned=True,observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
print('M3_MANAGED_NATIVE '+json.dumps(p))
PY
`

func nativeFixture(t *testing.T, script string) (*Runner, review.Request, string) {
	t.Helper()
	root := t.TempDir()
	if err := os.Chmod(root, 0700); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(root, "reviewed-native.sh")
	sum, err := privatefile.Write(path, []byte(script))
	if err != nil {
		t.Fatal(err)
	}
	c := connection.Config{Schema: "m3-native-recovery-config/v1", Owner: "iam.mysql", StoreID: "original", WriterEpoch: "epoch-1", DatabaseKind: "mysql", DatabaseURI: "unit:private@tcp(127.0.0.1:1)/original", DatabaseName: "original", Endpoint: "127.0.0.1:1", AccessKey: "unit", SecretKey: "private", AdminScript: path, AdminScriptSHA: review.Hex(sum), AdminNameserver: "127.0.0.1:1", AdminBroker: "127.0.0.1:1"}
	p, err := New(c)
	if err != nil {
		t.Fatal(err)
	}
	physical, err := transport.PhysicalTopicV2("logical", transport.TransactionMessageType, c.Owner, "m3-1")
	if err != nil {
		t.Fatal(err)
	}
	n := func(v int64) *int64 { return &v }
	index := review.Index{Topic: review.NativeTopic, KeySHA: strings.Repeat("1", 64), BrokerMessageID: strings.Repeat("A", 32), QueueID: n(0), QueueOffset: n(1), CommitlogOffset: n(2), IndexHour: n(3)}
	ih := index.Fingerprint()
	b := c.Binding()
	s := authority.Snapshot{Binding: b, Reference: transaction.Reference{Owner: b.Owner, Scope: "org:7", OperationID: "op", BranchID: "b", MessageID: "original", LogicalTopic: "logical", PhysicalTopic: physical, RouteRevision: "m3-1", WriterEpoch: b.WriterEpoch, Fence: 1, PlanDigest: [32]byte{1}, WireHash: [32]byte{2}, MessageFingerprint: [32]byte{3}}, DatabaseIdentitySHA256: [32]byte{4}, Decision: transaction.Commit, Half: transaction.HalfPrepared, BeforeFinal: transaction.FinalUnknown, Notice: authority.Notice{Key: authority.NoticeKey(b, ih), IndexSHA256: ih, FirstEvidenceSHA256: [32]byte{5}, Status: "blocked"}}
	r, err := review.New(s, index, review.Inputs{SourceSHA: strings.Repeat("1", 40), BinarySHA: [32]byte{6}, SourceBundleSHA: [32]byte{7}, ConfigSHA: [32]byte{8}, ManifestSHA: [32]byte{9}, ExportSHA: [32]byte{10}, DataOwner: "unit-data", RecoveryOwner: "unit-recovery", Now: time.Now().UTC()})
	if err != nil {
		t.Fatal(err)
	}
	return p, r, root
}

func TestFrozenNativeRunnerUsesOriginalBytesAndPrivateBoundedChild(t *testing.T) {
	p, r, root := nativeFixture(t, fakeScript)
	// The constructor copied independently hashed script bytes. A later path
	// replacement must not change the executed command.
	if err := os.WriteFile(p.config.AdminScript, []byte("exit 77\n"), 0600); err != nil {
		t.Fatal(err)
	}
	sha := sha256.Sum256([]byte("synthetic-reviewed-request"))
	for _, mode := range []string{"inspect", "resume"} {
		report, sum, err := p.Run(context.Background(), r, sha, mode, root)
		if err != nil || sum == [32]byte{} || report.BodyExported == nil || *report.BodyExported {
			t.Fatal("frozen fake child failed", err)
		}
		info, err := os.Stat(filepath.Join(root, "native-"+mode+"-private.log"))
		if err != nil || info.Mode().Perm() != 0600 {
			t.Fatal("child log not private")
		}
	}
	if _, _, err := p.Run(context.Background(), r, sha, "resume", root); err == nil {
		t.Fatal("overwrote prior native attempt")
	}
}

func TestNativeRunnerRejectsOutputFloodMalformedResponseAndLingeringGroup(t *testing.T) {
	for _, name := range []string{"raw-output", "unknown-field", "body-export", "wrong-identity", "flood", "lingering", "cancelled", "duplicate-frame", "unknown-enqueue-reply"} {
		t.Run(name, func(t *testing.T) {
			script := fakeScript
			switch name {
			case "raw-output":
				script = "printf 'DO_NOT_PRINT_PRIVATE\\n'\n"
			case "unknown-field":
				script = strings.Replace(script, "print('M3_MANAGED_NATIVE '", "p['unexpected']=True\nprint('M3_MANAGED_NATIVE '", 1)
			case "body-export":
				script = strings.Replace(script, "body_exported=False", "body_exported=True", 1)
			case "wrong-identity":
				script = strings.Replace(script, "request_sha256=r['request_sha256']", "request_sha256='0'*64", 1)
			case "flood":
				script = "exec python3 -c 'print(\"x\"*70000)'\n"
			case "lingering":
				script = "sleep 30 >/dev/null 2>&1 &\nexit 0\n"
			case "duplicate-frame":
				script = strings.Replace(script, "print('M3_MANAGED_NATIVE '+json.dumps(p))", "print('M3_MANAGED_NATIVE '+json.dumps(p))\nprint('M3_MANAGED_NATIVE '+json.dumps(p))", 1)
			case "unknown-enqueue-reply":
				script = strings.Replace(script, "else 'RecheckEnqueued'", "else 'Unknown'", 1)
				script = strings.Replace(script, "print('M3_MANAGED_NATIVE '+json.dumps(p))", "print('M3_MANAGED_NATIVE '+json.dumps(p))\nsys.exit(1)", 1)
			}
			p, r, root := nativeFixture(t, script)
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			if name == "cancelled" {
				cancel()
			}
			before := time.Now()
			report, sum, err := p.Run(ctx, r, [32]byte{1}, "resume", root)
			if name == "unknown-enqueue-reply" {
				if err != nil || report.Outcome != "Unknown" || sum == [32]byte{} {
					t.Fatal("conflated native unknown with definitive rejection", err)
				}
				return
			}
			if err == nil || sum != [32]byte{} || strings.Contains(err.Error(), "DO_NOT_PRINT_PRIVATE") || time.Since(before) > 5*time.Second {
				t.Fatal("unbounded/native invalid child accepted or leaked private output", err)
			}
		})
	}
}

func TestReportRejectsStaleBodyIdentityAndFiniteWindowMismatch(t *testing.T) {
	p, r, root := nativeFixture(t, fakeScript)
	sha := [32]byte{1}
	before := time.Now().UTC()
	report, _, err := p.Run(context.Background(), r, sha, "inspect", root)
	if err != nil {
		t.Fatal(err)
	}
	after := time.Now().UTC()
	for _, name := range []string{"request", "nonce", "wire", "owner-ref", "unique-id", "index", "body", "shutdown", "window", "retention", "old", "future", "mode"} {
		t.Run(name, func(t *testing.T) {
			v := report
			switch name {
			case "request":
				v.RequestSHA = strings.Repeat("2", 64)
			case "nonce":
				v.Nonce = strings.Repeat("2", 64)
			case "wire":
				v.WireSHA = strings.Repeat("2", 64)
			case "owner-ref":
				v.ReferenceSHA = strings.Repeat("2", 64)
			case "unique-id":
				v.UniqueSHA = strings.Repeat("2", 64)
			case "index":
				v.IndexSHA = strings.Repeat("2", 64)
			case "body":
				x := true
				v.BodyExported = &x
			case "shutdown":
				x := false
				v.Shutdown = &x
			case "window":
				v.Remaining = 120
			case "retention":
				v.Retention = 24
			case "old":
				v.ObservedAt = before.Add(-time.Minute)
			case "future":
				v.ObservedAt = after.Add(time.Minute)
			case "mode":
				v.Mode = "resume"
			}
			if v.Validate(r, sha, "inspect", before, after) == nil {
				t.Fatal("accepted stale/foreign physical report")
			}
		})
	}
}
