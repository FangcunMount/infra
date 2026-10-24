package authority

import (
	"bytes"
	"context"
	"encoding/hex"
	"errors"
	"time"

	txmongo "github.com/FangcunMount/reliable-messaging/storage/transaction/mongo"
	"github.com/FangcunMount/reliable-messaging/transaction"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/bsontype"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
	"go.mongodb.org/mongo-driver/mongo/readconcern"
	"go.mongodb.org/mongo-driver/mongo/readpref"
	"go.mongodb.org/mongo-driver/mongo/writeconcern"
)

type Mongo struct {
	db      *mongo.Database
	binding transaction.Binding
}

func NewMongo(db *mongo.Database, b transaction.Binding) (*Mongo, error) {
	if db == nil || db.Client() == nil || db.Name() == "" || !validBinding(b, true) {
		return nil, transaction.ErrBinding
	}
	primary := db.Client().Database(db.Name(), options.Database().SetReadPreference(readpref.Primary()).SetReadConcern(readconcern.Majority()).SetWriteConcern(writeconcern.Majority()))
	return &Mongo{primary, b}, nil
}

func (s *Mongo) CheckStore() (transaction.PreparedStore, error) { return txmongo.New(s.db, s.binding) }

type mongoWitness struct {
	Reference  []byte                   `bson:"reference"`
	State      transaction.State        `bson:"state"`
	Half       transaction.HalfOutcome  `bson:"half_outcome"`
	Final      transaction.FinalOutcome `bson:"final_outcome"`
	FinalAt    *time.Time               `bson:"final_recorded_at"`
	FinalError string                   `bson:"final_error_code"`
}
type mongoExecution struct {
	ID        []byte            `bson:"_id"`
	Owner     string            `bson:"owner"`
	Epoch     string            `bson:"writer_epoch"`
	Fence     int64             `bson:"fence"`
	State     transaction.State `bson:"state"`
	Witnesses []mongoWitness    `bson:"witnesses"`
}

// Mongo projection excludes the plan, execution capability, wire, and Broker
// transaction handles. Only bounded branch references and audit are decoded.
func mongoProjection() bson.M {
	return bson.M{"_id": 1, "owner": 1, "writer_epoch": 1, "fence": 1, "state": 1,
		"witnesses.reference": 1, "witnesses.state": 1, "witnesses.half_outcome": 1,
		"witnesses.final_outcome": 1, "witnesses.final_recorded_at": 1, "witnesses.final_error_code": 1}
}

func decodeMongoExecution(raw bson.Raw, b transaction.Binding, l Locator) (mongoExecution, transaction.Reference, mongoWitness, error) {
	var execution mongoExecution
	if len(raw) > transaction.MaxBranches*(16384+1024) || !validBinding(b, true) || !l.valid() || raw.Lookup("_id").Type != bsontype.Binary || raw.Lookup("fence").Type != bsontype.Int64 || raw.Lookup("witnesses").Type != bsontype.Array || bson.Unmarshal(raw, &execution) != nil {
		return execution, transaction.Reference{}, mongoWitness{}, ErrSnapshot
	}
	ek := transaction.ExecutionKey(b.Owner, l.OperationID, b.WriterEpoch, l.Fence)
	if !bytes.Equal(execution.ID, ek[:]) || execution.Owner != b.Owner || execution.Epoch != b.WriterEpoch || execution.Fence != int64(l.Fence) || len(execution.Witnesses) < 1 || len(execution.Witnesses) > transaction.MaxBranches {
		return execution, transaction.Reference{}, mongoWitness{}, ErrSnapshot
	}
	seen := map[string]bool{}
	var target transaction.Reference
	var branch mongoWitness
	for _, w := range execution.Witnesses {
		if len(w.Reference) > 16384 {
			return execution, target, branch, ErrSnapshot
		}
		ref, err := transaction.DecodeReference(w.Reference)
		if err != nil || ref.Owner != b.Owner || ref.WriterEpoch != b.WriterEpoch || ref.OperationID != l.OperationID || ref.Fence != l.Fence || seen[ref.BranchID] {
			return execution, target, branch, ErrSnapshot
		}
		seen[ref.BranchID] = true
		if ref.BranchID == l.BranchID {
			target, branch = ref, w
		}
	}
	if !target.Valid() {
		return execution, target, branch, ErrSnapshot
	}
	return execution, target, branch, nil
}

func (s *Mongo) primaryIdentity(ctx context.Context) ([32]byte, error) {
	var hello struct {
		Primary bool   `bson:"isWritablePrimary"`
		Set     string `bson:"setName"`
	}
	if err := s.db.RunCommand(ctx, bson.D{{Key: "hello", Value: 1}}).Decode(&hello); err != nil {
		return [32]byte{}, err
	}
	if !hello.Primary || hello.Set == "" {
		return [32]byte{}, ErrSnapshot
	}
	specs, err := s.db.ListCollectionSpecifications(ctx, bson.M{"name": bson.M{"$in": bson.A{"rm_tx_binding", "messaging_native_limit_notices"}}})
	if err != nil {
		return [32]byte{}, err
	}
	if len(specs) != 2 {
		return [32]byte{}, ErrSnapshot
	}
	var uuid []byte
	for _, spec := range specs {
		if spec == nil || spec.Type != "collection" || spec.ReadOnly {
			return [32]byte{}, ErrSnapshot
		}
		collation := spec.Options.Lookup("collation")
		if collation.Type != 0 {
			document, ok := collation.DocumentOK()
			if !ok {
				return [32]byte{}, ErrSnapshot
			}
			locale := document.Lookup("locale")
			if locale.Type != bsontype.String || locale.StringValue() != "simple" {
				return [32]byte{}, ErrSnapshot
			}
		}
		if spec.Name == "rm_tx_binding" {
			if spec.UUID == nil || spec.UUID.Subtype != 4 || len(spec.UUID.Data) != 16 {
				return [32]byte{}, ErrSnapshot
			}
			uuid = spec.UUID.Data
		}
	}
	if len(uuid) != 16 {
		return [32]byte{}, ErrSnapshot
	}
	return databaseIdentity("mongo", hello.Set, s.db.Name(), hex.EncodeToString(uuid)), nil
}

