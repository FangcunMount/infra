package authority

import (
	"context"
	"database/sql"
	"errors"
	"time"
)

// ResolveNotice is the original-primary conditional governance write primitive.
// Its caller owns approval and private actual-RPC proof validation. This method
// never supplies those proofs, changes SDK audit, or reopens host admission.
func (s *MySQL) ResolveNotice(ctx context.Context, r Resolution) (result ResolutionResult, err error) {
	result.Outcome = GovernanceNotAttempted
	if !r.valid() || r.Reviewed.Binding != s.binding {
		return result, ErrResolution
	}
	ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
	if err != nil {
		return result, err
	}
	defer func() {
		rollbackErr := tx.Rollback()
		if errors.Is(rollbackErr, sql.ErrTxDone) {
			rollbackErr = nil
		}
		err = errors.Join(err, rollbackErr)
	}()
	current, err := s.snapshotIn(ctx, tx, r.locator(), r.Reviewed.Notice.IndexSHA256, true)
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
	changed, err := tx.ExecContext(ctx, `UPDATE messaging_native_limit_notices SET status='resolved',resolved_at=UTC_TIMESTAMP(6),resolution_receipt_sha256=? WHERE notice_key=? AND status='blocked' AND evidence_sha256=? AND native_index_sha256=? AND resolved_at IS NULL AND resolution_receipt_sha256 IS NULL`, r.ReceiptSHA256[:], current.Notice.Key[:], current.Notice.FirstEvidenceSHA256[:], current.Notice.IndexSHA256[:])
	if err != nil {
		return result, err
	}
	count, err := changed.RowsAffected()
	if err != nil {
		return result, err
	}
	if count != 1 {
		return result, ErrResolution
	}
	// RowsAffected is not a committed governance change. A lost commit reply
	// remains Unknown; the caller must use a new verification read boundary.
	result.Outcome = GovernanceUnknown
	if err = tx.Commit(); err != nil {
		return result, err
	}
	result.Outcome = GovernanceCommitted
	return result, nil
}

// VerifyResolution performs no writes and can resolve an uncertain governance
// commit only by reading the exact receipt and positive SDK evidence anew.
func (s *MySQL) VerifyResolution(ctx context.Context, r Resolution) error {
	if !r.valid() || r.Reviewed.Binding != s.binding {
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
