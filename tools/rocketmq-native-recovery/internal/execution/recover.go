package execution

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	platform "runtime"
	"time"

	"fangcunmount.infra/rocketmq-native-recovery/internal/authority"
	"fangcunmount.infra/rocketmq-native-recovery/internal/checkonly"
	"fangcunmount.infra/rocketmq-native-recovery/internal/connection"
	"fangcunmount.infra/rocketmq-native-recovery/internal/nativeadmin"
	"fangcunmount.infra/rocketmq-native-recovery/internal/observation"
	"fangcunmount.infra/rocketmq-native-recovery/internal/receipt"
	"fangcunmount.infra/rocketmq-native-recovery/internal/review"
	"github.com/FangcunMount/reliable-messaging/transaction"
	"github.com/FangcunMount/reliable-messaging/transport/rocketmq"
)

var ErrIncomplete = errors.New("recovery incomplete; retain private attempt and exact unresolved responsibilities")

type Result struct {
	Schema        string                      `json:"schema"`
	ReceiptPath   string                      `json:"receipt_path,omitempty"`
	ReceiptSHA    string                      `json:"receipt_sha256,omitempty"`
	NativeOutcome string                      `json:"native_recheck_outcome"`
	Final         transaction.FinalOutcome    `json:"broker_final_outcome"`
	Governance    authority.GovernanceOutcome `json:"governance_outcome"`
}

// Dependencies exist only to verify orchestration with explicitly named fakes.
// Recover always supplies the real constructors; no CLI option selects fakes.
type runtime interface {
	Start(context.Context) error
	Close(context.Context) error
	Wait(context.Context) error
	Stats() rocketmq.TransactionStats
	VerifyDrained() error
}
type admin interface {
	Run(context.Context, review.Request, [32]byte, string, string) (nativeadmin.Report, [32]byte, error)
}
type dependencies struct {
	open    func(context.Context, connection.Config) (connection.Opened, error)
	native  func(connection.Config) (admin, error)
	runtime func(rocketmq.TransactionConfig, transaction.PreparedStore, transaction.Reference, transaction.FinalOutcome, checkonly.Sink) (runtime, error)
}

func Recover(ctx context.Context, in Input) (Result, error) {
	if platform.GOOS != "linux" {
		return Result{}, review.ErrReview
	}
	return recoverWith(ctx, in, dependencies{open: connection.Open, native: func(c connection.Config) (admin, error) { return nativeadmin.New(c) }, runtime: func(c rocketmq.TransactionConfig, s transaction.PreparedStore, r transaction.Reference, o transaction.FinalOutcome, sink checkonly.Sink) (runtime, error) {
		return checkonly.NewRuntime(c, s, r, o, sink)
	}})
}

