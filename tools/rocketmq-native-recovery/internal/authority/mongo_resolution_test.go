package authority

import (
	"context"
	"errors"
	"testing"

	"go.mongodb.org/mongo-driver/mongo"
)

type unusableSession struct{ mongo.Session } // Any session operation would panic.

func TestMongoResolutionRefusesInvalidInputAndBorrowedSessionBeforeIO(t *testing.T) {
	_, b, _, ref := mongoRowFixture(t)
	s, _ := snapshotFixture(t)
	s.Binding = b
	s.Reference = ref
	s.Notice.Key = NoticeKey(b, s.Notice.IndexSHA256)
	r := storageResolutionFixture(t, s)
	reader, err := NewMongo(new(mongo.Client).Database("owned"), b)
	if err != nil {
		t.Fatal(err)
	}
	if !r.valid() {
		t.Fatal("controlled precondition fixture invalid")
	}
	ctx := mongo.NewSessionContext(context.Background(), &unusableSession{})
	result, err := reader.ResolveNotice(ctx, r)
	if !errors.Is(err, ErrResolution) || result.Outcome != GovernanceNotAttempted {
		t.Fatal("borrowed session accepted or touched")
	}
	if err = reader.VerifyResolution(ctx, r); !errors.Is(err, ErrResolution) {
		t.Fatal("verification borrowed original session")
	}
	r.ReceiptSHA256 = [32]byte{}
	result, err = reader.ResolveNotice(context.Background(), r)
	if !errors.Is(err, ErrResolution) || result.Outcome != GovernanceNotAttempted {
		t.Fatal("invalid proof touched client")
	}
}
