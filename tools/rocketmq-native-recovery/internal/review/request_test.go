package review

import (
	"crypto/sha256"
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"

	"fangcunmount.infra/rocketmq-native-recovery/internal/authority"
	"github.com/FangcunMount/reliable-messaging/transaction"
	"github.com/FangcunMount/reliable-messaging/transport"
)

func fixture(t *testing.T) (Request, authority.Snapshot) {
	t.Helper()
	n := func(v int64) *int64 { return &v }
	i := Index{NativeTopic, strings.Repeat("1", 64), strings.Repeat("A", 32), n(0), n(1), n(2), n(3)}
	b := transaction.Binding{Owner: "qs.mysql", StoreID: "原库", WriterEpoch: "epoch-1"}
	physical, err := transport.PhysicalTopicV2("unit.logical", transport.TransactionMessageType, b.Owner, "m3-1")
	if err != nil {
		t.Fatal(err)
	}
	ref := transaction.Reference{Owner: b.Owner, Scope: "org:7", OperationID: "operation", BranchID: "branch", MessageID: "original", LogicalTopic: "unit.logical", PhysicalTopic: physical, RouteRevision: "m3-1", WriterEpoch: b.WriterEpoch, Fence: 1, PlanDigest: [32]byte{1}, WireHash: [32]byte{2}, MessageFingerprint: [32]byte{3}}
	index := i.Fingerprint()
	s := authority.Snapshot{Binding: b, Reference: ref, DatabaseIdentitySHA256: [32]byte{4}, Decision: transaction.Commit, Half: transaction.HalfPrepared, BeforeFinal: transaction.FinalUnknown, Notice: authority.Notice{Key: authority.NoticeKey(b, index), IndexSHA256: index, FirstEvidenceSHA256: [32]byte{5}, Status: "blocked"}}
	now := time.Date(2026, 10, 24, 0, 0, 0, 0, time.UTC)
	r, err := New(s, i, Inputs{SourceSHA: strings.Repeat("1", 40), BinarySHA: [32]byte{6}, SourceBundleSHA: [32]byte{7}, ConfigSHA: [32]byte{8}, ManifestSHA: [32]byte{9}, ExportSHA: [32]byte{10}, DataOwner: "unit-data", RecoveryOwner: "unit-recovery", Now: now})
	if err != nil {
		t.Fatal(err)
	}
	return r, s
}
func write(t *testing.T, value any) (string, [32]byte) {
	t.Helper()
	path := filepath.Join(t.TempDir(), "object.json")
	sum, err := Write(path, value)
	if err != nil {
		t.Fatal(err)
	}
	return path, sum
}

func TestFrozenRequestRoundTripRetainsOriginalBytesAndOldAudit(t *testing.T) {
	r, s := fixture(t)
	at := time.Unix(1, 0).UTC()
	s.BeforeFinal = transaction.FinalCommitConfirmed
	s.BeforeFinalAt = &at
	f, err := Freeze(s)
	if err != nil {
		t.Fatal(err)
	}
	r.Snapshot = f
	p, sum := write(t, r)
	loaded, err := Load(p, sum, r.CreatedAt)
	if err != nil {
		t.Fatal(err)
	}
	actual, err := loaded.Snapshot.Authority()
	if err != nil {
		t.Fatal(err)
	}
	if actual.Reference != s.Reference || actual.Binding != s.Binding || !actual.BeforeFinalAt.Equal(at) || !reflect.DeepEqual(actual.Notice, s.Notice) {
		t.Fatal("round trip changed authority")
	}
	if loaded.Expected() != transaction.FinalCommitConfirmed || ReferenceSHA(loaded) != sha256.Sum256([]byte(r.Snapshot.Reference)) {
		t.Fatal("wrong outcome or reference digest")
	}
	if _, err = Write(p, r); err == nil {
		t.Fatal("overwrote reviewed request")
	}
}