func recoverWith(ctx context.Context, in Input, deps dependencies) (result Result, err error) {
	result = Result{Schema: "m3-native-recovery-result/v1", NativeOutcome: "NotAttempted", Final: transaction.FinalUnknown, Governance: authority.GovernanceNotAttempted}
	started := time.Now().UTC()
	v, err := load(in, "recover", started)
	if err != nil || v.issued.TimeoutSeconds() < 240 || v.request.ExpiresAt.Sub(started) < 4*time.Minute {
		return result, review.ErrReview
	}
	r := v.request
	// Exclusive durable claim is consumed before any network/start operation.
	// A crashed/unknown attempt needs explicit new review, never silent reuse.
	claim := filepath.Join(in.Barrier.Directory, "native-recovery-claim-"+review.Hex(in.Request.SHA256)+".json")
	if _, err = review.Write(claim, map[string]string{"schema": "m3-native-recovery-claim/v1", "request_sha256": review.Hex(in.Request.SHA256), "invocation_nonce": r.Nonce, "binding_sha256": review.Hex(in.Barrier.BindingSHA256), "step_plan_sha256": review.Hex(in.Barrier.StepPlanSHA256)}); err != nil {
		return result, review.ErrReview
	}
	work, err := os.MkdirTemp(in.Barrier.Directory, "native-attempt-")
	if err != nil {
		return result, ErrIncomplete
	}
	managed, err := deps.native(v.config)
	if err != nil {
		return result, ErrIncomplete
	}
	owned, err := deps.open(ctx, v.config)
	if err != nil {
		return result, ErrIncomplete
	}
	closed := false
	mayClose := true
	defer func() {
		if mayClose && !closed {
			if owned.Close() != nil {
				err = ErrIncomplete
				result.ReceiptPath = ""
				result.ReceiptSHA = ""
			}
		}
	}()
	s, err := r.Snapshot.Authority()
	if err != nil {
		return result, ErrIncomplete
	}
	locator := authority.Locator{OperationID: s.Reference.OperationID, BranchID: s.Reference.BranchID, Fence: s.Reference.Fence}
	current, err := owned.Authority.Snapshot(ctx, locator, s.Notice.IndexSHA256)
	if err != nil || connection.Match(r, current) != nil || current.Notice.Status != "blocked" {
		return result, ErrIncomplete
	}
	if stillIssued(in, r) != nil {
		return result, ErrIncomplete
	}
	_, inspectionSHA, err := managed.Run(ctx, r, in.Request.SHA256, "inspect", work)
	if err != nil {
		return result, ErrIncomplete
	}
	store, err := owned.Authority.CheckStore()
	if err != nil {
		return result, ErrIncomplete
	}
	nonce, _ := review.Digest(r.Nonce)
	source, _ := hex.DecodeString(r.SourceSHA)
	var sourceBytes [20]byte
	copy(sourceBytes[:], source)
	recorder, err := observation.New(work, observation.Identity{RequestSHA256: in.Request.SHA256, Nonce: nonce, ReferenceSHA256: review.ReferenceSHA(r), SourceSHA: sourceBytes, Outcome: r.Expected()})
	if err != nil {
		return result, ErrIncomplete
	}
	tls, err := v.config.TLS()
	if err != nil {
		_, _ = recorder.Close()
		return result, ErrIncomplete
	}
	checker, err := deps.runtime(rocketmq.TransactionConfig{Endpoint: v.config.Endpoint, AccessKey: v.config.AccessKey, SecretKey: v.config.SecretKey, TLS: tls, Owner: v.config.Owner, Routes: v.routes}, store, s.Reference, r.Expected(), recorder.Sink)
	if err != nil {
		_, _ = recorder.Close()
		return result, ErrIncomplete
	}
	if stillIssued(in, r) != nil {
		_, _ = recorder.Close()
		return result, ErrIncomplete
	}
	// A short-lived runtime owns its pool. Never close that pool or seal the
	// observation while actual SDK callbacks/RPC are still running.
	mayClose = false
	startErr := checker.Start(ctx)
	var nativeSHA [32]byte
	var nativeErr error
	if startErr == nil && stillIssued(in, r) == nil {
		nativeReport, sum, e := managed.Run(ctx, r, in.Request.SHA256, "resume", work)
		nativeErr = e
		nativeSHA = sum
		if e == nil {
			result.NativeOutcome = nativeReport.Outcome
		}
		if e == nil {
			wait, cancel := context.WithTimeout(ctx, 90*time.Second)
			select {
			case <-recorder.First():
			case <-wait.Done():
				nativeErr = ErrIncomplete
			}
			cancel()
		}
	} else {
		nativeErr = ErrIncomplete
	}
	drain, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	closeErr := checker.Close(drain)
	if closeErr != nil {
		closeErr = checker.Wait(drain)
	}
	cancel()
	if !checker.Stats().Stopped {
		return result, ErrIncomplete
	} // Keep the owned pool open until process termination; never claim drain.
	mayClose = true
	files, observationErr := recorder.Close()
	if errors.Join(startErr, nativeErr, closeErr, observationErr, checker.VerifyDrained(), ctx.Err()) != nil {
		return result, ErrIncomplete
	}
	current, err = owned.Authority.Snapshot(ctx, locator, s.Notice.IndexSHA256)
	if err != nil || connection.Match(r, current) != nil || current.BeforeFinal != r.Expected() || current.BeforeFinalAt == nil {
		return result, ErrIncomplete
	}
	if owned.Close() != nil {
		closed = true
		return result, ErrIncomplete
	}
	closed = true
	stats, err := json.Marshal(checker.Stats())
	if err != nil {
		return result, ErrIncomplete
	}
	sealed := receipt.Receipt{Schema: "m3-native-recovery-receipt/v1", RequestSHA: review.Hex(in.Request.SHA256), SourceSHA: r.SourceSHA, BinarySHA: r.BinarySHA, Nonce: r.Nonce, CoordinatorBindingSHA: review.Hex(in.Barrier.BindingSHA256), StepPlanSHA: review.Hex(in.Barrier.StepPlanSHA256), StartedAt: started, CompletedAt: time.Now().UTC(), ObservationDirectory: recorder.Directory(), Observations: files, RuntimeStats: string(stats), InspectionSHA: review.Hex(inspectionSHA), NativeSHA: review.Hex(nativeSHA), NativeOutcome: result.NativeOutcome}
	if _, err = sealed.Validate(r, in.Request.SHA256, time.Now().UTC()); err != nil || nativeadmin.CheckReports(work, sealed, r, in.Request.SHA256) != nil {
		return result, ErrIncomplete
	}
	path := filepath.Join(work, "receipt.json")
	sum, err := review.Write(path, sealed)
	if err != nil {
		return result, ErrIncomplete
	}
	result.ReceiptPath, result.ReceiptSHA, result.Final = path, review.Hex(sum), r.Expected()
	return result, nil
}
