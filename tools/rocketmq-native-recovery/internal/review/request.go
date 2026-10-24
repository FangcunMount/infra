// Package review freezes private recovery requests before any SDK or native
// admin starts. File digests identify reviewed bytes; they do not authenticate
// operators or replace execution by the named, frozen coordinator command.
package review

import (
	"bytes"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"fangcunmount.infra/rocketmq-native-recovery/internal/authority"
	"fangcunmount.infra/rocketmq-native-recovery/internal/privatefile"
	"github.com/FangcunMount/reliable-messaging/transaction"
)

var ErrReview = errors.New("exact unexpired private recovery review required")

// Snapshot contains no wire, execution token, DSN or Broker transaction handle.
// Reference is the fixed SDK's canonical encoding, kept byte-for-byte.
type Snapshot struct {
	Owner         string                   `json:"owner"`
	Store         string                   `json:"store_id"`
	Epoch         string                   `json:"writer_epoch"`
	Reference     string                   `json:"reference"`
	Database      string                   `json:"database_identity_sha256"`
	Decision      transaction.Decision     `json:"local_decision"`
	Half          transaction.HalfOutcome  `json:"before_half"`
	Final         transaction.FinalOutcome `json:"before_final"`
	FinalAt       *time.Time               `json:"before_final_at"`
	NoticeKey     string                   `json:"notice_key"`
	Index         string                   `json:"native_index_sha256"`
	FirstEvidence string                   `json:"first_evidence_sha256"`
}

func Freeze(s authority.Snapshot) (Snapshot, error) {
	if authority.ValidateReview(s) != nil || s.Notice.Status != "blocked" {
		return Snapshot{}, ErrReview
	}
	raw, err := transaction.EncodeReference(s.Reference)
	if err != nil {
		return Snapshot{}, ErrReview
	}
	return Snapshot{Owner: s.Binding.Owner, Store: s.Binding.StoreID, Epoch: s.Binding.WriterEpoch,
		Reference: string(raw), Database: Hex(s.DatabaseIdentitySHA256), Decision: s.Decision,
		Half: s.Half, Final: s.BeforeFinal, FinalAt: s.BeforeFinalAt, NoticeKey: Hex(s.Notice.Key),
		Index: Hex(s.Notice.IndexSHA256), FirstEvidence: Hex(s.Notice.FirstEvidenceSHA256)}, nil
}

func (s Snapshot) Authority() (out authority.Snapshot, err error) {
	ref, err := transaction.DecodeReference([]byte(s.Reference))
	if err != nil {
		return out, ErrReview
	}
	canonical, err := transaction.EncodeReference(ref)
	if err != nil || !bytes.Equal(canonical, []byte(s.Reference)) {
		return out, ErrReview
	}
	values := []*[32]byte{&out.DatabaseIdentitySHA256, &out.Notice.Key, &out.Notice.IndexSHA256, &out.Notice.FirstEvidenceSHA256}
	for i, value := range []string{s.Database, s.NoticeKey, s.Index, s.FirstEvidence} {
		*values[i], err = Digest(value)
		if err != nil {
			return authority.Snapshot{}, ErrReview
		}
	}
	out.Binding = transaction.Binding{Owner: s.Owner, StoreID: s.Store, WriterEpoch: s.Epoch}
	out.Reference, out.Decision, out.Half, out.BeforeFinal, out.BeforeFinalAt = ref, s.Decision, s.Half, s.Final, s.FinalAt
	out.Notice.Status = "blocked"
	if authority.ValidateReview(out) != nil {
		return authority.Snapshot{}, ErrReview
	}
	return out, nil
}

type Request struct {
	Schema          string    `json:"schema"`
	SourceSHA       string    `json:"source_sha"`
	BinarySHA       string    `json:"binary_sha256"`
	SourceBundleSHA string    `json:"source_bundle_sha256"`
	ConfigSHA       string    `json:"config_sha256"`
	ManifestSHA     string    `json:"manifest_sha256"`
	ExportSHA       string    `json:"native_export_sha256"`
	Nonce           string    `json:"invocation_nonce"`
	CreatedAt       time.Time `json:"created_at"`
	ExpiresAt       time.Time `json:"expires_at"`
	DataOwner       string    `json:"data_owner"`
	RecoveryOwner   string    `json:"recovery_owner"`
	Snapshot        Snapshot  `json:"snapshot"`
	Index           Index     `json:"physical_index"`
}

type Inputs struct {
	SourceSHA                                                     string
	BinarySHA, SourceBundleSHA, ConfigSHA, ManifestSHA, ExportSHA [32]byte
	DataOwner, RecoveryOwner                                      string
	Now                                                           time.Time
}

