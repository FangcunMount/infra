package authority

import (
	"bytes"
	"crypto/sha256"
	"errors"

	"fangcunmount.infra/rocketmq-native-recovery/internal/checkonly"
	"github.com/FangcunMount/reliable-messaging/transaction"
)

var ErrResolution = errors.New("exact reviewed current-recovery evidence required")

// Resolution is a storage precondition, NOT an approval or RPC-success API.
// The eventual controlled CLI must independently validate the named approval,
// first-runtime barrier, full private receipt/nonce/source and genuine SDK
// observation before calling this lower-level primitive. Hashes alone are not
// permission. There is currently no production entrypoint for this operation.
type Resolution struct {
	Reviewed                     Snapshot
	RequestSHA256, ReceiptSHA256 [32]byte
	CurrentObservation           checkonly.Event
}

type GovernanceOutcome string

const (
	GovernanceNotAttempted    GovernanceOutcome = "not_attempted"
	GovernanceCommitted       GovernanceOutcome = "commit_confirmed"
	GovernanceUnknown         GovernanceOutcome = "unknown"
	GovernanceAlreadyResolved GovernanceOutcome = "already_resolved"
)

type ResolutionResult struct{ Outcome GovernanceOutcome }

func (r Resolution) locator() Locator {
	ref := r.Reviewed.Reference
	return Locator{ref.OperationID, ref.BranchID, ref.Fence}
}
func (r Resolution) expected() transaction.FinalOutcome {
	if r.Reviewed.Decision == transaction.Commit {
		return transaction.FinalCommitConfirmed
	}
	if r.Reviewed.Decision == transaction.Rollback {
		return transaction.FinalRollbackConfirmed
	}
	return transaction.FinalUnknown
}
func (r Resolution) valid() bool {
	s := r.Reviewed
	if r.RequestSHA256 == [32]byte{} || r.ReceiptSHA256 == [32]byte{} || s.Notice.Status != "blocked" || s.Notice.ResolvedAt != nil || s.Notice.ResolutionReceiptSHA256 != nil {
		return false
	}
	state, err := transaction.RecoveryFinalState(r.expected())
	if err != nil {
		return false
	}
	if validateSnapshot(s, r.locator(), state, state, "") != nil {
		return false
	}
	raw, err := transaction.EncodeReference(s.Reference)
	return err == nil && r.CurrentObservation.ReferenceSHA256 == sha256.Sum256(raw) && r.CurrentObservation.Outcome == r.expected()
}

func (r Resolution) matches(current Snapshot) bool {
	original := r.Reviewed
	if !r.valid() || current.Binding != original.Binding || current.DatabaseIdentitySHA256 != original.DatabaseIdentitySHA256 || current.Reference != original.Reference || current.Decision != original.Decision || current.Notice.Key != original.Notice.Key || current.Notice.IndexSHA256 != original.Notice.IndexSHA256 || current.Notice.FirstEvidenceSHA256 != original.Notice.FirstEvidenceSHA256 {
		return false
	}
	// Require an actual positive SDK audit on this fresh boundary, but never
	// demand a newer timestamp: the fixed SDK preserves its first positive time.
	if current.BeforeFinal != r.expected() || current.BeforeFinalAt == nil || current.BeforeFinalAt.IsZero() {
		return false
	}
	switch current.Notice.Status {
	case "blocked":
		return current.Notice.ResolvedAt == nil && current.Notice.ResolutionReceiptSHA256 == nil
	case "resolved":
		return current.Notice.ResolvedAt != nil && !current.Notice.ResolvedAt.IsZero() && bytes.Equal(current.Notice.ResolutionReceiptSHA256, r.ReceiptSHA256[:])
	default:
		return false
	}
}
