package preview

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"fangcunmount.infra/rocketmq-native-recovery/internal/authority"
	"fangcunmount.infra/rocketmq-native-recovery/internal/connection"
	"fangcunmount.infra/rocketmq-native-recovery/internal/privatefile"
	"fangcunmount.infra/rocketmq-native-recovery/internal/review"
	"github.com/FangcunMount/reliable-messaging/transaction"
)

type fixtureReader struct {
	snapshot authority.Snapshot
	calls    int
	err      error
}

func (r *fixtureReader) Snapshot(_ context.Context, l authority.Locator, index [32]byte) (authority.Snapshot, error) {
	r.calls++
	if l.OperationID != r.snapshot.Reference.OperationID || l.BranchID != r.snapshot.Reference.BranchID || l.Fence != r.snapshot.Reference.Fence || index != r.snapshot.Notice.IndexSHA256 {
		return authority.Snapshot{}, errors.New("wrong exact locator")
	}
	return r.snapshot, r.err
}
func previewFixture(t *testing.T) (Input, *fixtureReader, time.Time) {
	t.Helper()
	root := t.TempDir()
	if err := os.Chmod(root, 0700); err != nil {
		t.Fatal(err)
	}
	write := func(name string, value any) File {
		t.Helper()
		p := filepath.Join(root, name)
		sum, err := review.Write(p, value)
		if err != nil {
			t.Fatal(err)
		}
		return File{p, sum}
	}
	c := connection.Config{Schema: "m3-native-recovery-config/v1", Owner: "iam.mysql", StoreID: "original", WriterEpoch: "epoch-1", DatabaseKind: "mysql", DatabaseURI: "unit:secret@tcp(127.0.0.1:1)/original", DatabaseName: "original", Endpoint: "127.0.0.1:1", AccessKey: "unit", SecretKey: "secret"}
	raw, err := os.ReadFile("../../../../components/rocketmq/serverd-routes-m3-v2.json")
	if err != nil {
		t.Fatal(err)
	}
	mp := filepath.Join(root, "manifest.json")
	ms, err := privatefile.Write(mp, raw)
	if err != nil {
		t.Fatal(err)
	}
	var m struct {
		Routes []struct {
			Topic    string `json:"topic"`
			Physical string `json:"physical_topic"`
			Owner    string `json:"owner"`
			Type     string `json:"message_type"`
		} `json:"routes"`
	}
	if json.Unmarshal(raw, &m) != nil {
		t.Fatal("fixture manifest")
	}
	topic, physical := "", ""
	for _, r := range m.Routes {
		if r.Owner == c.Owner && r.Type == "TRANSACTION" {
			topic, physical = r.Topic, r.Physical
			break
		}
	}
	n := func(v int64) *int64 { return &v }
	i := review.Index{Topic: review.NativeTopic, KeySHA: strings.Repeat("1", 64), BrokerMessageID: strings.Repeat("A", 32), QueueID: n(0), QueueOffset: n(1), CommitlogOffset: n(2), IndexHour: n(3)}
	index := i.Fingerprint()
	b := c.Binding()
	ref := transaction.Reference{Owner: c.Owner, Scope: "org:7", OperationID: "op", BranchID: "branch", MessageID: "original", LogicalTopic: topic, PhysicalTopic: physical, RouteRevision: "m3-1", WriterEpoch: c.WriterEpoch, Fence: 1, PlanDigest: [32]byte{1}, WireHash: [32]byte{2}, MessageFingerprint: [32]byte{3}}
	a := authority.Snapshot{Binding: b, Reference: ref, DatabaseIdentitySHA256: [32]byte{4}, Decision: transaction.Commit, Half: transaction.HalfPrepared, BeforeFinal: transaction.FinalUnknown, Notice: authority.Notice{Key: authority.NoticeKey(b, index), IndexSHA256: index, FirstEvidenceSHA256: [32]byte{5}, Status: "blocked"}}
	export := map[string]any{"topic": review.NativeTopic, "key_sha256": i.KeySHA, "records": []map[string]any{{"broker_message_id": i.BrokerMessageID, "queue_id": 0, "queue_offset": 1, "commitlog_offset": 2, "index_hour": 3}}, "raw_admin_sha256": strings.Repeat("2", 64), "read_only": true, "body_exported": false, "truncated_possible": false, "alert": "native_transaction_check_limit_reached", "severity": "critical"}
	s := Selection{Schema: "m3-native-recovery-selection/v1", Operation: "op", Branch: "branch", Fence: 1, IndexSHA: review.Hex(index), SourceBundleSHA: strings.Repeat("3", 64), DataOwner: "unit-data", RecoveryOwner: "unit-recovery"}
	return Input{Config: write("config.json", c), Manifest: File{mp, ms}, Export: write("index.json", export), Selection: write("selection.json", s), Output: filepath.Join(root, "request.json"), SourceSHA: strings.Repeat("1", 40), BinarySHA: sha256.Sum256([]byte("unit-binary"))}, &fixtureReader{snapshot: a}, time.Date(2026, 10, 24, 0, 0, 0, 0, time.UTC)
}
func TestPreviewReadsOriginalOnceAndClosesBeforeReportingHash(t *testing.T) {
	in, reader, now := previewFixture(t)
	opens, closes := 0, 0
	open := func(_ context.Context, c connection.Config) (Owned, error) {
		opens++
		if c.Binding() != reader.snapshot.Binding {
			t.Fatal("request selected a database")
		}
		return Owned{reader, func() error { closes++; return nil }}, nil
	}
	sum, err := Run(context.Background(), in, now, open)
	if err != nil || opens != 1 || reader.calls != 1 || closes != 1 {
		t.Fatal("read-only preview failed", err)
	}
	r, err := review.Load(in.Output, sum, now)
	if err != nil || r.ConfigSHA != review.Hex(in.Config.SHA256) || r.ExportSHA != review.Hex(in.Export.SHA256) || r.ManifestSHA != review.Hex(in.Manifest.SHA256) || r.SourceSHA != in.SourceSHA {
		t.Fatal("request graph not frozen", err)
	}
	if _, err := Run(context.Background(), in, now, open); err == nil || opens != 1 {
		t.Fatal("existing output was replaced or database reopened")
	}
}
func TestPreviewInvalidFilesDoNotOpenDatabase(t *testing.T) {
	for _, name := range []string{"config-hash", "manifest-hash", "export-hash", "selection-hash", "source", "binary", "public-output-dir", "output-symlink", "selection-fence", "selection-owner", "missing-index"} {
		t.Run(name, func(t *testing.T) {
			in, _, now := previewFixture(t)
			switch name {
			case "config-hash":
				in.Config.SHA256[0] ^= 1
			case "manifest-hash":
				in.Manifest.SHA256[0] ^= 1
			case "export-hash":
				in.Export.SHA256[0] ^= 1
			case "selection-hash":
				in.Selection.SHA256[0] ^= 1
			case "source":
				in.SourceSHA = "unfrozen"
			case "binary":
				in.BinarySHA = [32]byte{}
			case "public-output-dir":
				if err := os.Chmod(filepath.Dir(in.Output), 0755); err != nil {
					t.Fatal(err)
				}
			case "output-symlink":
				if err := os.Symlink("missing", in.Output); err != nil {
					t.Fatal(err)
				}
			default:
				raw, err := os.ReadFile(in.Selection.Path)
				if err != nil {
					t.Fatal(err)
				}
				var s Selection
				if json.Unmarshal(raw, &s) != nil {
					t.Fatal("fixture")
				}
				if name == "selection-fence" {
					s.Fence = 0
				}
				if name == "selection-owner" {
					s.RecoveryOwner = ""
				}
				if name == "missing-index" {
					s.IndexSHA = strings.Repeat("4", 64)
				}
				p := filepath.Join(filepath.Dir(in.Output), "changed-selection.json")
				sum, err := review.Write(p, s)
				if err != nil {
					t.Fatal(err)
				}
				in.Selection = File{p, sum}
			}
			opens := 0
			open := func(context.Context, connection.Config) (Owned, error) { opens++; return Owned{}, nil }
			if _, err := Run(context.Background(), in, now, open); err == nil || opens != 0 {
				t.Fatal("invalid private input reached DB")
			}
		})
	}
}
func TestPreviewPrimaryMismatchOrCloseFailureHasNoSuccessfulHash(t *testing.T) {
	for _, name := range []string{"different-primary", "foreign-binding", "unknown", "resolved-notice", "wrong-route", "read-error", "close-error", "cancelled"} {
		t.Run(name, func(t *testing.T) {
			in, r, now := previewFixture(t)
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			closeErr := error(nil)
			switch name {
			// A new primary identity is frozen at preview, then later compared by
			// the execution phase. Here a mismatch in its own evidence is rejected.
			case "different-primary":
				r.snapshot.DatabaseIdentitySHA256 = [32]byte{}
			case "foreign-binding":
				r.snapshot.Binding.StoreID = "foreign"
			case "unknown":
				r.snapshot.Decision = transaction.Unknown
			case "resolved-notice":
				r.snapshot.Notice.Status = "resolved"
			case "wrong-route":
				r.snapshot.Reference.LogicalTopic = "other"
			case "read-error":
				r.err = errors.New("private DB error")
			case "close-error":
				closeErr = errors.New("private close error")
			case "cancelled":
				cancel()
			}
			closes := 0
			sum, err := Run(ctx, in, now, func(context.Context, connection.Config) (Owned, error) {
				return Owned{r, func() error { closes++; return closeErr }}, nil
			})
			if err == nil || sum != [32]byte{} || closes != 1 {
				t.Fatal("reported success on incomplete original read/close")
			}
		})
	}
}
