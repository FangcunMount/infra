package authority

import (
	"context"
	"crypto/sha256"
	"database/sql"
	_ "embed"
	"encoding/hex"
	"errors"
	"testing"
	"time"

	"github.com/FangcunMount/reliable-messaging/message"
	"github.com/FangcunMount/reliable-messaging/transaction"
	"github.com/FangcunMount/reliable-messaging/transport"
)

func snapshotFixture(t *testing.T) (Snapshot, Locator) {
	t.Helper()
	b := transaction.Binding{Owner: "ai.mysql", StoreID: "original", WriterEpoch: "m3-1"}
	m, err := message.New(message.Input{Producer: "unit", ID: "original", Destination: "unit.logical", EventType: "fact", SchemaVersion: "v1", Scope: "org:7", ContentType: "application/octet-stream", OccurredAt: "2026-10-24T00:00:00Z", Payload: []byte{0, 255, 1}})
	if err != nil {
		t.Fatal(err)
	}
	physical, err := transport.PhysicalTopicV2("unit.logical", transport.TransactionMessageType, b.Owner, "m3-1")
	if err != nil {
		t.Fatal(err)
	}
	p, err := transaction.NewPlan(transaction.PlanInput{Owner: b.Owner, Scope: "org:7", OperationID: "original-op", IdempotencyKey: "original-key", InputHash: sha256.Sum256([]byte("input")), Branches: []transaction.BranchInput{{ID: "fact", PhysicalTopic: physical, RouteRevision: "m3-1", Message: m, Wire: []byte{0, 255, 2}}}})
	if err != nil {
		t.Fatal(err)
	}
	ref, err := p.Reference("fact", 1, b.WriterEpoch)
	if err != nil {
		t.Fatal(err)
	}
	index := [32]byte{1}
	return Snapshot{Binding: b, Reference: ref, DatabaseIdentitySHA256: databaseIdentity("mysql", "original-uuid", "original-db"), Decision: transaction.Commit, Half: transaction.HalfPrepared, BeforeFinal: transaction.FinalUnknown, Notice: Notice{Key: NoticeKey(b, index), IndexSHA256: index, FirstEvidenceSHA256: [32]byte{2}, Status: "blocked"}}, Locator{"original-op", "fact", 1}
}

func TestSnapshotDoesNotTreatOldPositiveAuditAsCurrentRPC(t *testing.T) {
	s, l := snapshotFixture(t)
	if err := validateSnapshot(s, l, transaction.Committed, transaction.Committed, ""); err != nil {
		t.Fatal(err)
	}
	at := time.Unix(1, 0).UTC()
	s.BeforeFinal = transaction.FinalCommitConfirmed
	s.BeforeFinalAt = &at
	if err := validateSnapshot(s, l, transaction.Committed, transaction.Committed, ""); err != nil {
		t.Fatal("old positive audit must remain valid before recovery", err)
	}
	// No RPC result/current-observation field exists in this review snapshot.
	if !s.BeforeFinalAt.Equal(at) {
		t.Fatal("snapshot refreshed first positive time")
	}
}

func TestSnapshotAcceptsExactFencedAbortWithoutReauthorizingBusiness(t *testing.T) {
	s, l := snapshotFixture(t)
	s.Decision = transaction.Rollback
	s.BeforeFinal = transaction.FinalNotAttempted
	if err := validateSnapshot(s, l, transaction.Aborted, transaction.Aborted, ""); err != nil {
		t.Fatal(err)
	}
	at := time.Unix(1, 0).UTC()
	s.BeforeFinal, s.BeforeFinalAt = transaction.FinalRollbackConfirmed, &at
	if err := validateSnapshot(s, l, transaction.Aborted, transaction.Aborted, ""); err != nil {
		t.Fatal(err)
	}
}

