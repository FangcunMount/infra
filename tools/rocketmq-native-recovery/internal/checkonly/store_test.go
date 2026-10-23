package checkonly

import (
	"context"
	"crypto/sha256"
	"errors"
	"testing"
	"time"

	"github.com/FangcunMount/reliable-messaging/message"
	"github.com/FangcunMount/reliable-messaging/transaction"
)

type fakeAuthority struct {
	transaction.PreparedStore // Any unexpected delegation to execution panics.
	binding                   transaction.Binding
	evidence                  *transaction.Evidence
	calls                     []string
	fail                      error
	cancel                    context.CancelFunc
	firstPositiveAt           time.Time
}

func (f *fakeAuthority) Binding() transaction.Binding { return f.binding }
func (f *fakeAuthority) Validate(context.Context) error {
	f.calls = append(f.calls, "validate")
	return nil
}
func (f *fakeAuthority) Evidence(context.Context, transaction.Reference) (*transaction.Evidence, error) {
	f.calls = append(f.calls, "evidence")
	return f.evidence, f.fail
}
func (f *fakeAuthority) RecordRecoveryFinal(context.Context, transaction.Reference, transaction.FinalOutcome) error {
	f.calls = append(f.calls, "base_post_rpc_audit")
	if f.fail != nil {
		return f.fail
	}
	if f.firstPositiveAt.IsZero() {
		f.firstPositiveAt = time.Unix(1, 0).UTC()
	}
	if f.cancel != nil {
		f.cancel()
	}
	return nil
}
func fixture(t *testing.T) (*fakeAuthority, transaction.Reference) {
	t.Helper()
	m, err := message.New(message.Input{Producer: "unit", ID: "frozen", Destination: "unit.logical", EventType: "changed", SchemaVersion: "v1", Scope: "org:7", ContentType: "application/octet-stream", OccurredAt: "2026-10-24T00:00:00Z", Payload: []byte{0, 255, 1}})
	if err != nil {
		t.Fatal(err)
	}
	b := transaction.Binding{Owner: "ai.mysql", StoreID: "original", WriterEpoch: "m3-1"}
	p, err := transaction.NewPlan(transaction.PlanInput{Owner: b.Owner, Scope: "org:7", OperationID: "original-op", IdempotencyKey: "original-key", InputHash: sha256.Sum256([]byte("input")), Branches: []transaction.BranchInput{{ID: "fact", PhysicalTopic: "unit.physical", RouteRevision: "m3-1", Message: m, Wire: []byte{0, 255, 2}}}})
	if err != nil {
		t.Fatal(err)
	}
	e := transaction.Execution{Plan: p, WriterEpoch: b.WriterEpoch, Fence: 1, Token: [32]byte{1}, LeaseUntil: time.Now().UTC().Add(time.Hour)}
	ref := e.References()[0]
	return &fakeAuthority{binding: b, evidence: &transaction.Evidence{Reference: ref, ExecutionState: transaction.Committed, BranchState: transaction.Committed}}, ref
}
func TestConstructorAndForbiddenExecutionHaveNoAuthoritySideEffects(t *testing.T) {
	base, ref := fixture(t)
	store, err := New(base, ref, transaction.FinalCommitConfirmed, func(context.Context, Event) error { return nil })
	if err != nil {
		t.Fatal(err)
	}
	if len(base.calls) != 0 {
		t.Fatal("constructor performed work")
	}
	ctx := context.Background()
	if _, err = store.Lookup(ctx, transaction.Request{}); !errors.Is(err, ErrCapability) {
		t.Fatal(err)
	}
	if _, err = store.Reserve(ctx, transaction.Request{}, transaction.FrozenPlan{}, transaction.ReserveOptions{}); !errors.Is(err, ErrCapability) {
		t.Fatal(err)
	}
	if err = store.BeginPrepare(ctx, transaction.Execution{}); !errors.Is(err, ErrCapability) {
		t.Fatal(err)
	}
	if _, err = store.Abort(ctx, transaction.Execution{}); !errors.Is(err, ErrCapability) {
		t.Fatal(err)
	}
	if err = store.RecordHalf(ctx, transaction.Execution{}, ref, transaction.HalfReceipt{}); !errors.Is(err, ErrCapability) {
		t.Fatal(err)
	}
	if err = store.RecordFinal(ctx, transaction.Execution{}, ref, transaction.FinalCommitConfirmed, ""); !errors.Is(err, ErrCapability) {
		t.Fatal(err)
	}
	if n, err := store.ReconcileOnce(ctx, 100); err != nil || n != 0 {
		t.Fatal(n, err)
	}
	if len(base.calls) != 0 {
		t.Fatal("delegated execution/maintenance")
	}
}
func TestFakePostRPCCallbackPreservesFirstAuditButObservesEveryInvocation(t *testing.T) {
	base, ref := fixture(t)
	count := 0
	raw, err := transaction.EncodeReference(ref)
	if err != nil {
		t.Fatal(err)
	}
	store, err := New(base, ref, transaction.FinalCommitConfirmed, func(ctx context.Context, event Event) error {
		if _, ok := ctx.Deadline(); !ok {
			t.Fatal("unbounded audit callback")
		}
		if event.ReferenceSHA256 != sha256.Sum256(raw) || event.Outcome != transaction.FinalCommitConfirmed {
			t.Fatal("private observation identity differs")
		}
		if base.firstPositiveAt.IsZero() {
			t.Fatal("sink ran before original SDK audit")
		}
		count++
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	for range 2 {
		if err := store.RecordRecoveryFinal(context.Background(), ref, transaction.FinalCommitConfirmed); err != nil {
			t.Fatal(err)
		}
	}
	if count != 2 || len(base.calls) != 2 || !base.firstPositiveAt.Equal(time.Unix(1, 0).UTC()) {
		t.Fatal("first DB time overwritten or current callback discarded")
	}
}
func TestFakeFailedOrCancelledOriginalAuditCreatesNoObservation(t *testing.T) {
	for _, mode := range []string{"error", "cancel"} {
		t.Run(mode, func(t *testing.T) {
			base, ref := fixture(t)
			count := 0
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			if mode == "error" {
				base.fail = errors.New("owned fake failure")
			} else {
				base.cancel = cancel
			}
			store, err := New(base, ref, transaction.FinalCommitConfirmed, func(context.Context, Event) error { count++; return nil })
			if err != nil {
				t.Fatal(err)
			}
			if err = store.RecordRecoveryFinal(ctx, ref, transaction.FinalCommitConfirmed); err == nil || count != 0 {
				t.Fatal("missing/failed audit became positive proof")
			}
		})
	}
}
func TestTargetDriftIsUnknownBeforeConfirmation(t *testing.T) {
	base, ref := fixture(t)
	store, err := New(base, ref, transaction.FinalCommitConfirmed, func(context.Context, Event) error { return nil })
	if err != nil {
		t.Fatal(err)
	}
	base.evidence.ExecutionState, base.evidence.BranchState = transaction.Aborted, transaction.Aborted
	if _, err = store.Evidence(context.Background(), ref); !errors.Is(err, ErrEvidenceChanged) {
		t.Fatal("changed approved outcome accepted", err)
	}
	if err = store.RecordRecoveryFinal(context.Background(), ref, transaction.FinalRollbackConfirmed); !errors.Is(err, ErrEvidenceChanged) {
		t.Fatal("mismatched outcome accepted", err)
	}
	if len(base.calls) != 1 || base.calls[0] != "evidence" {
		t.Fatal("drift wrote audit")
	}
}
func TestBlockingPrivateSinkRetainsInvocationAfterCancellation(t *testing.T) {
	base, ref := fixture(t)
	entered, release, done := make(chan struct{}), make(chan struct{}), make(chan error, 1)
	store, err := New(base, ref, transaction.FinalCommitConfirmed, func(context.Context, Event) error { close(entered); <-release; return nil })
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go func() { done <- store.RecordRecoveryFinal(ctx, ref, transaction.FinalCommitConfirmed) }()
	<-entered
	cancel()
	select {
	case <-done:
		t.Fatal("capacity released while I/O still running")
	case <-time.After(10 * time.Millisecond):
	}
	close(release)
	select {
	case err := <-done:
		if !errors.Is(err, context.Canceled) {
			t.Fatal(err)
		}
	case <-time.After(time.Second):
		t.Fatal("fake I/O did not drain")
	}
}
