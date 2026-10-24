// Package receipt validates a private, drained per-invocation SDK observation
// graph. It never upgrades an old DB audit timestamp into a current RPC, grants
// permission, reads message bodies or writes protocol/governance state.
package receipt

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"syscall"
	"time"

	"fangcunmount.infra/rocketmq-native-recovery/internal/checkonly"
	"fangcunmount.infra/rocketmq-native-recovery/internal/observation"
	"fangcunmount.infra/rocketmq-native-recovery/internal/privatefile"
	"fangcunmount.infra/rocketmq-native-recovery/internal/review"
	"github.com/FangcunMount/reliable-messaging/transport/rocketmq"
)

type Receipt struct {
	Schema                string             `json:"schema"`
	RequestSHA            string             `json:"request_sha256"`
	SourceSHA             string             `json:"source_sha"`
	BinarySHA             string             `json:"binary_sha256"`
	Nonce                 string             `json:"invocation_nonce"`
	CoordinatorBindingSHA string             `json:"coordinator_binding_sha256"`
	StepPlanSHA           string             `json:"step_plan_sha256"`
	StartedAt             time.Time          `json:"started_at"`
	CompletedAt           time.Time          `json:"completed_at"`
	ObservationDirectory  string             `json:"observation_directory"`
	Observations          []observation.File `json:"observations"`
	// SDK stats are opaque canonical JSON, like the frozen SDK Reference. This
	// preserves its exact fixed-version encoding without relaxing strict keys
	// on the enclosing approval/receipt protocol.
	RuntimeStats  string `json:"runtime_stats"`
	InspectionSHA string `json:"inspection_sha256"`
	NativeSHA     string `json:"native_recheck_sha256"`
	NativeOutcome string `json:"native_recheck_outcome"`
}

func OwnedDirectory(path string) bool {
	if !filepath.IsAbs(path) || filepath.Clean(path) != path {
		return false
	}
	i, err := os.Lstat(path)
	if err != nil || !i.IsDir() || i.Mode().Perm() != 0700 {
		return false
	}
	s, ok := i.Sys().(*syscall.Stat_t)
	return ok && s.Uid == uint32(os.Geteuid()) && s.Mode&(syscall.S_ISUID|syscall.S_ISGID|syscall.S_ISVTX) == 0
}

func (r Receipt) Validate(request review.Request, requestSHA [32]byte, now time.Time) (event checkonly.Event, err error) {
	if request.Validate(request.CreatedAt) != nil || requestSHA == [32]byte{} || r.Schema != "m3-native-recovery-receipt/v1" || r.RequestSHA != review.Hex(requestSHA) || r.SourceSHA != request.SourceSHA || r.BinarySHA != request.BinarySHA || r.Nonce != request.Nonce || r.StartedAt.Before(request.CreatedAt) || !r.StartedAt.Before(request.ExpiresAt) || r.CompletedAt.Before(r.StartedAt) || r.CompletedAt.After(request.ExpiresAt) || r.CompletedAt.After(now.Add(time.Minute)) || r.CompletedAt.Sub(r.StartedAt) > 4*time.Minute || !OwnedDirectory(r.ObservationDirectory) || len(r.Observations) < 1 || len(r.Observations) > 16 {
		return event, review.ErrReview
	}
	for _, v := range []string{r.CoordinatorBindingSHA, r.StepPlanSHA, r.InspectionSHA, r.NativeSHA} {
		if _, e := review.Digest(v); e != nil {
			return event, review.ErrReview
		}
	}
	if r.NativeOutcome != "RecheckEnqueued" && r.NativeOutcome != "Unknown" {
		return event, review.ErrReview
	}
	var stats rocketmq.TransactionStats
	if json.Unmarshal([]byte(r.RuntimeStats), &stats) != nil || checkonly.VerifyStats(stats) != nil {
		return event, review.ErrReview
	}
	canonical, e := json.Marshal(stats)
	if e != nil || !bytes.Equal(canonical, []byte(r.RuntimeStats)) {
		return event, review.ErrReview
	}
	root, e := os.OpenRoot(r.ObservationDirectory)
	if e != nil {
		return event, review.ErrReview
	}
	defer root.Close()
	// No unlisted or half-written observation can be omitted from the sealed
	// bundle, including a sticky sink failure after an earlier successful RPC.
	d, e := root.Open(".")
	if e != nil {
		return event, review.ErrReview
	}
	names, e := d.Readdirnames(17)
	closeErr := d.Close()
	if e != nil || closeErr != nil || len(names) != len(r.Observations) {
		return event, review.ErrReview
	}
	ref := review.Hex(review.ReferenceSHA(request))
	for i, f := range r.Observations {
		if f.Name != fmt.Sprintf("rpc-%02d.json", i+1) {
			return event, review.ErrReview
		}
		sum, e := review.Digest(f.SHA256)
		if e != nil {
			return event, review.ErrReview
		}
		raw, e := privatefile.ReadAt(root, f.Name)
		var observed observation.Record
		if e != nil || sha256.Sum256(raw) != sum || privatefile.Decode(raw, &observed) != nil || observed.Schema != "m3-native-current-rpc/v1" || observed.RequestSHA256 != r.RequestSHA || observed.InvocationNonce != r.Nonce || observed.SourceSHA != r.SourceSHA || observed.ReferenceSHA256 != ref || observed.Outcome != request.Expected() || observed.ObservedAt.Before(r.StartedAt) || observed.ObservedAt.After(r.CompletedAt) {
			return event, review.ErrReview
		}
	}
	positive := stats.RecoveryCommitConfirmed
	if request.Expected() == "rollback_confirmed" {
		positive = stats.RecoveryRollbackConfirmed
	}
	if positive < int64(len(r.Observations)) {
		return event, review.ErrReview
	}
	return checkonly.Event{ReferenceSHA256: review.ReferenceSHA(request), Outcome: request.Expected()}, nil
}

func Load(path string, expected [32]byte, request review.Request, requestSHA [32]byte, now time.Time) (r Receipt, event checkonly.Event, err error) {
	raw, err := privatefile.Read(path, expected)
	if err != nil || privatefile.Decode(raw, &r) != nil {
		return Receipt{}, event, review.ErrReview
	}
	event, err = r.Validate(request, requestSHA, now)
	if err != nil {
		return Receipt{}, checkonly.Event{}, review.ErrReview
	}
	return r, event, nil
}