func TestRequestRejectsIdentityExpiryAndEvidenceDrift(t *testing.T) {
	for _, name := range []string{"prepared", "expired", "future", "long-window", "zero-window", "source", "binary", "nonce", "owner", "epoch", "fence", "reference-alias", "reference-duplicate", "reference-padding", "index", "key", "wire", "notice", "proof", "unknown-final", "missing-final-time", "blank-owner"} {
		t.Run(name, func(t *testing.T) {
			r, _ := fixture(t)
			switch name {
			case "prepared":
				r.Snapshot.Decision = transaction.Unknown
			case "expired":
				r.ExpiresAt = r.CreatedAt
			case "future":
				r.CreatedAt = r.CreatedAt.Add(2 * time.Minute)
			case "long-window":
				r.ExpiresAt = r.CreatedAt.Add(2 * time.Hour)
			case "zero-window":
				r.ExpiresAt = r.CreatedAt.Add(-time.Second)
			case "source":
				r.SourceSHA = strings.Repeat("0", 40)
			case "binary":
				r.BinarySHA = strings.Repeat("0", 64)
			case "nonce":
				r.Nonce = strings.Repeat("A", 64)
			case "owner":
				r.Snapshot.Owner = "ai.mysql"
			case "epoch":
				r.Snapshot.Epoch = "foreign"
			case "fence":
				r.Snapshot.Reference = strings.Replace(r.Snapshot.Reference, `"fence":1`, `"fence":0`, 1)
			case "reference-alias":
				r.Snapshot.Reference = strings.Replace(r.Snapshot.Reference, `"owner"`, `"Owner"`, 1)
			case "reference-duplicate":
				r.Snapshot.Reference = strings.Replace(r.Snapshot.Reference, `"owner":"qs.mysql"`, `"owner":"qs.mysql","owner":"qs.mysql"`, 1)
			case "reference-padding":
				r.Snapshot.Reference += "\n"
			case "index":
				v := int64(3)
				r.Index.CommitlogOffset = &v
			case "key":
				r.Index.KeySHA = strings.Repeat("0", 64)
			case "wire":
				r.Snapshot.Reference = strings.Replace(r.Snapshot.Reference, Hex([32]byte{2}), strings.Repeat("0", 64), 1)
			case "notice":
				r.Snapshot.NoticeKey = strings.Repeat("1", 64)
			case "proof":
				r.Snapshot.FirstEvidence = strings.Repeat("0", 64)
			case "unknown-final":
				r.Snapshot.Final = transaction.FinalRollbackConfirmed
			case "missing-final-time":
				r.Snapshot.Final = transaction.FinalCommitConfirmed
			case "blank-owner":
				r.DataOwner = "\n"
			}
			// Keep a fixed authoritative clock, independent of mutations.
			if r.Validate(time.Date(2026, 10, 24, 0, 0, 0, 0, time.UTC)) == nil {
				t.Fatal("accepted invalid request")
			}
		})
	}
}

func TestRepeatedPreviewUsesNewNonceWithoutChangingOriginalReference(t *testing.T) {
	a, _ := fixture(t)
	b, _ := fixture(t)
	if a.Nonce == b.Nonce || a.Snapshot.Reference != b.Snapshot.Reference || a.Snapshot.Index != b.Snapshot.Index {
		t.Fatal("new invocation must not become new message")
	}
}

func TestExpiredRequestCanOnlyBeLoadedForRecordedReadonlyVerification(t *testing.T) {
	r, _ := fixture(t)
	p, sha := write(t, r)
	later := r.ExpiresAt.Add(time.Hour)
	if _, err := Load(p, sha, later); err == nil {
		t.Fatal("expired review authorized new recovery")
	}
	if got, err := LoadRecorded(p, sha, later); err != nil || got.Nonce != r.Nonce || got.Snapshot.Reference != r.Snapshot.Reference {
		t.Fatal("lost ability to inspect an old uncertain governance commit", err)
	}
	if _, err := LoadRecorded(p, sha, r.CreatedAt.Add(-2*time.Minute)); err == nil {
		t.Fatal("accepted future recorded request")
	}
}

func TestApprovalPinsBothNamesBindingSourceAndCurrentReceipt(t *testing.T) {
	r, _ := fixture(t)
	requestSHA := [32]byte{1}
	receiptSHA := [32]byte{2}
	bindingSHA := [32]byte{3}
	base := Approval{Schema: "m3-native-recovery-approval/v1", Action: "check", RequestSHA: Hex(requestSHA), CoordinatorBindingSHA: Hex(bindingSHA), SourceBundleSHA: r.SourceBundleSHA, DataOwner: r.DataOwner, RecoveryOwner: r.RecoveryOwner, ExpiresAt: r.ExpiresAt}
	p, sum := write(t, base)
	if err := Approve(p, sum, r, requestSHA, [32]byte{}, bindingSHA, "check", r.CreatedAt); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"request", "receipt", "binding", "source", "data-owner", "recovery-owner", "action", "expiry", "zero-request"} {
		t.Run(name, func(t *testing.T) {
			a := base
			req := requestSHA
			switch name {
			case "request":
				a.RequestSHA = Hex(receiptSHA)
			case "receipt":
				a.ReceiptSHA = Hex(receiptSHA)
			case "binding":
				a.CoordinatorBindingSHA = Hex(requestSHA)
			case "source":
				a.SourceBundleSHA = Hex(requestSHA)
			case "data-owner":
				a.DataOwner = "other"
			case "recovery-owner":
				a.RecoveryOwner = "other"
			case "action":
				a.Action = "resolve"
			case "expiry":
				a.ExpiresAt = r.CreatedAt
			case "zero-request":
				req = [32]byte{}
			}
			p, sum := write(t, a)
			if Approve(p, sum, r, req, [32]byte{}, bindingSHA, "check", r.CreatedAt) == nil {
				t.Fatal("accepted changed review")
			}
		})
	}
	base.Action = "resolve"
	base.ReceiptSHA = Hex(receiptSHA)
	p, sum = write(t, base)
	for _, action := range []string{"resolve", "verify"} {
		if err := Approve(p, sum, r, requestSHA, receiptSHA, bindingSHA, action, r.CreatedAt); err != nil {
			t.Fatal(err)
		}
	}
	if Approve(p, sum, r, requestSHA, [32]byte{4}, bindingSHA, "verify", r.CreatedAt) == nil {
		t.Fatal("replaced RPC receipt during unknown-commit verification")
	}
}

