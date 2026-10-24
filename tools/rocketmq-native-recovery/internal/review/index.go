package review

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"hash"

	"fangcunmount.infra/rocketmq-native-recovery/internal/privatefile"
)

const NativeTopic = "TRANS_CHECK_MAX_TIME_TOPIC"

// Index is the existing host v1 physical fingerprint, including positions.
// BrokerMessageID can be a copied UNIQ_KEY; it is not a physical offset ID.
type Index struct {
	Topic           string `json:"source_topic"`
	KeySHA          string `json:"key_sha256"`
	BrokerMessageID string `json:"broker_message_id"`
	QueueID         *int64 `json:"queue_id"`
	QueueOffset     *int64 `json:"queue_offset"`
	CommitlogOffset *int64 `json:"commitlog_offset"`
	IndexHour       *int64 `json:"index_hour"`
}

func field(h hash.Hash, value []byte) {
	var n [4]byte
	binary.BigEndian.PutUint32(n[:], uint32(len(value)))
	_, _ = h.Write(n[:])
	_, _ = h.Write(value)
}
func (i Index) Fingerprint() (out [32]byte) {
	key, err := Digest(i.KeySHA)
	id, idErr := hex.DecodeString(i.BrokerMessageID)
	if i.Topic != NativeTopic || err != nil || idErr != nil || len(i.BrokerMessageID) < 32 || len(i.BrokerMessageID) > 64 {
		return out
	}
	h := sha256.New()
	_, _ = h.Write([]byte("m3-native-limit-index-v1\x00"))
	for _, v := range [][]byte{[]byte(i.Topic), key[:], id} {
		field(h, v)
	}
	for _, n := range []*int64{i.QueueID, i.QueueOffset, i.CommitlogOffset, i.IndexHour} {
		if n == nil || *n < 0 {
			return out
		}
		var v [8]byte
		binary.BigEndian.PutUint64(v[:], uint64(*n))
		_, _ = h.Write(v[:])
	}
	copy(out[:], h.Sum(nil))
	return out
}

type exportRow struct {
	MessageID       string `json:"broker_message_id"`
	QueueID         *int64 `json:"queue_id"`
	QueueOffset     *int64 `json:"queue_offset"`
	CommitlogOffset *int64 `json:"commitlog_offset"`
	IndexHour       *int64 `json:"index_hour"`
}
type nativeExport struct {
	Topic     string      `json:"topic"`
	Key       string      `json:"key_sha256"`
	Rows      []exportRow `json:"records"`
	Admin     string      `json:"raw_admin_sha256"`
	ReadOnly  *bool       `json:"read_only"`
	Body      *bool       `json:"body_exported"`
	Truncated *bool       `json:"truncated_possible"`
	Alert     string      `json:"alert"`
	Severity  string      `json:"severity"`
}

// SelectExport validates every row, including unselected copies. A 64-row
// export can select a target, but cannot demonstrate absence of other duties.
func SelectExport(path string, expected, selected [32]byte) (Index, error) {
	raw, err := privatefile.Read(path, expected)
	var e nativeExport
	if err != nil || privatefile.Decode(raw, &e) != nil || e.Topic != NativeTopic || e.ReadOnly == nil || !*e.ReadOnly || e.Body == nil || *e.Body || e.Truncated == nil || len(e.Rows) < 1 || len(e.Rows) > 64 || *e.Truncated != (len(e.Rows) == 64) || e.Alert != "native_transaction_check_limit_reached" || e.Severity != "critical" {
		return Index{}, ErrReview
	}
	if _, err = Digest(e.Admin); err != nil {
		return Index{}, ErrReview
	}
	seen := map[[32]byte]bool{}
	var result Index
	for _, r := range e.Rows {
		i := Index{e.Topic, e.Key, r.MessageID, r.QueueID, r.QueueOffset, r.CommitlogOffset, r.IndexHour}
		sum := i.Fingerprint()
		if sum == [32]byte{} || seen[sum] {
			return Index{}, ErrReview
		}
		seen[sum] = true
		if bytes.Equal(sum[:], selected[:]) {
			result = i
		}
	}
	if result.Fingerprint() == [32]byte{} {
		return Index{}, ErrReview
	}
	return result, nil
}