func TestSnapshotRejectsMissingPreparedContradictoryOrForeignAuthority(t *testing.T) {
	for _, scenario := range []string{"prepared", "contradiction", "owner", "epoch", "operation", "branch", "fence", "route", "physical-topic", "wire", "plan", "fingerprint", "database", "opposite-final", "missing-final-time", "final-error", "index", "notice-key", "proof", "unknown-status", "blocked-with-receipt", "resolved-without-receipt"} {
		t.Run(scenario, func(t *testing.T) {
			s, l := snapshotFixture(t)
			execution, branch := transaction.Committed, transaction.Committed
			code := ""
			switch scenario {
			case "prepared":
				execution = transaction.Prepared
			case "contradiction":
				branch = transaction.Aborted
			case "owner":
				s.Reference.Owner = "qs.mysql"
			case "epoch":
				s.Reference.WriterEpoch = "old"
			case "operation":
				s.Reference.OperationID = "other"
			case "branch":
				s.Reference.BranchID = "other"
			case "fence":
				s.Reference.Fence++
			case "route":
				s.Reference.RouteRevision = "other"
			case "physical-topic":
				s.Reference.PhysicalTopic += "_foreign"
			case "wire":
				s.Reference.WireHash = [32]byte{}
			case "plan":
				s.Reference.PlanDigest = [32]byte{}
			case "fingerprint":
				s.Reference.MessageFingerprint = [32]byte{}
			case "database":
				s.DatabaseIdentitySHA256 = [32]byte{}
			case "opposite-final":
				s.BeforeFinal = transaction.FinalRollbackConfirmed
			case "missing-final-time":
				s.BeforeFinal = transaction.FinalCommitConfirmed
			case "final-error":
				s.BeforeFinal = transaction.FinalCommitConfirmed
				now := time.Now()
				s.BeforeFinalAt = &now
				code = "conflicting"
			case "index":
				s.Notice.IndexSHA256 = [32]byte{}
			case "notice-key":
				s.Notice.Key[0] ^= 1
			case "proof":
				s.Notice.FirstEvidenceSHA256 = [32]byte{}
			case "unknown-status":
				s.Notice.Status = "ignored"
			case "blocked-with-receipt":
				s.Notice.ResolutionReceiptSHA256 = make([]byte, 32)
			case "resolved-without-receipt":
				s.Notice.Status = "resolved"
			}
			if !errors.Is(validateSnapshot(s, l, execution, branch, code), ErrSnapshot) {
				t.Fatal("unsafe authority accepted")
			}
		})
	}
}

func TestLocatorAndConstructorRejectBeforeAnyConnection(t *testing.T) {
	s, l := snapshotFixture(t)
	db := new(sql.DB)
	store, err := NewMySQL(db, s.Binding)
	if err != nil {
		t.Fatal(err)
	}
	for _, invalid := range []Locator{{}, {OperationID: l.OperationID, BranchID: l.BranchID, Fence: transaction.MaxFence + 1}, {OperationID: l.OperationID, BranchID: " ", Fence: 1}} {
		if _, err = store.Snapshot(context.Background(), invalid, [32]byte{1}); !errors.Is(err, ErrSnapshot) {
			t.Fatal("invalid locator reached database")
		}
	}
	if _, err = store.Snapshot(context.Background(), l, [32]byte{}); !errors.Is(err, ErrSnapshot) {
		t.Fatal("missing native index reached database")
	}
	for _, owner := range []string{"qs.mongo", "unknown", ""} {
		b := s.Binding
		b.Owner = owner
		if _, err = NewMySQL(db, b); !errors.Is(err, transaction.ErrBinding) {
			t.Fatal("foreign configured owner accepted")
		}
	}
	if _, err = NewMySQL(nil, s.Binding); !errors.Is(err, transaction.ErrBinding) {
		t.Fatal("nil primary accepted")
	}
}

func TestNoticeIdentityMatchesFrozenHostCrossLanguageVector(t *testing.T) {
	raw, err := hex.DecodeString("826e83de4c78da591b9fdeb1571d7ad86be6355bb1b360430d576ca262b4a633")
	if err != nil {
		t.Fatal(err)
	}
	var index [32]byte
	copy(index[:], raw)
	key := NoticeKey(transaction.Binding{Owner: "qs.mysql", StoreID: "原库", WriterEpoch: "epoch-1"}, index)
	if hex.EncodeToString(key[:]) != "f93835f735b87a3a4af30ceb3b0dae81b08815fb24c8705644f20e7ad5b608ff" {
		t.Fatal("host notice framing changed")
	}
}

// Frozen test-only copy of IAM migration45, not an operator installation path.
//
//go:embed testdata/iam-000045-governance.sql
var nativeNoticeSchema string

func TestFrozenGovernanceFixtureMatchesRecordedHostMigration(t *testing.T) {
	sum := sha256.Sum256([]byte(nativeNoticeSchema))
	if hex.EncodeToString(sum[:]) != "0d0df3ac8dcc10ebbe9e735ee0a8da600f0eefb3cdc6f33da276c975500e0e5a" {
		t.Fatal("frozen IAM45 governance fixture changed")
	}
}
