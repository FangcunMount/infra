package authority

import (
	"bytes"
	"context"
	"database/sql"
	"errors"
	"time"

	txmysql "github.com/FangcunMount/reliable-messaging/storage/transaction/mysql"
	"github.com/FangcunMount/reliable-messaging/transaction"
)

type MySQL struct {
	db      *sql.DB
	binding transaction.Binding
}

// NewMySQL borrows the caller's explicitly selected original-primary pool.
// It neither connects nor installs schema or binding.
func NewMySQL(db *sql.DB, b transaction.Binding) (*MySQL, error) {
	if db == nil || !validBinding(b, false) {
		return nil, transaction.ErrBinding
	}
	return &MySQL{db, b}, nil
}

func (s *MySQL) CheckStore() (transaction.PreparedStore, error) { return txmysql.New(s.db, s.binding) }

// Snapshot starts a fresh read-only root with a two-second total budget. No
// plan/token/wire/business body is selected; no SDK recorder or writer is used.
func (s *MySQL) Snapshot(ctx context.Context, l Locator, index [32]byte) (out Snapshot, err error) {
	if !l.valid() || index == [32]byte{} {
		return out, ErrSnapshot
	}
	ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelRepeatableRead, ReadOnly: true})
	if err != nil {
		return out, err
	}
	defer func() {
		rollbackErr := tx.Rollback()
		if errors.Is(rollbackErr, sql.ErrTxDone) {
			rollbackErr = nil
		}
		err = errors.Join(err, ctx.Err(), rollbackErr)
		if err != nil {
			out = Snapshot{}
		}
	}()
	// Read-only applies to this transaction; these flags additionally reject a
	// configured replica. The reviewed UUID/database digest freezes actual identity.
	var uuid, database string
	var readOnly, superReadOnly bool
	if err = tx.QueryRowContext(ctx, `SELECT @@server_uuid,DATABASE(),@@global.read_only,@@global.super_read_only`).Scan(&uuid, &database, &readOnly, &superReadOnly); err != nil {
		return out, err
	}
	if uuid == "" || database == "" || readOnly || superReadOnly {
		return out, ErrSnapshot
	}
	var store, epoch []byte
	var schema int
	if err = tx.QueryRowContext(ctx, `SELECT store_id,writer_epoch,schema_version FROM rm_tx_binding WHERE owner=?`, []byte(s.binding.Owner)).Scan(&store, &epoch, &schema); err != nil {
		return out, err
	}
	if schema != 1 || !bytes.Equal(store, []byte(s.binding.StoreID)) || !bytes.Equal(epoch, []byte(s.binding.WriterEpoch)) {
		return out, transaction.ErrBinding
	}
	ek, bk := transaction.ExecutionKey(s.binding.Owner, l.OperationID, s.binding.WriterEpoch, l.Fence), transaction.BranchKey(l.BranchID)
	var owner, operation, writer, raw []byte
	var fence uint64
	var execution, branch transaction.State
	var finalError string
	if err = tx.QueryRowContext(ctx, `SELECT e.owner,e.operation_id,e.writer_epoch,e.fence,e.state,w.reference,w.state,w.half_outcome,w.final_outcome,w.final_recorded_at,w.final_error_code FROM rm_tx_execution e JOIN rm_tx_witness w ON w.execution_key=e.execution_key WHERE e.execution_key=? AND w.branch_key=?`, ek[:], bk[:]).Scan(&owner, &operation, &writer, &fence, &execution, &raw, &branch, &out.Half, &out.BeforeFinal, &out.BeforeFinalAt, &finalError); err != nil {
		return out, err
	}
	if !bytes.Equal(owner, []byte(s.binding.Owner)) || !bytes.Equal(operation, []byte(l.OperationID)) || !bytes.Equal(writer, []byte(s.binding.WriterEpoch)) || fence != l.Fence || len(raw) > 16384 {
		return out, ErrSnapshot
	}
	out.Reference, err = transaction.DecodeReference(raw)
	if err != nil {
		return out, ErrSnapshot
	}
	out.Binding = s.binding
	out.DatabaseIdentitySHA256 = databaseIdentity("mysql", uuid, database)
	out.Decision = transaction.Resolve(out.Reference, &transaction.Evidence{Reference: out.Reference, ExecutionState: execution, BranchState: branch})
	key := NoticeKey(s.binding, index)
	var actualKey, noticeOwner, noticeStore, noticeEpoch, revision, actualIndex, proof []byte
	if err = tx.QueryRowContext(ctx, `SELECT notice_key,owner,store_id,writer_epoch,route_revision,native_index_sha256,evidence_sha256,status,schema_version,resolved_at,resolution_receipt_sha256 FROM messaging_native_limit_notices WHERE notice_key=?`, key[:]).Scan(&actualKey, &noticeOwner, &noticeStore, &noticeEpoch, &revision, &actualIndex, &proof, &out.Notice.Status, &schema, &out.Notice.ResolvedAt, &out.Notice.ResolutionReceiptSHA256); err != nil {
		return out, err
	}
	if schema != 1 || !bytes.Equal(actualKey, key[:]) || !bytes.Equal(noticeOwner, []byte(s.binding.Owner)) || !bytes.Equal(noticeStore, store) || !bytes.Equal(noticeEpoch, epoch) || string(revision) != "m3-1" || !bytes.Equal(actualIndex, index[:]) || len(proof) != 32 {
		return out, ErrSnapshot
	}
	out.Notice.Key = key
	out.Notice.IndexSHA256 = index
	copy(out.Notice.FirstEvidenceSHA256[:], proof)
	if err = validateSnapshot(out, l, execution, branch, finalError); err != nil {
		return out, err
	}
	// A read-only rollback ends the snapshot; do not imply an audited write.
	return out, nil
}
