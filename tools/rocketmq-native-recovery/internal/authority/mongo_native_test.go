//go:build integration

package authority

import (
	"context"
	"fmt"
	"os"
	"reflect"
	"testing"
	"time"

	txmongo "github.com/FangcunMount/reliable-messaging/storage/transaction/mongo"
	"github.com/FangcunMount/reliable-messaging/transaction"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

func ownedMongo(t *testing.T) *mongo.Database {
	t.Helper()
	if os.Getenv("GITHUB_ACTIONS") != "true" || os.Getenv("RUNNER_ENVIRONMENT") != "github-hosted" || os.Getenv("GITHUB_REPOSITORY") != "FangcunMount/infra" || os.Getenv("NATIVE_TOOL_TEST_MONGO_URI") != "mongodb://127.0.0.1:27017/?directConnection=true&replicaSet=native-proof" {
		t.Fatal("required isolated GitHub loopback replica set missing")
	}
	client, err := mongo.Connect(t.Context(), options.Client().ApplyURI(os.Getenv("NATIVE_TOOL_TEST_MONGO_URI")).SetConnectTimeout(3*time.Second).SetServerSelectionTimeout(3*time.Second).SetTimeout(3*time.Second))
	if err != nil {
		t.Fatal("connect disposable client failed")
	}
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if client.Disconnect(ctx) != nil {
			t.Error("owned Mongo client incomplete")
		}
	})
	name := fmt.Sprintf("m3_native_tool_test_%d", time.Now().UnixNano())
	db := client.Database(name)
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if db.Drop(ctx) != nil {
			t.Error("owned database cleanup failed")
			return
		}
		names, e := client.ListDatabaseNames(ctx, bson.M{"name": name})
		if e != nil || len(names) != 0 {
			t.Error("owned database cleanup readback failed")
			return
		}
		t.Log("owned_database_removed=true")
	})
	if err = txmongo.InstallSchema(t.Context(), db); err != nil {
		t.Fatal("explicit owned SDK schema failed")
	}
	var commands struct {
		Commands []bson.Raw `bson:"commands"`
	}
	if err = bson.UnmarshalExtJSON([]byte(`{"commands":`+nativeMongoNoticeSchema+`}`), false, &commands); err != nil {
		t.Fatal("frozen host fixture decode failed")
	}
	for _, command := range commands.Commands {
		if err = db.RunCommand(t.Context(), command).Err(); err != nil {
			t.Fatal("explicit owned governance schema failed", err)
		}
	}
	if err = db.CreateCollection(t.Context(), "native_test_fact"); err != nil {
		t.Fatal(err)
	}
	return db
}

