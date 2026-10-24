package execution

import (
	"context"
	"path/filepath"
	platform "runtime"
	"time"

	"fangcunmount.infra/rocketmq-native-recovery/internal/authority"
	"fangcunmount.infra/rocketmq-native-recovery/internal/connection"
	"fangcunmount.infra/rocketmq-native-recovery/internal/nativeadmin"
	"fangcunmount.infra/rocketmq-native-recovery/internal/receipt"
	"fangcunmount.infra/rocketmq-native-recovery/internal/review"
	"github.com/FangcunMount/reliable-messaging/transaction"
)

// Resolve independently validates the exact approved immutable receipt and
// fresh original database before touching governance. No SDK starts here and
// an uncertain governance COMMIT remains Unknown, distinct from Broker final.
func Resolve(ctx context.Context, in Input, verifyOnly bool) (result Result, err error) {
	if platform.GOOS != "linux" {
		return result, review.ErrReview
	}
	result = Result{Schema: "m3-native-recovery-result/v1", Stage: "review", NativeOutcome: "NotAttempted", Final: transaction.FinalUnknown, Governance: authority.GovernanceNotAttempted}
	action := "resolve"
	if verifyOnly {
		action = "verify"
	}
	v, err := load(in, action, time.Now().UTC())
	if err != nil {
		return result, review.ErrReview
	}
	r := v.request
	result.Stage = "recorded_rpc_receipt"
	sealed, event, err := receipt.Load(in.Receipt.Path, in.Receipt.SHA256, r, in.Request.SHA256, time.Now().UTC())
	if err != nil || sealed.CoordinatorBindingSHA != review.Hex(in.Barrier.BindingSHA256) || nativeadmin.CheckReports(filepath.Dir(in.Receipt.Path), sealed, r, in.Request.SHA256) != nil {
		return result, review.ErrReview
	}
	s, err := r.Snapshot.Authority()
	if err != nil {
		return result, review.ErrReview
	}
	resolution := authority.Resolution{Reviewed: s, RequestSHA256: in.Request.SHA256, ReceiptSHA256: in.Receipt.SHA256, CurrentObservation: event}
	result.Stage = "original_primary"
	owned, err := connection.Open(ctx, v.config)
	if err != nil {
		return result, ErrIncomplete
	}
	defer func() {
		if owned.Close() != nil {
			err = ErrIncomplete
		}
	}()
	result.NativeOutcome, result.Final = sealed.NativeOutcome, r.Expected()
	issuedErr := stillIssued(in, r)
	if verifyOnly {
		result.Stage = "fresh_governance_verify"
		issuedErr = issuedForRecordedRead(in, r)
	}
	if issuedErr != nil {
		return result, review.ErrReview
	}
	if verifyOnly {
		if err = owned.Authority.VerifyResolution(ctx, resolution); err != nil {
			return result, ErrIncomplete
		}
		result.Governance = authority.GovernanceAlreadyResolved
		return result, nil
	}
	result.Stage = "governance_commit"
	governance, e := owned.Authority.ResolveNotice(ctx, resolution)
	result.Governance = governance.Outcome
	if e != nil {
		return result, ErrIncomplete
	}
	result.Stage = "fresh_governance_verify"
	if err = owned.Authority.VerifyResolution(ctx, resolution); err != nil {
		return result, ErrIncomplete
	}
	return result, nil
}