func New(s authority.Snapshot, index Index, input Inputs) (Request, error) {
	frozen, err := Freeze(s)
	if err != nil {
		return Request{}, err
	}
	var nonce [32]byte
	if _, err = rand.Read(nonce[:]); err != nil {
		return Request{}, ErrReview
	}
	now := input.Now.UTC()
	r := Request{Schema: "m3-native-recovery-request/v1", SourceSHA: input.SourceSHA,
		BinarySHA: Hex(input.BinarySHA), SourceBundleSHA: Hex(input.SourceBundleSHA), ConfigSHA: Hex(input.ConfigSHA),
		ManifestSHA: Hex(input.ManifestSHA), ExportSHA: Hex(input.ExportSHA), Nonce: Hex(nonce),
		CreatedAt: now, ExpiresAt: now.Add(30 * time.Minute), DataOwner: input.DataOwner, RecoveryOwner: input.RecoveryOwner,
		Snapshot: frozen, Index: index}
	if err = r.Validate(now); err != nil {
		return Request{}, err
	}
	return r, nil
}

func (r Request) Validate(now time.Time) error {
	if r.Schema != "m3-native-recovery-request/v1" || !Source(r.SourceSHA) || !Named(r.DataOwner) || !Named(r.RecoveryOwner) || r.CreatedAt.IsZero() || r.CreatedAt.After(now.Add(time.Minute)) || !r.ExpiresAt.After(now) || r.ExpiresAt.Sub(r.CreatedAt) <= 0 || r.ExpiresAt.Sub(r.CreatedAt) > time.Hour || now.Before(r.CreatedAt.Add(-time.Minute)) {
		return ErrReview
	}
	for _, value := range []string{r.BinarySHA, r.SourceBundleSHA, r.ConfigSHA, r.ManifestSHA, r.ExportSHA, r.Nonce} {
		if _, err := Digest(value); err != nil {
			return ErrReview
		}
	}
	s, err := r.Snapshot.Authority()
	if err != nil || r.Index.Fingerprint() != s.Notice.IndexSHA256 {
		return ErrReview
	}
	return nil
}

func (r Request) Expected() transaction.FinalOutcome {
	if r.Snapshot.Decision == transaction.Commit {
		return transaction.FinalCommitConfirmed
	}
	if r.Snapshot.Decision == transaction.Rollback {
		return transaction.FinalRollbackConfirmed
	}
	return transaction.FinalUnknown
}

func Load(path string, expected [32]byte, now time.Time) (r Request, err error) {
	raw, err := privatefile.Read(path, expected)
	if err != nil || privatefile.Decode(raw, &r) != nil || r.Validate(now) != nil {
		return Request{}, ErrReview
	}
	return r, nil
}

// LoadRecorded permits only forensic, read-only verification after a request
// expires. Its full frozen graph still validates; it cannot authorize a new
// SDK start, native recheck or governance write.
func LoadRecorded(path string, expected [32]byte, now time.Time) (r Request, err error) {
	raw, err := privatefile.Read(path, expected)
	if err != nil || privatefile.Decode(raw, &r) != nil || r.CreatedAt.After(now.Add(time.Minute)) || r.Validate(r.CreatedAt) != nil {
		return Request{}, ErrReview
	}
	return r, nil
}

func Write(path string, value any) ([32]byte, error) {
	raw, err := json.Marshal(value)
	if err != nil {
		return [32]byte{}, ErrReview
	}
	return privatefile.Write(path, append(raw, '\n'))
}

func Hex(v [32]byte) string { return hex.EncodeToString(v[:]) }
func Digest(value string) (out [32]byte, err error) {
	raw, err := hex.DecodeString(value)
	if err != nil || len(raw) != 32 || value != hex.EncodeToString(raw) || bytes.Equal(raw, make([]byte, 32)) {
		return out, ErrReview
	}
	copy(out[:], raw)
	return out, nil
}
func Source(value string) bool {
	raw, err := hex.DecodeString(value)
	return err == nil && len(raw) == 20 && value == hex.EncodeToString(raw) && !bytes.Equal(raw, make([]byte, 20))
}
func Named(value string) bool {
	if strings.TrimSpace(value) == "" || len(value) > 128 {
		return false
	}
	for _, c := range value {
		if c < 32 || c == 127 {
			return false
		}
	}
	return true
}

func ReferenceSHA(r Request) [32]byte { return sha256.Sum256([]byte(r.Snapshot.Reference)) }
