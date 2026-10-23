package checkonly

import (
	"context"
	"errors"
	"reflect"
	"testing"

	"github.com/FangcunMount/reliable-messaging/transaction"
	"github.com/FangcunMount/reliable-messaging/transport"
	"github.com/FangcunMount/reliable-messaging/transport/rocketmq"
)

type fakeRuntime struct {
	stats rocketmq.TransactionStats
	calls []string
	err   error
}

func (f *fakeRuntime) Start(context.Context) error      { f.calls = append(f.calls, "start"); return f.err }
func (f *fakeRuntime) StopAdmission()                   { f.calls = append(f.calls, "stop_admission") }
func (f *fakeRuntime) Close(context.Context) error      { f.calls = append(f.calls, "close"); return f.err }
func (f *fakeRuntime) Wait(context.Context) error       { f.calls = append(f.calls, "wait"); return f.err }
func (f *fakeRuntime) Stats() rocketmq.TransactionStats { return f.stats }

func TestRuntimeSealsAdmissionAfterStartIncludingFailureWithoutHidingClose(t *testing.T) {
	for _, failure := range []error{nil, errors.New("controlled start failure")} {
		f := &fakeRuntime{err: failure}
		r := &Runtime{sdk: f}
		if !errors.Is(r.Start(context.Background()), failure) {
			t.Fatal("start failure changed")
		}
		if !reflect.DeepEqual(f.calls, []string{"start", "stop_admission"}) {
			t.Fatal("fixed SDK startup order changed", f.calls)
		}
		if !errors.Is(r.Close(context.Background()), failure) || !errors.Is(r.Wait(context.Background()), failure) {
			t.Fatal("close/wait failure hidden")
		}
	}
}

func TestRealConstructorOwnsNoExecutionAPIOrNetworkWork(t *testing.T) {
	base, ref := fixture(t)
	physical, err := transport.PhysicalTopicV2(ref.LogicalTopic, transport.TransactionMessageType, ref.Owner, ref.RouteRevision)
	if err != nil {
		t.Fatal(err)
	}
	ref.PhysicalTopic = physical
	config := rocketmq.TransactionConfig{Endpoint: "127.0.0.1:1", AccessKey: "unit", SecretKey: "unit", Owner: ref.Owner, Routes: []rocketmq.TransactionRoute{{LogicalTopic: ref.LogicalTopic, PhysicalTopic: physical, Revision: ref.RouteRevision}}}
	r, err := NewRuntime(config, base, ref, transaction.FinalCommitConfirmed, func(context.Context, Event) error { return nil })
	if err != nil || len(base.calls) != 0 {
		t.Fatal("constructor performed authority work", err)
	}
	if _, ok := any(r).(transaction.Sender); ok {
		t.Fatal("operator exposed sender")
	}
	if r.Stats().Ready || r.Stats().Stopped {
		t.Fatal("constructor started lifecycle")
	}
	config.Routes = nil
	if _, err = NewRuntime(config, base, ref, transaction.FinalCommitConfirmed, func(context.Context, Event) error { return nil }); !errors.Is(err, transaction.ErrBinding) {
		t.Fatal("target absent from reviewed routes accepted")
	}
}

func TestDrainedProofRefusesEveryUnfinishedOrExecutionSideEffect(t *testing.T) {
	clean := rocketmq.TransactionStats{Stopped: true, Stopping: true, RecoveryCommitConfirmed: 1, RecoveryAuditRecorded: 1, CheckCommit: 1}
	f := &fakeRuntime{stats: clean}
	r := &Runtime{sdk: f}
	if err := r.VerifyDrained(); err != nil {
		t.Fatal(err)
	}
	for _, mutate := range []func(*rocketmq.TransactionStats){
		func(s *rocketmq.TransactionStats) { s.Stopped = false }, func(s *rocketmq.TransactionStats) { s.Ready = true },
		func(s *rocketmq.TransactionStats) { s.ActiveSends = 1 }, func(s *rocketmq.TransactionStats) { s.RunningChecks = 1 }, func(s *rocketmq.TransactionStats) { s.QueuedChecks = 1 },
		func(s *rocketmq.TransactionStats) { s.RecoveryAuditRecorded = 0 }, func(s *rocketmq.TransactionStats) { s.RecoveryAuditRecorded = 2 },
		func(s *rocketmq.TransactionStats) { s.RecoveryRPCFailed = 1 }, func(s *rocketmq.TransactionStats) { s.RecoveryAuditErrors = 1 }, func(s *rocketmq.TransactionStats) { s.RecoveryAuditUnsupported = 1 },
		func(s *rocketmq.TransactionStats) { s.CompletedResults = 1 }, func(s *rocketmq.TransactionStats) { s.HalfPreparedResults = 1 }, func(s *rocketmq.TransactionStats) { s.HalfRejectedResults = 1 }, func(s *rocketmq.TransactionStats) { s.HalfUnknownResults = 1 },
		func(s *rocketmq.TransactionStats) { s.LocalCommittedResults = 1 }, func(s *rocketmq.TransactionStats) { s.LocalAbortedResults = 1 }, func(s *rocketmq.TransactionStats) { s.LocalUnknownResults = 1 },
		func(s *rocketmq.TransactionStats) { s.FinalCommitResults = 1 }, func(s *rocketmq.TransactionStats) { s.FinalRollbackResults = 1 }, func(s *rocketmq.TransactionStats) { s.FinalUnknownResults = 1 },
		func(s *rocketmq.TransactionStats) { s.Reconciled = 1 }, func(s *rocketmq.TransactionStats) { s.CallbackErrors = 1 }, func(s *rocketmq.TransactionStats) { s.InvalidChecks = 1 }, func(s *rocketmq.TransactionStats) { s.DatabaseErrors = 1 },
	} {
		f.stats = clean
		mutate(&f.stats)
		if !errors.Is(r.VerifyDrained(), ErrRuntimeProof) {
			t.Fatal("unfinished or impure runtime accepted")
		}
	}
}
