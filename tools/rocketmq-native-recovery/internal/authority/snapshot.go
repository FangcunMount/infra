// Package authority reads exact original-primary facts for an independently
// reviewed recovery operation. It never borrows an execution token or wire.
package authority

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"errors"
	"strings"
	"time"

	"github.com/FangcunMount/reliable-messaging/transaction"
	"github.com/FangcunMount/reliable-messaging/transport"
)

var ErrSnapshot = errors.New("exact terminal primary recovery snapshot required")

type Locator struct {
	OperationID, BranchID string
	Fence                 uint64
}

func (l Locator) valid() bool {
	return strings.TrimSpace(l.OperationID) != "" && strings.TrimSpace(l.BranchID) != "" && len(l.OperationID) <= 4096 && len(l.BranchID) <= 4096 && l.Fence > 0 && l.Fence <= transaction.MaxFence
}

type Notice struct {
	Key, IndexSHA256, FirstEvidenceSHA256 [32]byte
	Status                                string
	ResolvedAt                            *time.Time
	ResolutionReceiptSHA256               []byte
}

// Snapshot is private review input, not RPC success or clearance. BeforeFinalAt
// can remain unchanged through a fresh positive SDK recovery callback.
type Snapshot struct {
	Binding                transaction.Binding
	Reference              transaction.Reference
	DatabaseIdentitySHA256 [32]byte
	Decision               transaction.Decision
	Half                   transaction.HalfOutcome
	BeforeFinal            transaction.FinalOutcome
	BeforeFinalAt          *time.Time
	Notice                 Notice
}

// ValidateReview validates a terminal snapshot as review input. It establishes
// neither that a database was read nor that a Broker RPC or approval occurred.
func ValidateReview(s Snapshot) error {
	state := transaction.Committed
	if s.Decision == transaction.Rollback {
		state = transaction.Aborted
	} else if s.Decision != transaction.Commit {
		return ErrSnapshot
	}
	return validateSnapshot(s, Locator{s.Reference.OperationID, s.Reference.BranchID, s.Reference.Fence}, state, state, "")
}

func validBinding(b transaction.Binding, mongo bool) bool {
	if !b.Valid() || len(b.Owner) > 128 || len(b.StoreID) > 128 || len(b.WriterEpoch) > 128 {
		return false
	}
	if mongo {
		return b.Owner == "qs.mongo"
	}
	return b.Owner == "iam.mysql" || b.Owner == "qs.mysql" || b.Owner == "ai.mysql"
}

// NoticeKey preserves the host v1 length framing, including every identity byte.
func NoticeKey(b transaction.Binding, index [32]byte) [32]byte {
	h := sha256.New()
	_, _ = h.Write([]byte("m3-native-limit-notice-v1\x00"))
	for _, v := range [][]byte{[]byte(b.Owner), []byte(b.StoreID), []byte(b.WriterEpoch), []byte("m3-1"), index[:]} {
		var n [4]byte
		binary.BigEndian.PutUint32(n[:], uint32(len(v)))
		_, _ = h.Write(n[:])
		_, _ = h.Write(v)
	}
	var out [32]byte
	copy(out[:], h.Sum(nil))
	return out
}

func databaseIdentity(kind string, fields ...string) [32]byte {
	h := sha256.New()
	_, _ = h.Write([]byte("m3-native-primary-" + kind + "-v1\x00"))
	for _, v := range fields {
		var n [4]byte
		binary.BigEndian.PutUint32(n[:], uint32(len(v)))
		_, _ = h.Write(n[:])
		_, _ = h.Write([]byte(v))
	}
	var out [32]byte
	copy(out[:], h.Sum(nil))
	return out
}

func validateSnapshot(s Snapshot, locator Locator, execution, branch transaction.State, finalError string) error {
	r := s.Reference
	b := s.Binding
	if !locator.valid() || !validBinding(b, b.Owner == "qs.mongo") || !r.Valid() || r.Owner != b.Owner || r.WriterEpoch != b.WriterEpoch || r.OperationID != locator.OperationID || r.BranchID != locator.BranchID || r.Fence != locator.Fence || r.RouteRevision != "m3-1" || s.DatabaseIdentitySHA256 == [32]byte{} || r.PlanDigest == [32]byte{} || r.WireHash == [32]byte{} || r.MessageFingerprint == [32]byte{} {
		return ErrSnapshot
	}
	expectedTopic, err := transport.PhysicalTopicV2(r.LogicalTopic, transport.TransactionMessageType, b.Owner, r.RouteRevision)
	if err != nil || r.PhysicalTopic != expectedTopic {
		return ErrSnapshot
	}
	decision := transaction.Resolve(r, &transaction.Evidence{Reference: r, ExecutionState: execution, BranchState: branch})
	if decision == transaction.Unknown || s.Decision != decision {
		return ErrSnapshot
	}
	positive := transaction.FinalCommitConfirmed
	if decision == transaction.Rollback {
		positive = transaction.FinalRollbackConfirmed
	}
	switch s.BeforeFinal {
	case transaction.FinalNotAttempted, transaction.FinalUnknown:
	case positive:
		if s.BeforeFinalAt == nil || s.BeforeFinalAt.IsZero() || finalError != "" {
			return ErrSnapshot
		}
	default:
		return ErrSnapshot
	}
	switch s.Half {
	case transaction.HalfNotAttempted, transaction.HalfPrepared, transaction.HalfRejected, transaction.HalfUnknown:
	default:
		return ErrSnapshot
	}
	n := s.Notice
	if n.IndexSHA256 == [32]byte{} || n.FirstEvidenceSHA256 == [32]byte{} || n.Key != NoticeKey(b, n.IndexSHA256) {
		return ErrSnapshot
	}
	switch n.Status {
	case "blocked":
		if n.ResolvedAt != nil || n.ResolutionReceiptSHA256 != nil {
			return ErrSnapshot
		}
	case "resolved":
		if n.ResolvedAt == nil || n.ResolvedAt.IsZero() || len(n.ResolutionReceiptSHA256) != 32 || bytes.Equal(n.ResolutionReceiptSHA256, make([]byte, 32)) {
			return ErrSnapshot
		}
	default:
		return ErrSnapshot
	}
	return nil
}
