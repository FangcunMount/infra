package authority

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/FangcunMount/reliable-messaging/transaction"
	"github.com/FangcunMount/reliable-messaging/transport"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
)

// Synthetic projected BSON only; these tests do not claim a real Mongo root.
func mongoRowFixture(t *testing.T) (bson.M, transaction.Binding, Locator, transaction.Reference) {
	t.Helper()
	s, l := snapshotFixture(t)
	b := s.Binding
	b.Owner = "qs.mongo"
	ref := s.Reference
	ref.Owner = b.Owner
	physical, err := transport.PhysicalTopicV2(ref.LogicalTopic, transport.TransactionMessageType, b.Owner, ref.RouteRevision)
	if err != nil {
		t.Fatal(err)
	}
	ref.PhysicalTopic = physical
	raw, err := transaction.EncodeReference(ref)
	if err != nil {
		t.Fatal(err)
	}
	ek := transaction.ExecutionKey(b.Owner, l.OperationID, b.WriterEpoch, l.Fence)
	return bson.M{"_id": ek[:], "owner": b.Owner, "writer_epoch": b.WriterEpoch, "fence": int64(l.Fence), "state": transaction.Committed, "witnesses": bson.A{bson.M{"reference": raw, "state": transaction.Committed}}}, b, l, ref
}

func TestMongoProjectionDecodesExactTargetWithoutExecutionCapability(t *testing.T) {
	row, b, l, ref := mongoRowFixture(t)
	raw, err := bson.Marshal(row)
	if err != nil {
		t.Fatal(err)
	}
	execution, actual, witness, err := decodeMongoExecution(raw, b, l)
	if err != nil || actual != ref || execution.Fence != int64(l.Fence) || witness.State != transaction.Committed {
		t.Fatal("exact projected identity lost", err)
	}
	for field := range mongoProjection() {
		for _, forbidden := range []string{"token", "plan", "wire", "broker_message_id", "broker_transaction_id"} {
			if strings.Contains(field, forbidden) {
				t.Fatal("projection exposes execution capability or message bytes")
			}
		}
	}
}

func TestMongoProjectionRejectsAmbiguousOrUnsupportedIdentity(t *testing.T) {
	for _, scenario := range []string{"float-fence", "negative-fence", "owner", "epoch", "key", "too-many", "duplicate-branch", "missing-branch", "bad-reference", "oversize-reference", "oversize-document", "wrong-ref-owner"} {
		t.Run(scenario, func(t *testing.T) {
			row, b, l, ref := mongoRowFixture(t)
			w := row["witnesses"].(bson.A)[0].(bson.M)
			switch scenario {
			case "float-fence":
				row["fence"] = float64(1)
			case "negative-fence":
				row["fence"] = int64(-1)
			case "owner":
				row["owner"] = "ai.mysql"
			case "epoch":
				row["writer_epoch"] = "old"
			case "key":
				row["_id"] = make([]byte, 32)
			case "too-many":
				values := bson.A{}
				for range transaction.MaxBranches + 1 {
					values = append(values, w)
				}
				row["witnesses"] = values
			case "duplicate-branch":
				row["witnesses"] = bson.A{w, w}
			case "missing-branch":
				l.BranchID = "absent"
			case "bad-reference":
				w["reference"] = []byte("{}")
			case "oversize-reference":
				w["reference"] = make([]byte, 16385)
			case "oversize-document":
				row["unused"] = make([]byte, transaction.MaxBranches*(16384+1024))
			case "wrong-ref-owner":
				ref.Owner = "ai.mysql"
				raw, e := transaction.EncodeReference(ref)
				if e != nil {
					t.Fatal(e)
				}
				w["reference"] = raw
			}
			raw, err := bson.Marshal(row)
			if err != nil {
				t.Fatal(err)
			}
			if _, _, _, err = decodeMongoExecution(raw, b, l); !errors.Is(err, ErrSnapshot) {
				t.Fatal("ambiguous original evidence accepted")
			}
		})
	}
}

func TestMongoConstructorAndInvalidLocatorDoNotStartClientWork(t *testing.T) {
	_, b, l, _ := mongoRowFixture(t)
	client := new(mongo.Client)
	reader, err := NewMongo(client.Database("owned"), b)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = reader.Snapshot(context.Background(), Locator{}, [32]byte{1}); !errors.Is(err, ErrSnapshot) {
		t.Fatal("invalid input opened a session")
	}
	if _, err = reader.Snapshot(context.Background(), l, [32]byte{}); !errors.Is(err, ErrSnapshot) {
		t.Fatal("missing index opened a session")
	}
	b.Owner = "qs.mysql"
	if _, err = NewMongo(client.Database("owned"), b); !errors.Is(err, transaction.ErrBinding) {
		t.Fatal("wrong store type accepted")
	}
	if _, err = NewMongo(nil, b); !errors.Is(err, transaction.ErrBinding) {
		t.Fatal("nil database accepted")
	}
}