// Snapshot reads a fresh primary/snapshot session, never the business session.
// No transaction callback is retried, no document is written, and the read root
// ends with AbortTransaction rather than a manufactured business commit.
func (s *Mongo) Snapshot(ctx context.Context, l Locator, index [32]byte) (out Snapshot, err error) {
	if !l.valid() || index == [32]byte{} || mongo.SessionFromContext(ctx) != nil {
		return out, ErrSnapshot
	}
	ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	identity, err := s.prepare(ctx)
	if err != nil {
		return out, err
	}
	session, err := s.db.Client().StartSession()
	if err != nil {
		return out, err
	}
	defer session.EndSession(ctx)
	if err = session.StartTransaction(options.Transaction().SetReadPreference(readpref.Primary()).SetReadConcern(readconcern.Snapshot()).SetWriteConcern(writeconcern.Majority())); err != nil {
		return out, err
	}
	sc := mongo.NewSessionContext(ctx, session)
	defer func() {
		err = errors.Join(err, session.AbortTransaction(sc), ctx.Err())
		if err != nil {
			out = Snapshot{}
		}
	}()
	return s.snapshotIn(sc, identity, l, index)
}

func (s *Mongo) prepare(ctx context.Context) ([32]byte, error) {
	store, err := txmongo.New(s.db, s.binding)
	if err != nil {
		return [32]byte{}, err
	}
	if err = store.ValidateSchema(ctx); err != nil {
		return [32]byte{}, err
	}
	return s.primaryIdentity(ctx)
}

// snapshotIn reads only, borrowing this operation's private root session.
func (s *Mongo) snapshotIn(sc mongo.SessionContext, identity [32]byte, l Locator, index [32]byte) (out Snapshot, err error) {
	var binding struct {
		Store  string `bson:"store_id"`
		Epoch  string `bson:"writer_epoch"`
		Schema int    `bson:"schema_version"`
	}
	if err = s.db.Collection("rm_tx_binding").FindOne(sc, bson.M{"_id": s.binding.Owner}).Decode(&binding); err != nil {
		return out, err
	}
	if binding.Store != s.binding.StoreID || binding.Epoch != s.binding.WriterEpoch || binding.Schema != 1 {
		return out, transaction.ErrBinding
	}
	var marker struct {
		Version int `bson:"version"`
	}
	if err = s.db.Collection("messaging_native_limit_schema").FindOne(sc, bson.M{"_id": "v1"}).Decode(&marker); err != nil {
		return out, err
	}
	if marker.Version != 1 {
		return out, transaction.ErrSchema
	}
	ek := transaction.ExecutionKey(s.binding.Owner, l.OperationID, s.binding.WriterEpoch, l.Fence)
	var raw bson.Raw
	if err = s.db.Collection("rm_tx_execution").FindOne(sc, bson.M{"_id": ek[:]}, options.FindOne().SetProjection(mongoProjection())).Decode(&raw); err != nil {
		return out, err
	}
	execution, ref, witness, err := decodeMongoExecution(raw, s.binding, l)
	if err != nil {
		return out, err
	}
	out.Binding = s.binding
	out.Reference = ref
	out.DatabaseIdentitySHA256 = identity
	out.Decision = transaction.Resolve(ref, &transaction.Evidence{Reference: ref, ExecutionState: execution.State, BranchState: witness.State})
	out.Half = witness.Half
	if out.Half == "" {
		out.Half = transaction.HalfNotAttempted
	}
	out.BeforeFinal = witness.Final
	if out.BeforeFinal == "" {
		out.BeforeFinal = transaction.FinalNotAttempted
	}
	out.BeforeFinalAt = witness.FinalAt
	key := NoticeKey(s.binding, index)
	var notice struct {
		Key      []byte     `bson:"_id"`
		Owner    string     `bson:"owner"`
		Store    string     `bson:"store_id"`
		Epoch    string     `bson:"writer_epoch"`
		Revision string     `bson:"route_revision"`
		Index    []byte     `bson:"native_index_sha256"`
		Proof    []byte     `bson:"evidence_sha256"`
		Status   string     `bson:"status"`
		Schema   int        `bson:"schema_version"`
		At       *time.Time `bson:"resolved_at"`
		Receipt  []byte     `bson:"resolution_receipt_sha256"`
	}
	if err = s.db.Collection("messaging_native_limit_notices").FindOne(sc, bson.M{"_id": key[:]}).Decode(&notice); err != nil {
		return out, err
	}
	if !bytes.Equal(notice.Key, key[:]) || notice.Owner != s.binding.Owner || notice.Store != binding.Store || notice.Epoch != binding.Epoch || notice.Revision != "m3-1" || notice.Schema != 1 || !bytes.Equal(notice.Index, index[:]) || len(notice.Proof) != 32 {
		return out, ErrSnapshot
	}
	out.Notice = Notice{Key: key, IndexSHA256: index, Status: notice.Status, ResolvedAt: notice.At, ResolutionReceiptSHA256: notice.Receipt}
	copy(out.Notice.FirstEvidenceSHA256[:], notice.Proof)
	if err = validateSnapshot(out, l, execution.State, witness.State, witness.FinalError); err != nil {
		return out, err
	}
	return out, nil
}
