// Package nativeadmin executes only frozen, reviewed private script bytes. The
// operator must validate the actual coordinator barrier before invoking it.
// Native recheck is an internal copy/enqueue, never Commit/Rollback authority.
package nativeadmin

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"syscall"
	"time"

	"fangcunmount.infra/rocketmq-native-recovery/internal/connection"
	"fangcunmount.infra/rocketmq-native-recovery/internal/privatefile"
	"fangcunmount.infra/rocketmq-native-recovery/internal/receipt"
	"fangcunmount.infra/rocketmq-native-recovery/internal/review"
)

var ErrNative = errors.New("bounded exact physical native inspection/recheck incomplete")

type Request struct {
	Schema       string `json:"schema"`
	Mode         string `json:"mode"`
	RequestSHA   string `json:"request_sha256"`
	Nonce        string `json:"invocation_nonce"`
	SourceSHA    string `json:"source_sha"`
	IndexSHA     string `json:"native_index_sha256"`
	Nameserver   string `json:"nameserver"`
	Broker       string `json:"broker"`
	Topic        string `json:"source_topic"`
	Offset       int64  `json:"commitlog_offset"`
	QueueID      int64  `json:"queue_id"`
	QueueOffset  int64  `json:"queue_offset"`
	RealTopic    string `json:"expected_real_topic"`
	Owner        string `json:"expected_owner"`
	ReferenceSHA string `json:"expected_reference_sha256"`
	WireSHA      string `json:"expected_wire_sha256"`
	UniqueSHA    string `json:"expected_unique_id_sha256"`
	Retention    int    `json:"expected_retention_hours"`
	Revision     string `json:"expected_route_revision"`
}
type Report struct {
	Schema       string    `json:"schema"`
	Mode         string    `json:"mode"`
	RequestSHA   string    `json:"request_sha256"`
	Nonce        string    `json:"invocation_nonce"`
	SourceSHA    string    `json:"source_sha"`
	IndexSHA     string    `json:"native_index_sha256"`
	Outcome      string    `json:"outcome"`
	BodyExported *bool     `json:"body_exported"`
	ReferenceSHA string    `json:"reference_sha256"`
	WireSHA      string    `json:"wire_sha256"`
	UniqueSHA    string    `json:"unique_id_sha256"`
	Retention    int       `json:"retention_hours"`
	Remaining    int64     `json:"remaining_seconds"`
	BodyBytes    int64     `json:"body_bytes"`
	Shutdown     *bool     `json:"admin_shutdown_returned"`
	ObservedAt   time.Time `json:"observed_at"`
	FailureStage string    `json:"failure_stage,omitempty"`
	FailureKind  string    `json:"failure_kind,omitempty"`
}

type Runner struct {
	script []byte
	config connection.Config
}

func New(c connection.Config) (*Runner, error) {
	if c.Validate() != nil || c.AdminScript == "" {
		return nil, ErrNative
	}
	sum, err := review.Digest(c.AdminScriptSHA)
	if err != nil {
		return nil, ErrNative
	}
	raw, err := privatefile.Read(c.AdminScript, sum)
	if err != nil {
		return nil, ErrNative
	}
	return &Runner{append([]byte(nil), raw...), c}, nil
}
func makeRequest(r review.Request, sha [32]byte, mode string, c connection.Config) (Request, error) {
	s, err := r.Snapshot.Authority()
	if err != nil || r.Index.Fingerprint() == [32]byte{} || sha == [32]byte{} || (mode != "inspect" && mode != "resume") {
		return Request{}, ErrNative
	}
	unique := sha256.Sum256([]byte(r.Index.BrokerMessageID))
	return Request{Schema: "m3-managed-native-request/v1", Mode: mode, RequestSHA: review.Hex(sha), Nonce: r.Nonce, SourceSHA: r.SourceSHA, IndexSHA: r.Snapshot.Index, Nameserver: c.AdminNameserver, Broker: c.AdminBroker, Topic: r.Index.Topic, Offset: *r.Index.CommitlogOffset, QueueID: *r.Index.QueueID, QueueOffset: *r.Index.QueueOffset, RealTopic: s.Reference.PhysicalTopic, Owner: s.Binding.Owner, ReferenceSHA: review.Hex(review.ReferenceSHA(r)), WireSHA: review.Hex(s.Reference.WireHash), UniqueSHA: review.Hex(unique), Retention: 48, Revision: s.Reference.RouteRevision}, nil
}

