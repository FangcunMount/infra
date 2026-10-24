package authority

import (
	"context"
	"errors"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
	"go.mongodb.org/mongo-driver/mongo/readconcern"
	"go.mongodb.org/mongo-driver/mongo/readpref"
	"go.mongodb.org/mongo-driver/mongo/writeconcern"
)

// ResolveNotice is a conditional storage primitive, not an authorization or
// RPC-success endpoint. The caller must validate the full independent approval
// and actual-RPC receipt and keep binding/schema writers excluded by the owned
// operation lock. No binding, SDK execution, witness, business or Outbox is written.
func (s *Mongo) ResolveNotice(ctx context.Context, r Resolution) (result ResolutionResult, err error) {
	result.Outcome = GovernanceNotAttempted
	if !r.valid() || r.Reviewed.Binding != s.binding || mongo.SessionFromContext(ctx) != nil {
		return result, ErrResolution
	}
	ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	identity, err := s.prepare(ctx)
	if err != nil {
		return result, err
	}
	session, err := s.db.Client().StartSession()
	if err != nil {
		return result, err
	}
	defer session.EndSession(ctx)
	if err = session.StartTransaction(options.Transaction().SetReadPreference(readpref.Primary()).SetReadConcern(readconcern.Snapshot()).SetWriteConcern(writeconcern.Majority())); err != nil {
		return result, err
	}
	sc := mongo.NewSessionContext(ctx, session)
	commitAttempted := false
	defer func() {
		if !commitAttempted {
			err = errors.Join(err, session.AbortTransaction(sc))
		}
	}()
	current, err := s.snapshotIn(sc, identity, r.locator(), r.Reviewed.Notice.IndexSHA256)
	if err != nil {
		return result, err
	}
	if !r.matches(current) {
		return result, ErrResolution
	}
	if current.Notice.Status == "resolved" {
		result.Outcome = GovernanceAlreadyResolved
		return result, nil
	}
	filter := bson.M{"_id": current.Notice.Key[:], "owner": s.binding.Owner, "store_id": s.binding.StoreID, "writer_epoch": s.binding.WriterEpoch, "route_revision": "m3-1", "schema_version": 1, "native_index_sha256": current.Notice.IndexSHA256[:], "evidence_sha256": current.Notice.FirstEvidenceSHA256[:], "status": "blocked", "resolved_at": nil, "resolution_receipt_sha256": nil}
	changed, err := s.db.Collection("messaging_native_limit_notices").UpdateOne(sc, filter, bson.M{"$set": bson.M{"status": "resolved", "resolution_receipt_sha256": r.ReceiptSHA256[:]}, "$currentDate": bson.M{"resolved_at": true}})
	if err != nil {
		return result, err
	}
	if changed.MatchedCount != 1 || changed.ModifiedCount != 1 {
		return result, ErrResolution
	}
	// No WithTransaction callback/retry. A conflict before commit is a failed
	// attempt; a commit error remains Unknown and must be verified independently.
	commitAttempted = true
	result.Outcome = GovernanceUnknown
	if err = session.CommitTransaction(sc); err != nil {
		return result, err
	}
	result.Outcome = GovernanceCommitted
	return result, nil
}

func (s *Mongo) VerifyResolution(ctx context.Context, r Resolution) error {
	if !r.valid() || r.Reviewed.Binding != s.binding || mongo.SessionFromContext(ctx) != nil {
		return ErrResolution
	}
	current, err := s.Snapshot(ctx, r.locator(), r.Reviewed.Notice.IndexSHA256)
	if err != nil {
		return err
	}
	if current.Notice.Status != "resolved" || !r.matches(current) {
		return ErrResolution
	}
	return nil
}