func TestPhysicalIndexMatchesExistingHostV1VectorsAndKeepsCopiedClientID(t *testing.T) {
	r, _ := fixture(t)
	if Hex(r.Index.Fingerprint()) != "c17eef089ffe8dcd195b09d54c8d7af26283362fc173a6226b964a4a4c0968d3" {
		t.Fatal("changed host v1 fingerprint")
	}
	copyIndex := r.Index
	queue, offset := int64(2), int64(3)
	copyIndex.QueueOffset = &queue
	copyIndex.CommitlogOffset = &offset
	if Hex(copyIndex.Fingerprint()) != "61922da276bd4e4b9eced322f30aac9224929b6614dce2205f5fed99df91a878" {
		t.Fatal("copy deduplicated by client ID")
	}
	r.Index.BrokerMessageID = strings.ToLower(r.Index.BrokerMessageID)
	if r.Index.Fingerprint() == [32]byte{} || r.Index.Fingerprint() != mustIndex(t).Fingerprint() {
		t.Fatal("hex case changed physical identity")
	}
}
func mustIndex(t *testing.T) Index { t.Helper(); r, _ := fixture(t); return r.Index }

func exportFixture(t *testing.T) nativeExport {
	t.Helper()
	i := mustIndex(t)
	yes, no := true, false
	return nativeExport{Topic: NativeTopic, Key: i.KeySHA, Admin: strings.Repeat("2", 64), ReadOnly: &yes, Body: &no, Truncated: &no, Alert: "native_transaction_check_limit_reached", Severity: "critical", Rows: []exportRow{{i.BrokerMessageID, i.QueueID, i.QueueOffset, i.CommitlogOffset, i.IndexHour}}}
}
func TestSelectExportValidatesAllRowsAndDoesNotCollapseNativeCopies(t *testing.T) {
	e := exportFixture(t)
	i := mustIndex(t)
	copyRow := e.Rows[0]
	queue, offset := int64(2), int64(3)
	copyRow.QueueOffset = &queue
	copyRow.CommitlogOffset = &offset
	e.Rows = append(e.Rows, copyRow)
	p, sum := write(t, e)
	selected, err := SelectExport(p, sum, i.Fingerprint())
	if err != nil || selected.Fingerprint() != i.Fingerprint() {
		t.Fatal(err)
	}
	for _, name := range []string{"duplicate-case-alias", "missing-position", "negative-position", "bad-unselected-row", "not-readonly", "body-exported", "truncated-flag", "bad-admin", "missing-target", "duplicate-json-key"} {
		t.Run(name, func(t *testing.T) {
			e := exportFixture(t)
			target := i.Fingerprint()
			switch name {
			case "duplicate-case-alias":
				row := e.Rows[0]
				row.MessageID = strings.ToLower(row.MessageID)
				e.Rows = append(e.Rows, row)
			case "missing-position":
				e.Rows[0].CommitlogOffset = nil
			case "negative-position":
				v := int64(-1)
				e.Rows[0].QueueID = &v
			case "bad-unselected-row":
				row := e.Rows[0]
				row.MessageID = "invalid"
				e.Rows = append(e.Rows, row)
			case "not-readonly":
				v := false
				e.ReadOnly = &v
			case "body-exported":
				v := true
				e.Body = &v
			case "truncated-flag":
				v := true
				e.Truncated = &v
			case "bad-admin":
				e.Admin = strings.Repeat("0", 64)
			case "missing-target":
				target = [32]byte{1}
			}
			p, sum := write(t, e)
			if name == "duplicate-json-key" {
				raw, er := json.Marshal(e)
				if er != nil {
					t.Fatal(er)
				}
				raw = []byte(strings.Replace(string(raw), `"topic":`, `"topic":"ignored","topic":`, 1))
				if er = os.WriteFile(p, raw, 0600); er != nil {
					t.Fatal(er)
				}
				sum = sha256.Sum256(raw)
			}
			if _, err := SelectExport(p, sum, target); err == nil {
				t.Fatal("accepted invalid native export")
			}
		})
	}
}