func (p Report) Validate(r review.Request, sha [32]byte, mode string, started, ended time.Time) error {
	s, err := r.Snapshot.Authority()
	if err != nil || p.Schema != "m3-managed-native-recheck/v1" || p.Mode != mode || p.RequestSHA != review.Hex(sha) || p.Nonce != r.Nonce || p.SourceSHA != r.SourceSHA || p.IndexSHA != r.Snapshot.Index || p.BodyExported == nil || *p.BodyExported || p.Shutdown == nil || !*p.Shutdown || p.ReferenceSHA != review.Hex(review.ReferenceSHA(r)) || p.WireSHA != review.Hex(s.Reference.WireHash) || p.Retention != 48 || p.Remaining <= 120 || p.BodyBytes < 1 || p.BodyBytes > 262144 || p.ObservedAt.Before(started.Add(-time.Second)) || p.ObservedAt.After(ended.Add(time.Second)) {
		return ErrNative
	}
	if p.Outcome != "Unknown" && (p.FailureStage != "" || p.FailureKind != "") {
		return ErrNative
	}
	if len(p.FailureStage) > 64 || len(p.FailureKind) > 128 {
		return ErrNative
	}
	u := sha256.Sum256([]byte(r.Index.BrokerMessageID))
	if p.UniqueSHA != review.Hex(u) {
		return ErrNative
	}
	if mode == "inspect" {
		if p.Outcome != "NotAttempted" {
			return ErrNative
		}
	} else if mode == "resume" {
		if p.Outcome != "RecheckEnqueued" && p.Outcome != "Unknown" {
			return ErrNative
		}
	} else {
		return ErrNative
	}
	return nil
}

type limitedOutput struct {
	mu     sync.Mutex
	buffer bytes.Buffer
	failed bool
	cancel context.CancelFunc
}

func (w *limitedOutput) Write(p []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.failed || w.buffer.Len()+len(p) > privatefile.MaxBytes {
		w.failed = true
		w.cancel()
		return 0, ErrNative
	}
	return w.buffer.Write(p)
}

func (r *Runner) Run(ctx context.Context, request review.Request, sha [32]byte, mode, directory string) (report Report, sum [32]byte, err error) {
	if !receipt.OwnedDirectory(directory) {
		return report, sum, ErrNative
	}
	input, err := makeRequest(request, sha, mode, r.config)
	if err != nil {
		return report, sum, ErrNative
	}
	path := filepath.Join(directory, "native-"+mode+"-input.json")
	if _, err = review.Write(path, input); err != nil {
		return report, sum, ErrNative
	}
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	output := &limitedOutput{cancel: cancel}
	started := time.Now().UTC()
	cmd := exec.CommandContext(ctx, "/bin/bash", "-s", "--", path)
	cmd.Dir = directory
	cmd.Env = []string{"PATH=" + os.Getenv("PATH"), "LANG=C.UTF-8", "TMPDIR=" + directory}
	cmd.Stdin = bytes.NewReader(r.script)
	cmd.Stdout = output
	cmd.Stderr = output
	cmd.SysProcAttr = childAttributes()
	cmd.WaitDelay = 2 * time.Second
	cmd.Cancel = func() error {
		if cmd.Process == nil {
			return nil
		}
		e := syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
		if errors.Is(e, syscall.ESRCH) {
			return nil
		}
		return e
	}
	runErr := cmd.Run()
	// A returned shell may have left descendants. They cannot become a success
	// proof or survive as an unowned native admin. Kill only this owned group.
	groupGone := true
	if cmd.Process != nil {
		e := syscall.Kill(-cmd.Process.Pid, 0)
		if !errors.Is(e, syscall.ESRCH) {
			groupGone = false
			_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
		}
	}
	raw := append([]byte(nil), output.buffer.Bytes()...)
	if len(raw) > 0 {
		if _, e := privatefile.Write(filepath.Join(directory, "native-"+mode+"-private.log"), raw); e != nil {
			return report, sum, ErrNative
		}
	}
	if !groupGone || output.failed || ctx.Err() != nil {
		return report, sum, ErrNative
	}
	var framed []byte
	for _, line := range bytes.Split(raw, []byte{'\n'}) {
		if bytes.HasPrefix(line, []byte("M3_MANAGED_NATIVE ")) {
			if framed != nil {
				return report, sum, ErrNative
			}
			framed = bytes.TrimPrefix(line, []byte("M3_MANAGED_NATIVE "))
		}
	}
	if privatefile.Decode(framed, &report) != nil || report.Validate(request, sha, mode, started, time.Now().UTC()) != nil {
		return Report{}, sum, ErrNative
	}
	if runErr != nil && !(mode == "resume" && report.Outcome == "Unknown") {
		return Report{}, sum, ErrNative
	}
	encoded, e := json.Marshal(report)
	if e != nil {
		return Report{}, sum, ErrNative
	}
	sum, e = privatefile.Write(filepath.Join(directory, "native-"+mode+"-report.json"), append(encoded, '\n'))
	if e != nil {
		return Report{}, [32]byte{}, ErrNative
	}
	return report, sum, nil
}

// CheckReports rechecks the exact private report bytes while validating a
// receipt. It does not claim their presence authenticates the original runner.
func CheckReports(directory string, receiptData receipt.Receipt, r review.Request, sha [32]byte) error {
	for _, item := range []struct{ mode, digest string }{{"inspect", receiptData.InspectionSHA}, {"resume", receiptData.NativeSHA}} {
		sum, err := review.Digest(item.digest)
		if err != nil {
			return ErrNative
		}
		raw, err := privatefile.Read(filepath.Join(directory, "native-"+item.mode+"-report.json"), sum)
		var p Report
		if err != nil || privatefile.Decode(raw, &p) != nil || p.Validate(r, sha, item.mode, receiptData.StartedAt, receiptData.CompletedAt) != nil || (item.mode == "resume" && p.Outcome != receiptData.NativeOutcome) {
			return ErrNative
		}
	}
	return nil
}
