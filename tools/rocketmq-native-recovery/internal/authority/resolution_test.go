package authority

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"errors"
	"testing"
	"time"

	"fangcunmount.infra/rocketmq-native-recovery/internal/checkonly"
	"github.com/FangcunMount/reliable-messaging/transaction"
)

// Controlled storage-input fixture. It is NOT a named approval or real RPC;
// complete CLI/approval/RPC validation remains a separate mandatory gate.
func storageResolutionFixture(t *testing.T, s Snapshot) Resolution {
	t.Helper()
	raw, err := transaction.EncodeReference(s.Reference)
	if err != nil {
		t.Fatal(err)
	}
	outcome := transaction.FinalCommitConfirmed
	if s.Decision == transaction.Rollback {
		outcome = transaction.FinalRollbackConfirmed
	}
	return Resolution{Reviewed: s, RequestSHA256: sha256.Sum256([]byte("controlled-request-not-production-approval")), ReceiptSHA256: sha256.Sum256([]byte("controlled-receipt-not-rpc-proof")), CurrentObservation: checkonly.Event{ReferenceSHA256: sha256.Sum256(raw), Outcome: outcome}}
}

func TestResolutionUsesFreshPositiveAuthorityWithoutTimestampRefresh(t *testing.T) {
	s, _ := snapshotFixture(t)
	r := storageResolutionFixture(t, s)
	if !r.valid() {
		t.Fatal("valid controlled storage precondition rejected")
	}
	if r.matches(s) {
		t.Fatal("missing positive DB audit accepted")
	}
	old := time.Unix(1, 0).UTC()
	current := s
	current.BeforeFinal = transaction.FinalCommitConfirmed
	current.BeforeFinalAt = &old
	if !r.matches(current) {
		t.Fatal("old preserved positive audit incorrectly required refresh")
	}
	current.Notice.Status = "resolved"
	current.Notice.ResolvedAt = &old
	current.Notice.ResolutionReceiptSHA256 = r.ReceiptSHA256[:]
	if !r.matches(current) {
		t.Fatal("same receipt cannot be verified idempotently")
	}
	current.Notice.ResolutionReceiptSHA256 = make([]byte, 32)
	if r.matches(current) {
		t.Fatal("different resolution receipt accepted")
	}
}

func TestResolutionRejectsMissingReceiptOrCurrentReferenceBeforeConnecting(t *testing.T) {
	s, _ := snapshotFixture(t)
	reader, err := NewMySQL(new(sql.DB), s.Binding)
	if err != nil {
		t.Fatal(err)
	}
	for _, scenario := range []string{"request", "receipt", "current-ref", "current-outcome", "prepared", "notice-proof", "already-resolved-input"} {
		t.Run(scenario, func(t *testing.T) {
			r := storageResolutionFixture(t, s)
			switch scenario {
			case "request":
				r.RequestSHA256 = [32]byte{}
			case "receipt":
				r.ReceiptSHA256 = [32]byte{}
			case "current-ref":
				r.CurrentObservation.ReferenceSHA256[0] ^= 1
			case "current-outcome":
				r.CurrentObservation.Outcome = transaction.FinalRollbackConfirmed
			case "prepared":
				r.Reviewed.Decision = transaction.Unknown
			case "notice-proof":
				r.Reviewed.Notice.FirstEvidenceSHA256 = [32]byte{}
			case "already-resolved-input":
				r.Reviewed.Notice.Status = "resolved"
			}
			result, e := reader.ResolveNotice(context.Background(), r)
			if !errors.Is(e, ErrResolution) || result.Outcome != GovernanceNotAttempted {
				t.Fatal("invalid input reached primary or claimed a commit")
			}
		})
	}
}

func TestResolutionRejectsDriftedPrimaryReferenceOrFirstNotice(t *testing.T) {
	s, _ := snapshotFixture(t)
	r := storageResolutionFixture(t, s)
	old := time.Unix(1, 0).UTC()
	for _, scenario := range []string{"database", "binding", "reference", "decision", "notice-key", "index", "first-proof", "positive-outcome", "positive-time"} {
		t.Run(scenario, func(t *testing.T) {
			current := s
			current.BeforeFinal = r.expected()
			current.BeforeFinalAt = &old
			switch scenario {
			case "database":
				current.DatabaseIdentitySHA256[0] ^= 1
			case "binding":
				current.Binding.StoreID = "different"
			case "reference":
				current.Reference.Fence++
			case "decision":
				current.Decision = transaction.Rollback
			case "notice-key":
				current.Notice.Key[0] ^= 1
			case "index":
				current.Notice.IndexSHA256[0] ^= 1
			case "first-proof":
				current.Notice.FirstEvidenceSHA256[0] ^= 1
			case "positive-outcome":
				current.BeforeFinal = transaction.FinalUnknown
			case "positive-time":
				current.BeforeFinalAt = nil
			}
			if r.matches(current) {
				t.Fatal("drifted facts authorized governance change")
			}
		})
	}
}
