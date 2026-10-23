// Package observation keeps per-invocation SDK post-RPC observations private.
// Its files prove neither consumer completion nor operator authorization.
package observation

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"

	"fangcunmount.infra/rocketmq-native-recovery/internal/checkonly"
	"github.com/FangcunMount/reliable-messaging/transaction"
)

var ErrObservation = errors.New("private current-RPC observation incomplete")

// Identity is frozen in the separately reviewed request. The nonce is freshly
// generated for this invocation; an old DB audit timestamp is never freshness.
type Identity struct {
	RequestSHA256, Nonce, ReferenceSHA256 [32]byte
	SourceSHA                             [20]byte
	Outcome                               transaction.FinalOutcome
}

type Record struct {
	Schema          string                   `json:"schema"`
	RequestSHA256   string                   `json:"request_sha256"`
	InvocationNonce string                   `json:"invocation_nonce"`
	SourceSHA       string                   `json:"source_sha"`
	ReferenceSHA256 string                   `json:"reference_sha256"`
	Outcome         transaction.FinalOutcome `json:"rpc_outcome"`
	ObservedAt      time.Time                `json:"observed_at"`
}

type File struct {
	Name   string `json:"name"`
	SHA256 string `json:"sha256"`
}

// Recorder creates a new private directory and never replaces an existing
// observation. The bounded synchronous write remains inside the SDK's running
// recovery callback. Cancellation cannot report that a write has stopped early.
type Recorder struct {
	mu       sync.Mutex
	root     *os.Root
	dir      string
	identity Identity
	files    []File
	failed   bool
	closed   bool
	first    chan struct{}
}

const maxObservations = 16

func New(parent string, identity Identity) (*Recorder, error) {
	if !filepath.IsAbs(parent) || identity.RequestSHA256 == [32]byte{} || identity.Nonce == [32]byte{} || identity.ReferenceSHA256 == [32]byte{} || identity.SourceSHA == [20]byte{} {
		return nil, ErrObservation
	}
	if _, err := transaction.RecoveryFinalState(identity.Outcome); err != nil {
		return nil, ErrObservation
	}
	dir, err := os.MkdirTemp(parent, "native-rpc-")
	if err != nil {
		return nil, ErrObservation
	}
	root, err := os.OpenRoot(dir)
	if err != nil {
		// Keep the owned directory for diagnosis; never clean unrelated paths.
		return nil, ErrObservation
	}
	return &Recorder{root: root, dir: dir, identity: identity, first: make(chan struct{})}, nil
}

func (r *Recorder) Directory() string      { return r.dir }
func (r *Recorder) First() <-chan struct{} { return r.first }

func (r *Recorder) Sink(ctx context.Context, event checkonly.Event) (err error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	defer func() {
		if err != nil {
			r.failed = true
		}
	}()
	if r.closed || r.failed || len(r.files) >= maxObservations || ctx.Err() != nil || event.ReferenceSHA256 != r.identity.ReferenceSHA256 || event.Outcome != r.identity.Outcome {
		return ErrObservation
	}
	id := r.identity
	record := Record{"m3-native-current-rpc/v1", hex.EncodeToString(id.RequestSHA256[:]), hex.EncodeToString(id.Nonce[:]), hex.EncodeToString(id.SourceSHA[:]), hex.EncodeToString(id.ReferenceSHA256[:]), event.Outcome, time.Now().UTC()}
	raw, err := json.Marshal(record)
	if err != nil {
		return ErrObservation
	}
	raw = append(raw, '\n')
	name := fmt.Sprintf("rpc-%02d.json", len(r.files)+1)
	f, err := r.root.OpenFile(name, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return ErrObservation
	}
	_, writeErr := f.Write(raw)
	syncErr := f.Sync()
	closeErr := f.Close()
	if errors.Join(writeErr, syncErr, closeErr, ctx.Err()) != nil {
		return ErrObservation
	}
	// Persist the directory entry as well as its contents. Do not claim durable
	// success on a filesystem that rejects directory synchronization.
	directory, err := r.root.Open(".")
	if err != nil {
		return ErrObservation
	}
	syncErr = directory.Sync()
	closeErr = directory.Close()
	if errors.Join(syncErr, closeErr, ctx.Err()) != nil {
		return ErrObservation
	}
	sum := sha256.Sum256(raw)
	r.files = append(r.files, File{name, hex.EncodeToString(sum[:])})
	if len(r.files) == 1 {
		close(r.first)
	}
	return nil
}

// Close must follow the actual SDK Close/Wait drain, never a caller timeout.
// Files are retained on every failure. A second close returns the same outcome.
func (r *Recorder) Close() ([]File, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if !r.closed {
		r.closed = true
		if r.root.Close() != nil {
			r.failed = true
		}
	}
	if r.failed || len(r.files) == 0 {
		return nil, ErrObservation
	}
	return append([]File(nil), r.files...), nil
}
