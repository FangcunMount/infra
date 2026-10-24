//go:build integration

package authority

import (
	"errors"
	"testing"
	"time"

	"github.com/FangcunMount/reliable-messaging/transaction"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
)

// Real Mongo storage with deliberately synthetic approval/RPC metadata. It
// cannot substitute for the later complete controlled CLI or actual MQ gate.
func mongoResolutionStorageFixture(t *testing.T, db *mongo.Database, reader *Mongo, reviewed Snapshot) {
	t.Helper()
	r := storageResolutionFixture(t, reviewed)
	key := reviewed.Notice.Key
	ek := transaction.ExecutionKey(reviewed.Binding.Owner, reviewed.Reference.OperationID, reviewed.Binding.WriterEpoch, reviewed.Reference.Fence)
	oldAt := time.Date(2000, 1, 1, 0, 0, 0, 0, time.UTC)
	t.Run("current-positive-metadata-without-db-audit-refused", func(t *testing.T) {
		if _, err := db.Collection("rm_tx_execution").UpdateOne(t.Context(), bson.M{"_id": ek[:]}, bson.M{"$set": bson.M{"witnesses.0.final_outcome": transaction.FinalUnknown}, "$unset": bson.M{"witnesses.0.final_recorded_at": ""}}); err != nil {
			t.Fatal(err)
		}
		result, err := reader.ResolveNotice(t.Context(), r)
		if !errors.Is(err, ErrResolution) || result.Outcome != GovernanceNotAttempted {
			t.Fatal("missing actual DB audit accepted", err)
		}
		if _, err = db.Collection("rm_tx_execution").UpdateOne(t.Context(), bson.M{"_id": ek[:]}, bson.M{"$set": bson.M{"witnesses.0.final_outcome": transaction.FinalCommitConfirmed, "witnesses.0.final_recorded_at": oldAt}}); err != nil {
			t.Fatal(err)
		}
	})
	t.Run("actual-governance-write-conflict-keeps-original-row", func(t *testing.T) {
		session, err := db.Client().StartSession()
		if err != nil {
			t.Fatal(err)
		}
		defer session.EndSession(t.Context())
		if err = session.StartTransaction(); err != nil {
			t.Fatal(err)
		}
		held := mongo.NewSessionContext(t.Context(), session)
		if _, err = db.Collection("messaging_native_limit_notices").UpdateOne(held, bson.M{"_id": key[:]}, bson.M{"$set": bson.M{"evidence_sha256": make([]byte, 32)}}); err != nil {
			_ = session.AbortTransaction(held)
			t.Fatal(err)
		}
		started := time.Now()
		result, err := reader.ResolveNotice(t.Context(), r)
		if e := session.AbortTransaction(held); e != nil {
			t.Fatal(e)
		}
		var labelled interface{ HasErrorLabel(string) bool }
		if err == nil || result.Outcome != GovernanceNotAttempted || !errors.As(err, &labelled) || !labelled.HasErrorLabel("TransientTransactionError") || time.Since(started) > 1500*time.Millisecond {
			t.Fatal("actual write conflict was not returned without a callback retry", err)
		}
		current, e := reader.Snapshot(t.Context(), r.locator(), reviewed.Notice.IndexSHA256)
		if e != nil || current.Notice.Status != "blocked" || current.Notice.FirstEvidenceSHA256 != reviewed.Notice.FirstEvidenceSHA256 {
			t.Fatal("write conflict changed original evidence", e)
		}
	})
	t.Run("two-original-roots-allow-one-governance-write", func(t *testing.T) {
		type answer struct {
			result ResolutionResult
			err    error
		}
		answers := make(chan answer, 2)
		for range 2 {
			go func() { result, err := reader.ResolveNotice(t.Context(), r); answers <- answer{result, err} }()
		}
		committed, already, conflicted := 0, 0, 0
		for range 2 {
			a := <-answers
			switch {
			case a.err == nil && a.result.Outcome == GovernanceCommitted:
				committed++
			case a.err == nil && a.result.Outcome == GovernanceAlreadyResolved:
				already++
			case a.err != nil && a.result.Outcome == GovernanceNotAttempted:
				conflicted++
			default:
				t.Errorf("unexpected competing root result: %s", a.result.Outcome)
			}
		}
		if committed != 1 || already+conflicted != 1 {
			t.Fatal("competing Mongo roots wrote more than once", committed, already, conflicted)
		}
		if err := reader.VerifyResolution(t.Context(), r); err != nil {
			t.Fatal("independent verify did not converge", err)
		}
	})
	first, err := reader.Snapshot(t.Context(), r.locator(), reviewed.Notice.IndexSHA256)
	if err != nil || first.Notice.ResolvedAt == nil || first.BeforeFinalAt == nil || !first.BeforeFinalAt.Equal(oldAt) {
		t.Fatal("first native or SDK audit lost", err)
	}
	t.Run("repeat-preserves-first-times-and-different-receipt-refused", func(t *testing.T) {
		result, e := reader.ResolveNotice(t.Context(), r)
		if e != nil || result.Outcome != GovernanceAlreadyResolved {
			t.Fatal(result, e)
		}
		other := r
		other.ReceiptSHA256[0] ^= 1
		result, e = reader.ResolveNotice(t.Context(), other)
		if !errors.Is(e, ErrResolution) || result.Outcome != GovernanceNotAttempted {
			t.Fatal("different receipt overwrote first governance", e)
		}
		if e = reader.VerifyResolution(t.Context(), other); !errors.Is(e, ErrResolution) {
			t.Fatal("different receipt verified")
		}
		again, e := reader.Snapshot(t.Context(), r.locator(), reviewed.Notice.IndexSHA256)
		if e != nil || again.Notice.ResolvedAt == nil || !again.Notice.ResolvedAt.Equal(*first.Notice.ResolvedAt) || again.BeforeFinalAt == nil || !again.BeforeFinalAt.Equal(oldAt) || again.Notice.FirstEvidenceSHA256 != reviewed.Notice.FirstEvidenceSHA256 {
			t.Fatal("repeat rewrote original proof", e)
		}
	})
	t.Run("new-native-index-stays-blocked-without-new-business-or-sdk-record", func(t *testing.T) {
		index := [32]byte{99}
		next := NoticeKey(reviewed.Binding, index)
		proof := reviewed.Notice.FirstEvidenceSHA256
		if _, err := db.Collection("messaging_native_limit_notices").InsertOne(t.Context(), bson.M{"_id": next[:], "owner": reviewed.Binding.Owner, "store_id": reviewed.Binding.StoreID, "writer_epoch": reviewed.Binding.WriterEpoch, "route_revision": "m3-1", "native_index_sha256": index[:], "evidence_sha256": proof[:], "status": "blocked", "schema_version": 1, "recorded_at": time.Now().UTC()}); err != nil {
			t.Fatal(err)
		}
		blocked, e := db.Collection("messaging_native_limit_notices").CountDocuments(t.Context(), bson.M{"owner": reviewed.Binding.Owner, "status": "blocked"})
		if e != nil || blocked != 1 {
			t.Fatal("unselected index responsibility cleared", e)
		}
		for _, name := range []string{"rm_tx_request", "rm_tx_execution", "native_test_fact"} {
			count, e := db.Collection(name).CountDocuments(t.Context(), bson.M{})
			if e != nil || count != 1 {
				t.Fatal("governance write changed original facts", e)
			}
		}
	})
}
