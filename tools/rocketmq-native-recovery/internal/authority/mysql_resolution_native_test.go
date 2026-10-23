//go:build integration

package authority

import (
	"context"
	"database/sql"
	"errors"
	"github.com/FangcunMount/reliable-messaging/transaction"
	"testing"
	"time"
)

// Real SQL storage CAS with synthetic reviewed-receipt input. This proves
// conditional database behavior, NOT actual RPC, approval or production use.
func mysqlResolutionStorageFixture(t *testing.T, db *sql.DB, reader *MySQL, reviewed Snapshot) {
	t.Helper()
	r := storageResolutionFixture(t, reviewed)
	t.Run("fresh-positive-audit-required-despite-positive-input", func(t *testing.T) {
		if _, err := db.ExecContext(t.Context(), `UPDATE rm_tx_witness SET final_outcome='unknown',final_recorded_at=NULL WHERE execution_key=? AND branch_key=?`, executionKeyFor(reviewed.Reference), branchKeyFor(reviewed.Reference)); err != nil {
			t.Fatal(err)
		}
		result, err := reader.ResolveNotice(t.Context(), r)
		if !errors.Is(err, ErrResolution) || result.Outcome != GovernanceNotAttempted {
			t.Fatal("non-positive fresh evidence allowed CAS", err)
		}
		if _, err = db.ExecContext(t.Context(), `UPDATE rm_tx_witness SET final_outcome='commit_confirmed',final_recorded_at='2000-01-01 00:00:00.000000' WHERE execution_key=? AND branch_key=?`, executionKeyFor(reviewed.Reference), branchKeyFor(reviewed.Reference)); err != nil {
			t.Fatal(err)
		}
		current, err := reader.Snapshot(t.Context(), r.locator(), reviewed.Notice.IndexSHA256)
		if err != nil || current.Notice.Status != "blocked" {
			t.Fatal("failed CAS changed governance", err)
		}
	})
	t.Run("real-row-lock-respects-caller-budget", func(t *testing.T) {
		locker, err := db.BeginTx(t.Context(), nil)
		if err != nil {
			t.Fatal(err)
		}
		var key []byte
		if err = locker.QueryRowContext(t.Context(), `SELECT notice_key FROM messaging_native_limit_notices WHERE notice_key=? FOR UPDATE`, reviewed.Notice.Key[:]).Scan(&key); err != nil {
			_ = locker.Rollback()
			t.Fatal(err)
		}
		ctx, cancel := context.WithTimeout(t.Context(), 100*time.Millisecond)
		started := time.Now()
		result, err := reader.ResolveNotice(ctx, r)
		cancel()
		if e := locker.Rollback(); e != nil {
			t.Fatal(e)
		}
		if err == nil || result.Outcome != GovernanceNotAttempted || time.Since(started) > 3*time.Second {
			t.Fatal("row-lock wait was not bounded before commit", err)
		}
	})
	t.Run("two-real-roots-one-write-same-receipt-is-idempotent", func(t *testing.T) {
		type answer struct {
			result ResolutionResult
			err    error
		}
		answers := make(chan answer, 2)
		for range 2 {
			go func() { result, err := reader.ResolveNotice(t.Context(), r); answers <- answer{result, err} }()
		}
		counts := map[GovernanceOutcome]int{}
		var failures error
		for range 2 {
			a := <-answers
			failures = errors.Join(failures, a.err)
			counts[a.result.Outcome]++
		}
		if failures != nil {
			t.Fatal(failures)
		}
		if counts[GovernanceCommitted] != 1 || counts[GovernanceAlreadyResolved] != 1 {
			t.Fatal("competing roots rewrote governance", counts)
		}
	})
	first, err := reader.Snapshot(t.Context(), r.locator(), reviewed.Notice.IndexSHA256)
	if err != nil || first.Notice.Status != "resolved" || first.Notice.ResolvedAt == nil || first.BeforeFinalAt == nil || first.BeforeFinalAt.Year() != 2000 || first.Notice.FirstEvidenceSHA256 != reviewed.Notice.FirstEvidenceSHA256 {
		t.Fatal("first SDK audit or native evidence changed", err)
	}
	t.Run("independent-verify-and-repeat-preserve-first-times", func(t *testing.T) {
		if err := reader.VerifyResolution(t.Context(), r); err != nil {
			t.Fatal(err)
		}
		result, err := reader.ResolveNotice(t.Context(), r)
		if err != nil || result.Outcome != GovernanceAlreadyResolved {
			t.Fatal(result, err)
		}
		again, err := reader.Snapshot(t.Context(), r.locator(), reviewed.Notice.IndexSHA256)
		if err != nil || again.Notice.ResolvedAt == nil || !again.Notice.ResolvedAt.Equal(*first.Notice.ResolvedAt) || again.BeforeFinalAt == nil || !again.BeforeFinalAt.Equal(*first.BeforeFinalAt) {
			t.Fatal("repeat refreshed first evidence", err)
		}
	})
	t.Run("different-receipt-cannot-overwrite-resolved-row", func(t *testing.T) {
		changed := r
		changed.ReceiptSHA256[0] ^= 1
		result, err := reader.ResolveNotice(t.Context(), changed)
		if !errors.Is(err, ErrResolution) || result.Outcome != GovernanceNotAttempted {
			t.Fatal("different receipt overwrote resolution", err)
		}
		if err = reader.VerifyResolution(t.Context(), changed); !errors.Is(err, ErrResolution) {
			t.Fatal("foreign receipt verified")
		}
		if err = reader.VerifyResolution(t.Context(), r); err != nil {
			t.Fatal(err)
		}
	})
	t.Run("other-physical-index-stays-blocked-and-original-facts-stay", func(t *testing.T) {
		var blocked int
		if err := db.QueryRowContext(t.Context(), `SELECT COUNT(*) FROM messaging_native_limit_notices WHERE owner=? AND status='blocked'`, []byte(reviewed.Binding.Owner)).Scan(&blocked); err != nil || blocked != 1 {
			t.Fatal("single-index CAS cleared unrelated responsibility", err)
		}
		for _, table := range []string{"rm_tx_request", "rm_tx_execution", "rm_tx_witness", "native_test_fact"} {
			var count int
			want := 2
			if table == "native_test_fact" {
				want = 1
			}
			if err := db.QueryRowContext(t.Context(), `SELECT COUNT(*) FROM `+table).Scan(&count); err != nil || count != want {
				t.Fatal("governance CAS rewrote original facts", err)
			}
		}
	})
}

func executionKeyFor(ref transaction.Reference) []byte {
	key := transaction.ExecutionKey(ref.Owner, ref.OperationID, ref.WriterEpoch, ref.Fence)
	return key[:]
}
func branchKeyFor(ref transaction.Reference) []byte {
	key := transaction.BranchKey(ref.BranchID)
	return key[:]
}
