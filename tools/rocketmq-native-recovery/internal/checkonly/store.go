// Package checkonly restricts an embedded SDK instance to authority reads and
// genuine post-RPC protocol audit. It is not a business retry/transaction owner.
package checkonly

import (
	"context"
	"crypto/sha256"
	"errors"
	"time"

	"github.com/FangcunMount/reliable-messaging/transaction"
)

var ErrCapability = errors.New("check-only maintenance instance refuses execution")
var ErrEvidenceChanged = errors.New("approved terminal reference evidence changed")

// Event is a current SDK post-RPC observation, not local-commit or consumption
// authority. No wire, IDs, execution capability, or credentials are emitted.
type Event struct {
	ReferenceSHA256 [32]byte
	Outcome         transaction.FinalOutcome
}
type Sink func(context.Context, Event) error

// Store holds only the SDK interface, not an exposed SQL/Mongo adapter with
// Bind. All execution and reconciliation capabilities are disabled.
type Store struct {
	base     transaction.PreparedStore
	recorder transaction.RecoveryReceiptRecorder
	target   transaction.Reference
	expected transaction.FinalOutcome
	sink     Sink
}

func New(base transaction.PreparedStore, target transaction.Reference, outcome transaction.FinalOutcome, sink Sink) (*Store, error) {
	if base == nil || sink == nil || !target.Valid() || !base.Binding().Valid() || target.Owner != base.Binding().Owner || target.WriterEpoch != base.Binding().WriterEpoch {
		return nil, transaction.ErrBinding
	}
	if _, err := transaction.RecoveryFinalState(outcome); err != nil {
		return nil, err
	}
	recorder, ok := base.(transaction.RecoveryReceiptRecorder)
	if !ok {
		return nil, transaction.ErrBinding
	}
	return &Store{base, recorder, target, outcome, sink}, nil
}

var _ transaction.PreparedStore = (*Store)(nil)
var _ transaction.RecoveryReceiptRecorder = (*Store)(nil)

func (s *Store) Binding() transaction.Binding { return s.base.Binding() }

func budget(ctx context.Context) (context.Context, context.CancelFunc) {
	return context.WithTimeout(ctx, 2*time.Second)
}
func (s *Store) Validate(ctx context.Context) error {
	ctx, cancel := budget(ctx)
	defer cancel()
	return s.base.Validate(ctx)
}
func (s *Store) Evidence(ctx context.Context, ref transaction.Reference) (*transaction.Evidence, error) {
	if !ref.Valid() || ref.Owner != s.Binding().Owner {
		return nil, transaction.ErrBinding
	}
	ctx, cancel := budget(ctx)
	defer cancel()
	e, err := s.base.Evidence(ctx, ref)
	if err != nil {
		return nil, err
	}
	if ref == s.target {
		expected := transaction.Commit
		if s.expected == transaction.FinalRollbackConfirmed {
			expected = transaction.Rollback
		}
		if transaction.Resolve(ref, e) != expected {
			return nil, ErrEvidenceChanged
		}
	}
	return e, nil
}
func (*Store) Lookup(context.Context, transaction.Request) (transaction.Reservation, error) {
	return transaction.Reservation{}, ErrCapability
}
func (*Store) Reserve(context.Context, transaction.Request, transaction.FrozenPlan, transaction.ReserveOptions) (transaction.Reservation, error) {
	return transaction.Reservation{}, ErrCapability
}
func (*Store) BeginPrepare(context.Context, transaction.Execution) error { return ErrCapability }
func (*Store) Abort(context.Context, transaction.Execution) (bool, error) {
	return false, ErrCapability
}
func (*Store) RecordHalf(context.Context, transaction.Execution, transaction.Reference, transaction.HalfReceipt) error {
	return ErrCapability
}
func (*Store) RecordFinal(context.Context, transaction.Execution, transaction.Reference, transaction.FinalOutcome, string) error {
	return ErrCapability
}

// Maintenance remains the original host's responsibility. Zero means this
// explicitly read-only helper processed none, not that no Prepared rows exist.
func (*Store) ReconcileOnce(context.Context, int) (int, error) { return 0, nil }

// RecordRecoveryFinal is invoked ONLY by the fixed SDK after an actual positive
// RPC. The CLI must never call it to reconstruct missing confirmation evidence.
// A repeat can preserve the first DB audit timestamp and still produce a new
// per-invocation observation through this callback.
func (s *Store) RecordRecoveryFinal(ctx context.Context, ref transaction.Reference, outcome transaction.FinalOutcome) error {
	if !ref.Valid() || ref.Owner != s.Binding().Owner {
		return transaction.ErrBinding
	}
	if _, err := transaction.RecoveryFinalState(outcome); err != nil {
		return err
	}
	if ref == s.target && outcome != s.expected {
		return ErrEvidenceChanged
	}
	ctx, cancel := budget(ctx)
	defer cancel()
	if err := ctx.Err(); err != nil {
		return err
	}
	if err := s.recorder.RecordRecoveryFinal(ctx, ref, outcome); err != nil {
		return err
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	if ref == s.target {
		raw, err := transaction.EncodeReference(ref)
		if err != nil {
			return err
		}
		if err = s.sink(ctx, Event{sha256.Sum256(raw), outcome}); err != nil {
			return err
		}
	}
	return ctx.Err()
}
