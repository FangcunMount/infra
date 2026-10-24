//go:build integration

package authority

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"errors"
	"fmt"
	"os"
	"reflect"
	"testing"
	"time"

	"github.com/FangcunMount/reliable-messaging/message"
	txmysql "github.com/FangcunMount/reliable-messaging/storage/transaction/mysql"
	"github.com/FangcunMount/reliable-messaging/transaction"
	"github.com/FangcunMount/reliable-messaging/transport"
	driver "github.com/go-sql-driver/mysql"
)

func ownedMySQL(t *testing.T) *sql.DB {
	t.Helper()
	if os.Getenv("GITHUB_ACTIONS") != "true" || os.Getenv("RUNNER_ENVIRONMENT") != "github-hosted" || os.Getenv("GITHUB_REPOSITORY") != "FangcunMount/infra" {
		t.Fatal("required isolated GitHub-hosted environment missing")
	}
	c, err := driver.ParseDSN(os.Getenv("NATIVE_TOOL_TEST_MYSQL_DSN"))
	if err != nil || c.Net != "tcp" || c.Addr != "127.0.0.1:3306" {
		t.Fatal("required disposable loopback database missing")
	}
	c.DBName = ""
	c.ParseTime = true
	c.MultiStatements = true
	c.Timeout = 3 * time.Second
	c.ReadTimeout = 3 * time.Second
	c.WriteTimeout = 3 * time.Second
	server, err := sql.Open("mysql", c.FormatDSN())
	if err != nil {
		t.Fatal("open disposable server")
	}
	t.Cleanup(func() {
		if server.Close() != nil {
			t.Error("owned server pool close failed")
		}
	})
	name := fmt.Sprintf("m3_native_tool_test_%d", time.Now().UnixNano())
	if _, err = server.ExecContext(t.Context(), "CREATE DATABASE `"+name+"`"); err != nil {
		t.Fatal("create owned database failed")
	}
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if _, e := server.ExecContext(ctx, "DROP DATABASE `"+name+"`"); e != nil {
			t.Error("owned database cleanup failed")
			return
		}
		var count int
		if e := server.QueryRowContext(ctx, `SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name=?`, name).Scan(&count); e != nil || count != 0 {
			t.Error("owned database cleanup readback failed")
			return
		}
		t.Log("owned_database_removed=true")
	})
	c.DBName = name
	db, err := sql.Open("mysql", c.FormatDSN())
	if err != nil {
		t.Fatal("open owned primary failed")
	}
	db.SetMaxOpenConns(2)
	db.SetMaxIdleConns(2)
	t.Cleanup(func() {
		if db.Close() != nil {
			t.Error("owned primary pool close failed")
		}
	})
	for _, schema := range []string{txmysql.Schema, nativeNoticeSchema, `CREATE TABLE native_test_fact(id VARBINARY(128) PRIMARY KEY) ENGINE=InnoDB`} {
		if _, err = db.ExecContext(t.Context(), schema); err != nil {
			t.Fatal("explicit test fixture installation failed")
		}
	}
	return db
}

