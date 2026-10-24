package review

import (
	"time"

	"fangcunmount.infra/rocketmq-native-recovery/internal/privatefile"
)

// Approval is explicitly authored/reviewed outside the helper. The CLI never
// auto-generates one. The frozen coordinator script independently pins its raw
// SHA and request SHA. Same-UID file possession is not an authentication system.
type Approval struct {
	Schema                string    `json:"schema"`
	Action                string    `json:"action"`
	RequestSHA            string    `json:"request_sha256"`
	ReceiptSHA            string    `json:"receipt_sha256"`
	CoordinatorBindingSHA string    `json:"coordinator_binding_sha256"`
	SourceBundleSHA       string    `json:"source_bundle_sha256"`
	DataOwner             string    `json:"data_owner"`
	RecoveryOwner         string    `json:"recovery_owner"`
	ExpiresAt             time.Time `json:"expires_at"`
}

func Approve(path string, expected [32]byte, request Request, requestSHA, receiptSHA, bindingSHA [32]byte, action string, now time.Time) error {
	expectedAction := action
	if action == "verify" {
		expectedAction = "resolve"
	}
	raw, err := privatefile.Read(path, expected)
	var a Approval
	if err != nil || privatefile.Decode(raw, &a) != nil || request.Validate(now) != nil || requestSHA == [32]byte{} || bindingSHA == [32]byte{} || a.Schema != "m3-native-recovery-approval/v1" || a.Action != expectedAction || a.RequestSHA != Hex(requestSHA) || a.CoordinatorBindingSHA != Hex(bindingSHA) || a.SourceBundleSHA != request.SourceBundleSHA || a.DataOwner != request.DataOwner || a.RecoveryOwner != request.RecoveryOwner || !a.ExpiresAt.After(now) || a.ExpiresAt.After(request.ExpiresAt) {
		return ErrReview
	}
	switch action {
	case "check", "recover":
		if receiptSHA != [32]byte{} || a.ReceiptSHA != "" {
			return ErrReview
		}
	case "resolve", "verify":
		// Verify uses the same approval and immutable receipt as Resolve, so an
		// uncertain governance commit never requires inventing a new RPC.
		if receiptSHA == [32]byte{} || a.ReceiptSHA != Hex(receiptSHA) {
			return ErrReview
		}
	default:
		return ErrReview
	}
	return nil
}
