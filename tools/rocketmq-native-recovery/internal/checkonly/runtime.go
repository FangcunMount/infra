package checkonly

import (
	"context"
	"errors"
	"time"

	"github.com/FangcunMount/reliable-messaging/transaction"
	"github.com/FangcunMount/reliable-messaging/transport/rocketmq"
)

type sdkRuntime interface {
	transaction.Runtime
	Stats() rocketmq.TransactionStats
}

// Runtime deliberately exposes no Sender or execution capability. The fixed
// SDK's StopAdmission before Start would refuse startup; therefore Store denies
// execution from construction, and Start seals SDK admission immediately on
// return (including failure). Only the private SDK owns the post-RPC callback.
type Runtime struct{ sdk sdkRuntime }

func NewRuntime(config rocketmq.TransactionConfig, base transaction.PreparedStore, target transaction.Reference, outcome transaction.FinalOutcome, sink Sink) (*Runtime, error) {
	store, err := New(base, target, outcome, sink)
	if err != nil {
		return nil, err
	}
	matched := false
	for _, route := range config.Routes {
		if route.PhysicalTopic == target.PhysicalTopic && route.LogicalTopic == target.LogicalTopic && route.Revision == target.RouteRevision {
			matched = true
		}
	}
	if !matched {
		return nil, transaction.ErrBinding
	}
	limits := transaction.DefaultLimits()
	limits.Sends, limits.CheckWorkers, limits.CheckQueue = 1, 1, 4
	limits.CheckTimeout, limits.RPCTimeout = 2*time.Second, 5*time.Second
	config.Limits = limits
	sdk, err := rocketmq.NewTransactionalSender(config, store)
	if err != nil {
		return nil, err
	}
	return &Runtime{sdk}, nil
}

func (r *Runtime) Start(ctx context.Context) error {
	defer r.sdk.StopAdmission()
	return r.sdk.Start(ctx)
}
func (r *Runtime) Close(ctx context.Context) error  { return r.sdk.Close(ctx) }
func (r *Runtime) Wait(ctx context.Context) error   { return r.sdk.Wait(ctx) }
func (r *Runtime) Stats() rocketmq.TransactionStats { return r.sdk.Stats() }

var ErrRuntimeProof = errors.New("check-only runtime has not drained with a positive audited recovery")

// VerifyDrained must precede sealing the private observation bundle. A positive
// observation alone cannot disguise unfinished work, missing SDK audit, a new
// send/local callback, or failed confirmation in this owned instance.
func (r *Runtime) VerifyDrained() error {
	s := r.sdk.Stats()
	if !s.Stopped || s.Ready || s.ActiveSends != 0 || s.RunningChecks != 0 || s.QueuedChecks != 0 ||
		s.RecoveryAuditRecorded < 1 || s.RecoveryAuditRecorded != s.RecoveryCommitConfirmed+s.RecoveryRollbackConfirmed ||
		s.RecoveryRPCFailed != 0 || s.RecoveryAuditErrors != 0 || s.RecoveryAuditUnsupported != 0 ||
		s.CompletedResults != 0 || s.HalfPreparedResults != 0 || s.HalfRejectedResults != 0 || s.HalfUnknownResults != 0 ||
		s.LocalCommittedResults != 0 || s.LocalAbortedResults != 0 || s.LocalUnknownResults != 0 ||
		s.FinalCommitResults != 0 || s.FinalRollbackResults != 0 || s.FinalUnknownResults != 0 ||
		s.Reconciled != 0 || s.CallbackErrors != 0 || s.InvalidChecks != 0 || s.DatabaseErrors != 0 {
		return ErrRuntimeProof
	}
	return nil
}