func TestMongoSnapshotNative(t *testing.T) {
	db := ownedMongo(t)
	b := transaction.Binding{Owner: "qs.mongo", StoreID: "owned-original", WriterEpoch: "m3-1"}
	l := Locator{"original-op", "fact", 1}
	if _, err := db.Collection("rm_tx_binding").InsertOne(t.Context(), bson.M{"_id": b.Owner, "store_id": b.StoreID, "writer_epoch": b.WriterEpoch, "schema_version": 1}); err != nil {
		t.Fatal(err)
	}
	base, err := txmongo.New(db, b)
	if err != nil {
		t.Fatal(err)
	}
	p := nativePlanForOwner(t, b.Owner, l)
	reservation, err := base.Reserve(t.Context(), transaction.RequestFor(p), p, transaction.ReserveOptions{Lease: time.Hour})
	if err != nil || !reservation.Acquired {
		t.Fatal("reserve controlled Mongo fixture failed", err)
	}
	index := [32]byte{1}
	key := NoticeKey(b, index)
	proof := [32]byte{2}
	if _, err = db.Collection("messaging_native_limit_notices").InsertOne(t.Context(), bson.M{"_id": key[:], "owner": b.Owner, "store_id": b.StoreID, "writer_epoch": b.WriterEpoch, "route_revision": "m3-1", "native_index_sha256": index[:], "evidence_sha256": proof[:], "status": "blocked", "schema_version": 1, "recorded_at": time.Now().UTC()}); err != nil {
		t.Fatal(err)
	}
	reader, err := NewMongo(db, b)
	if err != nil {
		t.Fatal(err)
	}
	t.Run("prepared-refuses-without-partial-authority", func(t *testing.T) {
		result, e := reader.Snapshot(t.Context(), l, index)
		if e == nil || !reflect.DeepEqual(result, Snapshot{}) {
			t.Fatal("Prepared evidence yielded authority")
		}
	})
	session, err := db.Client().StartSession()
	if err != nil {
		t.Fatal(err)
	}
	defer session.EndSession(t.Context())
	if err = session.StartTransaction(); err != nil {
		t.Fatal(err)
	}
	sc := mongo.NewSessionContext(t.Context(), session)
	guard, err := base.Bind(sc, reservation.Execution)
	if err != nil {
		_ = session.AbortTransaction(sc)
		t.Fatal(err)
	}
	if _, err = db.Collection("native_test_fact").InsertOne(sc, bson.M{"_id": "once"}); err != nil {
		_ = session.AbortTransaction(sc)
		t.Fatal(err)
	}
	if err = guard.CommitWitness(sc); err != nil {
		_ = session.AbortTransaction(sc)
		t.Fatal(err)
	}
	if err = session.CommitTransaction(sc); err != nil {
		t.Fatal(err)
	}
	var original Snapshot
	t.Run("exact-original-root-and-fresh-primary", func(t *testing.T) {
		original, err = reader.Snapshot(t.Context(), l, index)
		if err != nil || original.Decision != transaction.Commit || original.Reference != reservation.Execution.References()[0] || original.BeforeFinal != transaction.FinalNotAttempted || original.BeforeFinalAt != nil {
			t.Fatal("original committed Mongo snapshot failed", err)
		}
	})
	if err != nil {
		t.Fatal("no authority after failed committed fixture")
	}
	ek := transaction.ExecutionKey(b.Owner, l.OperationID, b.WriterEpoch, l.Fence)
	oldAt := time.Date(2000, 1, 1, 0, 0, 0, 0, time.UTC)
	// Synthetic old audit reader fixture, never a current RPC success claim.
	if _, err = db.Collection("rm_tx_execution").UpdateOne(t.Context(), bson.M{"_id": ek[:]}, bson.M{"$set": bson.M{"witnesses.0.final_outcome": transaction.FinalCommitConfirmed, "witnesses.0.final_recorded_at": oldAt, "witnesses.0.final_error_code": ""}}); err != nil {
		t.Fatal(err)
	}
	before, err := reader.Snapshot(t.Context(), l, index)
	if err != nil || before.BeforeFinalAt == nil || !before.BeforeFinalAt.Equal(oldAt) {
		t.Fatal("old Mongo audit lost", err)
	}
	t.Run("borrowed-original-session-is-refused", func(t *testing.T) {
		result, e := reader.Snapshot(sc, l, index)
		if e == nil || !reflect.DeepEqual(result, Snapshot{}) {
			t.Fatal("borrowed session accepted")
		}
	})
	for _, scenario := range []string{"wrong-fence", "wrong-index", "wrong-current-epoch", "missing-final-time"} {
		t.Run(scenario, func(t *testing.T) {
			locator, notice := l, index
			switch scenario {
			case "wrong-fence":
				locator.Fence++
			case "wrong-index":
				notice[0] ^= 1
			case "wrong-current-epoch":
				if _, e := db.Collection("rm_tx_binding").UpdateOne(t.Context(), bson.M{"_id": b.Owner}, bson.M{"$set": bson.M{"writer_epoch": "different"}}); e != nil {
					t.Fatal(e)
				}
				defer func() {
					if _, e := db.Collection("rm_tx_binding").UpdateOne(t.Context(), bson.M{"_id": b.Owner}, bson.M{"$set": bson.M{"writer_epoch": b.WriterEpoch}}); e != nil {
						t.Error(e)
					}
				}()
			case "missing-final-time":
				if _, e := db.Collection("rm_tx_execution").UpdateOne(t.Context(), bson.M{"_id": ek[:]}, bson.M{"$unset": bson.M{"witnesses.0.final_recorded_at": ""}}); e != nil {
					t.Fatal(e)
				}
				defer func() {
					if _, e := db.Collection("rm_tx_execution").UpdateOne(t.Context(), bson.M{"_id": ek[:]}, bson.M{"$set": bson.M{"witnesses.0.final_recorded_at": oldAt}}); e != nil {
						t.Error(e)
					}
				}()
			}
			result, e := reader.Snapshot(t.Context(), locator, notice)
			if e == nil || !reflect.DeepEqual(result, Snapshot{}) {
				t.Fatal("invalid Mongo authority returned partial facts")
			}
		})
	}
	t.Run("same-original-facts-no-new-transaction-or-business", func(t *testing.T) {
		for _, name := range []string{"rm_tx_request", "rm_tx_execution", "native_test_fact", "messaging_native_limit_notices"} {
			count, e := db.Collection(name).CountDocuments(t.Context(), bson.M{})
			if e != nil || count != 1 {
				t.Fatal("original Mongo facts changed", e)
			}
		}
		final, e := reader.Snapshot(t.Context(), l, index)
		if e != nil || !reflect.DeepEqual(final, before) || final.DatabaseIdentitySHA256 != original.DatabaseIdentitySHA256 {
			t.Fatal("read-only snapshot changed original facts", e)
		}
	})

	t.Run("controlled-governance-storage-not-rpc-proof", func(t *testing.T) { mongoResolutionStorageFixture(t, db, reader, original) })
}