func TestMySQLSnapshotNative(t *testing.T) {
	for _, owner := range []string{"iam.mysql", "qs.mysql", "ai.mysql"} {
		t.Run(owner, func(t *testing.T) {
			db := ownedMySQL(t)
			s, l := snapshotFixture(t)
			s.Binding.Owner = owner
			if _, err := db.ExecContext(t.Context(), `INSERT INTO rm_tx_binding VALUES(?,?,?,1)`, []byte(owner), []byte(s.Binding.StoreID), []byte(s.Binding.WriterEpoch)); err != nil {
				t.Fatal("install explicit owned binding")
			}
			base, err := txmysql.New(db, s.Binding)
			if err != nil {
				t.Fatal(err)
			}
			// Reuse only immutable test message data, then freeze it for this owner.
			p := nativePlanForOwner(t, s.Binding.Owner, l)
			reservation, err := base.Reserve(t.Context(), transaction.RequestFor(p), p, transaction.ReserveOptions{Lease: time.Hour})
			if err != nil || !reservation.Acquired {
				t.Fatal("reserve controlled fixture failed")
			}
			reference := reservation.Execution.References()[0]
			index := [32]byte{1}
			key := NoticeKey(s.Binding, index)
			proof := [32]byte{2}
			if _, err = db.ExecContext(t.Context(), `INSERT INTO messaging_native_limit_notices(notice_key,owner,store_id,writer_epoch,route_revision,native_index_sha256,evidence_sha256,status,schema_version,recorded_at) VALUES(?,?,?,?,?,?,?,'blocked',1,UTC_TIMESTAMP(6))`, key[:], []byte(owner), []byte(s.Binding.StoreID), []byte(s.Binding.WriterEpoch), []byte("m3-1"), index[:], proof[:]); err != nil {
				t.Fatal("controlled governance fixture failed")
			}
			reader, err := NewMySQL(db, s.Binding)
			if err != nil {
				t.Fatal(err)
			}
			if result, e := reader.Snapshot(t.Context(), l, index); !errors.Is(e, ErrSnapshot) || !reflect.DeepEqual(result, Snapshot{}) {
				t.Fatal("Prepared yielded authority or partial snapshot")
			}
			tx, err := db.BeginTx(t.Context(), nil)
			if err != nil {
				t.Fatal(err)
			}
			guard, err := base.Bind(t.Context(), tx, reservation.Execution)
			if err != nil {
				_ = tx.Rollback()
				t.Fatal(err)
			}
			if _, err = tx.ExecContext(t.Context(), `INSERT INTO native_test_fact VALUES('once')`); err != nil {
				_ = tx.Rollback()
				t.Fatal(err)
			}
			if err = guard.CommitWitness(t.Context()); err != nil {
				_ = tx.Rollback()
				t.Fatal(err)
			}
			if err = tx.Commit(); err != nil {
				t.Fatal(err)
			}
			before, err := reader.Snapshot(t.Context(), l, index)
			if err != nil || before.Decision != transaction.Commit || before.Reference != reference || before.BeforeFinal != transaction.FinalNotAttempted || before.BeforeFinalAt != nil {
				t.Fatal("original terminal snapshot failed", err)
			}
			// Explicit synthetic OLD audit fixture. No real RPC is claimed by this
			// reader test, and no recovery recorder is called to fill a missing audit.
			ek, bk := transaction.ExecutionKey(owner, l.OperationID, s.Binding.WriterEpoch, l.Fence), transaction.BranchKey(l.BranchID)
			if _, err = db.ExecContext(t.Context(), `UPDATE rm_tx_witness SET final_outcome='commit_confirmed',final_recorded_at='2000-01-01 00:00:00.000000',final_error_code='' WHERE execution_key=? AND branch_key=?`, ek[:], bk[:]); err != nil {
				t.Fatal(err)
			}
			old, err := reader.Snapshot(t.Context(), l, index)
			if err != nil || old.BeforeFinal != transaction.FinalCommitConfirmed || old.BeforeFinalAt == nil || old.BeforeFinalAt.Year() != 2000 || old.DatabaseIdentitySHA256 != before.DatabaseIdentitySHA256 {
				t.Fatal("old first audit snapshot lost", err)
			}
			for _, change := range []string{"wrong-notice", "wrong-fence", "wrong-current-epoch", "missing-final-time"} {
				t.Run(change, func(t *testing.T) {
					locator, notice := l, index
					switch change {
					case "wrong-notice":
						notice[0] ^= 1
					case "wrong-fence":
						locator.Fence++
					case "wrong-current-epoch":
						if _, e := db.ExecContext(t.Context(), `UPDATE rm_tx_binding SET writer_epoch='different' WHERE owner=?`, []byte(owner)); e != nil {
							t.Fatal(e)
						}
						defer func() {
							if _, e := db.ExecContext(t.Context(), `UPDATE rm_tx_binding SET writer_epoch=? WHERE owner=?`, []byte(s.Binding.WriterEpoch), []byte(owner)); e != nil {
								t.Error(e)
							}
						}()
					case "missing-final-time":
						if _, e := db.ExecContext(t.Context(), `UPDATE rm_tx_witness SET final_recorded_at=NULL WHERE execution_key=? AND branch_key=?`, ek[:], bk[:]); e != nil {
							t.Fatal(e)
						}
						defer func() {
							if _, e := db.ExecContext(t.Context(), `UPDATE rm_tx_witness SET final_recorded_at='2000-01-01 00:00:00.000000' WHERE execution_key=? AND branch_key=?`, ek[:], bk[:]); e != nil {
								t.Error(e)
							}
						}()
					}
					result, e := reader.Snapshot(t.Context(), locator, notice)
					if e == nil || !reflect.DeepEqual(result, Snapshot{}) {
						t.Fatal("invalid source yielded authority or partial result")
					}
				})
			}

			// A separate original SDK execution is actually fenced Aborted.
			abortedLocator := Locator{"aborted-op", l.BranchID, 1}
			abortedPlan := nativePlanForOwner(t, owner, abortedLocator)
			aborted, abortErr := base.Reserve(t.Context(), transaction.RequestFor(abortedPlan), abortedPlan, transaction.ReserveOptions{Lease: time.Hour})
			if abortErr != nil || !aborted.Acquired {
				t.Fatal("reserve abort fixture failed", abortErr)
			}
			if ok, e := base.Abort(t.Context(), aborted.Execution); e != nil || !ok {
				t.Fatal("actual fenced abort failed", e)
			}
			secondIndex := [32]byte{3}
			secondKey := NoticeKey(s.Binding, secondIndex)
			if _, e := db.ExecContext(t.Context(), `INSERT INTO messaging_native_limit_notices(notice_key,owner,store_id,writer_epoch,route_revision,native_index_sha256,evidence_sha256,status,schema_version,recorded_at) VALUES(?,?,?,?,?,?,?,'blocked',1,UTC_TIMESTAMP(6))`, secondKey[:], []byte(owner), []byte(s.Binding.StoreID), []byte(s.Binding.WriterEpoch), []byte("m3-1"), secondIndex[:], proof[:]); e != nil {
				t.Fatal(e)
			}
			rolledBack, e := reader.Snapshot(t.Context(), abortedLocator, secondIndex)
			if e != nil || rolledBack.Decision != transaction.Rollback || rolledBack.Reference != aborted.Execution.References()[0] {
				t.Fatal("original fenced abort not recognized", e)
			}
			for _, table := range []string{"rm_tx_request", "rm_tx_execution", "rm_tx_witness", "native_test_fact", "messaging_native_limit_notices"} {
				var count int
				if err = db.QueryRowContext(t.Context(), `SELECT COUNT(*) FROM `+table).Scan(&count); err != nil || (table == "native_test_fact" && count != 1) || (table != "native_test_fact" && count != 2) {
					t.Fatal("original fixture facts changed", err)
				}
			}
			final, err := reader.Snapshot(t.Context(), l, index)
			if err != nil || !reflect.DeepEqual(final, old) {
				t.Fatal("readonly snapshot changed facts", err)
			}

			t.Run("controlled-governance-storage-not-rpc-proof", func(t *testing.T) { mysqlResolutionStorageFixture(t, db, reader, before) })
			t.Run("compiled-preview-cli-readonly-not-rpc-proof", func(t *testing.T) {
				var name string
				if e := db.QueryRowContext(t.Context(), `SELECT DATABASE()`).Scan(&name); e != nil {
					t.Fatal(e)
				}
				c, e := driver.ParseDSN(os.Getenv("NATIVE_TOOL_TEST_MYSQL_DSN"))
				if e != nil {
					t.Fatal("fixture DSN")
				}
				c.DBName = name
				c.MultiStatements = false
				current, e := reader.Snapshot(t.Context(), l, index)
				if e != nil {
					t.Fatal(e)
				}
				previewCLINative(t, current, "mysql", c.FormatDSN(), name, func(index, proof [32]byte) {
					key := NoticeKey(s.Binding, index)
					if _, e := db.ExecContext(t.Context(), `INSERT INTO messaging_native_limit_notices(notice_key,owner,store_id,writer_epoch,route_revision,native_index_sha256,evidence_sha256,status,schema_version,recorded_at) VALUES(?,?,?,?,?,?,?,'blocked',1,UTC_TIMESTAMP(6))`, key[:], []byte(owner), []byte(s.Binding.StoreID), []byte(s.Binding.WriterEpoch), []byte("m3-1"), index[:], proof[:]); e != nil {
						t.Fatal(e)
					}
				})
				after, e := reader.Snapshot(t.Context(), l, index)
				if e != nil || !reflect.DeepEqual(current, after) {
					t.Fatal("preview changed original witness/notice", e)
				}
			})
		})
	}
}

func nativePlanForOwner(t *testing.T, owner string, l Locator) transaction.FrozenPlan {
	t.Helper()
	m, err := message.New(message.Input{Producer: "unit", ID: "original", Destination: "unit.logical", EventType: "fact", SchemaVersion: "v1", Scope: "org:7", ContentType: "application/octet-stream", OccurredAt: "2026-10-24T00:00:00Z", Payload: []byte{0, 255, 1}})
	if err != nil {
		t.Fatal(err)
	}
	physical, err := transport.PhysicalTopicV2("unit.logical", transport.TransactionMessageType, owner, "m3-1")
	if err != nil {
		t.Fatal(err)
	}
	p, err := transaction.NewPlan(transaction.PlanInput{Owner: owner, Scope: "org:7", OperationID: l.OperationID, IdempotencyKey: l.OperationID, InputHash: sha256.Sum256([]byte("input")), Branches: []transaction.BranchInput{{ID: l.BranchID, PhysicalTopic: physical, RouteRevision: "m3-1", Message: m, Wire: []byte{0, 255, 2}}}})
	if err != nil {
		t.Fatal(err)
	}
	return p
}
