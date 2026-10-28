//go:build integration && m3_evaluation_broker

package eventtransaction

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	shared "github.com/FangcunMount/qs-server/internal/apiserver/eventing/transactionplan"
	hostmysql "github.com/FangcunMount/qs-server/internal/pkg/database/mysql"
	"github.com/FangcunMount/qs-server/internal/pkg/messagingruntime"
	"github.com/FangcunMount/qs-server/internal/pkg/options"
	"github.com/FangcunMount/reliable-messaging/transaction"
	"github.com/FangcunMount/reliable-messaging/transport"
	"github.com/FangcunMount/reliable-messaging/transport/rocketmq"
	driver "github.com/go-sql-driver/mysql"
	"github.com/stretchr/testify/require"
	gormmysql "gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

// This owned test is copied into the reviewed host test package and removed
// afterwards. It uses the real host Committer, SDK store and Broker. No provider
// or system/business acceptance is claimed.
func TestReadableCrossRouteReplanBrokerHost(t *testing.T) {
	require.True(t, strings.HasPrefix(os.Getenv("QS_M3_FIXTURE_PROJECT"), "rocketmq-m2-"))
	cfg, err := driver.ParseDSN(os.Getenv("QS_M3_EVALUATION_DSN"))
	require.NoError(t, err)
	require.Empty(t, cfg.DBName)
	host, _, err := net.SplitHostPort(cfg.Addr)
	require.NoError(t, err)
	require.True(t, net.ParseIP(host).IsLoopback())
	cfg.ParseTime, cfg.MultiStatements = true, true
	admin, err := sql.Open("mysql", cfg.FormatDSN())
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, admin.Close()) })
	database := fmt.Sprintf("qs_readable_replan_%d", time.Now().UnixNano())
	_, err = admin.ExecContext(t.Context(), "CREATE DATABASE `"+database+"`")
	require.NoError(t, err)
	t.Cleanup(func() {
		_, err := admin.ExecContext(context.Background(), "DROP DATABASE `"+database+"`")
		require.NoError(t, err)
	})
	cfg.DBName = database
	db, err := gorm.Open(gormmysql.Open(cfg.FormatDSN()), &gorm.Config{Logger: logger.Default.LogMode(logger.Silent)})
	require.NoError(t, err)
	pool, err := db.DB()
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, pool.Close()) })
	for _, name := range []string{"000106_transaction_messaging.up.sql", "000110_native_transaction_limit_notices.up.sql"} {
		raw, err := os.ReadFile(filepath.Join("..", "..", "..", "..", "pkg", "migration", "migrations", "mysql", name))
		require.NoError(t, err)
		_, err = pool.ExecContext(t.Context(), string(raw))
		require.NoError(t, err)
	}
	_, err = pool.ExecContext(t.Context(), "CREATE TABLE replan_fact(id VARBINARY(128) PRIMARY KEY) ENGINE=InnoDB")
	require.NoError(t, err)
	load := func(key string) options.MessagingOptions {
		raw, err := os.ReadFile(os.Getenv(key))
		require.NoError(t, err)
		var value options.MessagingOptions
		require.NoError(t, json.Unmarshal(raw, &value))
		require.NotNil(t, value.RocketMQ)
		return value
	}
	t.Log("READABLE_REPLAN_STAGE configuration")
	producer, observer := load("QS_M3_PRODUCER_CONFIG"), load("QS_M3_OBSERVER_CONFIG")
	identity := producer.RocketMQ.Transactions[owner]
	_, err = pool.ExecContext(t.Context(), "INSERT INTO rm_tx_binding VALUES(?,?,?,1)", []byte(owner), []byte(identity.StoreID), []byte(identity.WriterEpoch))
	require.NoError(t, err)
	const topic = "qs.evaluation.lifecycle"
	t.Log("READABLE_REPLAN_STAGE construct_owner")
	c, err := New(db, &producer, fixtureResolver{}, []string{topic})
	require.NoError(t, err)
	t.Log("READABLE_REPLAN_STAGE start_owner")
	require.NoError(t, c.Runtime().Start(t.Context()))
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
		defer cancel()
		require.NoError(t, c.Runtime().Close(ctx))
	})
	request := fixtureRequest("explicit-owned-readable-handoff")
	old, err := freeze(request, fixtureResolver{})
	require.NoError(t, err)
	input := old.Input()
	input.OperationID += "-readable"
	input.Branches[0].PhysicalTopic, err = transport.PhysicalTopicV3(topic, transport.TransactionMessageType, owner, revision)
	require.NoError(t, err)
	candidate, err := transaction.NewPlan(input)
	require.NoError(t, err)
	t.Log("READABLE_REPLAN_STAGE reserve_old")
	previous, err := c.store.Reserve(t.Context(), transaction.RequestFor(old), old, transaction.ReserveOptions{Lease: time.Minute})
	require.NoError(t, err)
	require.True(t, previous.Acquired)
	authorization := transaction.ReplanAuthorization{Previous: previous.Execution, Candidate: candidate}
	t.Log("READABLE_REPLAN_STAGE refuse_unknown")
	_, err = c.store.Replan(t.Context(), authorization, transaction.ReserveOptions{Lease: time.Minute})
	require.ErrorIs(t, err, transaction.ErrStaleExecution)
	cases := map[string]bool{"old_unknown_replan_refused_without_business": true}
	t.Log("READABLE_REPLAN_STAGE refuse_historical_retry")
	_, err = c.RetryAborted(t.Context(), previous.Execution, transaction.ReserveOptions{Lease: time.Minute})
	require.ErrorIs(t, err, shared.ErrHistoricalExecution)
	cases["historical_ordinary_retry_refused"] = true
	t.Log("READABLE_REPLAN_STAGE abort_old")
	_, err = c.store.Abort(t.Context(), previous.Execution)
	require.NoError(t, err)
	t.Log("READABLE_REPLAN_STAGE replan")
	require.Equal(t, transaction.LocalAborted, c.Confirm(t.Context(), previous.Execution))
	next, err := c.store.Replan(t.Context(), authorization, transaction.ReserveOptions{Lease: time.Minute})
	require.NoError(t, err)
	require.True(t, next.Acquired)
	require.Equal(t, previous.Execution.Fence+1, next.Execution.Fence)
	require.NotEqual(t, old.Digest(), candidate.Digest())
	require.Equal(t, old.Input().Branches[0].Wire, candidate.Input().Branches[0].Wire)
	require.Equal(t, old.Input().Branches[0].Message, candidate.Input().Branches[0].Message)
	t.Log("READABLE_REPLAN_STAGE verify_artifacts")
	for _, p := range []transaction.FrozenPlan{old, candidate} {
		body, err := c.Artifact(p)
		require.NoError(t, err)
		require.Equal(t, request.Artifact, body)
	}
	// Confirm intentionally follows only the active execution after Replan.
	require.Equal(t, transaction.LocalUnknown, c.Confirm(t.Context(), previous.Execution))
	for _, ref := range previous.Execution.References() {
		require.Equal(t, transaction.Rollback, (transaction.StoreChecker{Store: c.store}).Check(t.Context(), ref), "exact old witness remains Aborted")
	}
	cases["explicit_aborted_replan_retains_wire_and_prior_evidence"] = true
	t.Log("READABLE_REPLAN_STAGE start_consumer")
	config, err := observer.RocketMQ.Load([]string{topic}, 2, 5*time.Second)
	require.NoError(t, err)
	consumer, err := rocketmq.NewSubscriber(rocketmq.SubscriberConfig{Config: config, MaxAttempts: 3, InvisibleDuration: 15 * time.Second, HandlerTimeout: 5 * time.Second, RetryDelay: time.Second})
	require.NoError(t, err)
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		require.NoError(t, consumer.Close(ctx))
	})
	received := make(chan transport.Received, 8)
	want := candidate.Input().Branches[0].Message.Input().ID
	require.NoError(t, consumer.Subscribe(t.Context(), topic, "qs-m3-evaluation-observer", func(_ context.Context, delivery transport.Delivery) error {
		m := delivery.Message()
		if err := delivery.Ack(); err != nil {
			return err
		}
		if m.ID == want {
			select {
			case received <- m:
			default:
			}
		}
		return nil
	}, func(context.Context, transport.Failure) error { return fmt.Errorf("owned replan delivery failed") }))
	var calls atomic.Int32
	t.Log("READABLE_REPLAN_STAGE commit")
	result, err := c.Commit(t.Context(), next.Execution, func(ctx context.Context) error {
		calls.Add(1)
		tx, err := hostmysql.RequireTx(ctx)
		if err != nil {
			return err
		}
		// Bind one string value; GORM expands a byte slice inside VALUES(?).
		return tx.Exec("INSERT INTO replan_fact(id) VALUES (?)", want).Error
	})
	// Never serialize Result, Execution or an error: they contain capabilities,
	// wire identities or service addresses. The harness applies a second allowlist.
	state := map[string]any{"local": result.Local, "business_calls": calls.Load(),
		"lease_expired":    !time.Now().Before(next.Execution.LeaseUntil),
		"ready":            c.Runtime().Stats().Ready,
		"admission_closed": errors.Is(err, messagingruntime.ErrTransactionAdmissionClosed),
		"stale_execution":  errors.Is(err, transaction.ErrStaleExecution),
		"binding_error":    errors.Is(err, transaction.ErrBinding),
		"invalid_plan":     errors.Is(err, transaction.ErrInvalidPlan),
		"root_required":    errors.Is(err, transaction.ErrTransactionRequired),
		"schema_error":     errors.Is(err, transaction.ErrSchema),
		"deadline":         errors.Is(err, context.DeadlineExceeded),
		"canceled":         errors.Is(err, context.Canceled)}
	protection := c.Runtime().ProtectionStats()
	state["protection"] = map[string]any{"available": protection.Available, "fresh": protection.Fresh,
		"protected": protection.Protected, "reason": protection.Reason}
	var dbError *driver.MySQLError
	if errors.As(err, &dbError) {
		state["mysql_number"] = int(dbError.Number)
	}
	branches := make([]map[string]any, 0, len(result.Branches))
	for _, branch := range result.Branches {
		code := "unclassified"
		for _, fixed := range []string{"", "half_unknown", "half_rejected_grpc_permission_denied", "half_rejected_grpc_unauthenticated", "invalid_half_receipt", "half_audit_failed", "final_audit_failed"} {
			if branch.ErrorCode == fixed {
				code = fixed
			}
		}
		branches = append(branches, map[string]any{"half": branch.Half, "final": branch.Final, "code": code})
	}
	state["branches"] = branches
	diagnostic, diagnosticErr := json.Marshal(state)
	require.NoError(t, diagnosticErr)
	fmt.Println("READABLE_REPLAN_COMMIT_STATE " + string(diagnostic))
	require.NoError(t, err)
	require.Equal(t, transaction.LocalCommitted, result.Local)
	t.Log("READABLE_REPLAN_STAGE consume")
	select {
	case m := <-received:
		require.Equal(t, want, m.ID)
		require.Equal(t, candidate.Input().Branches[0].Wire, m.Wire)
	case <-time.After(30 * time.Second):
		t.Fatal("actual readable replan wire not received")
	}
	require.Equal(t, int32(1), calls.Load())
	var count int
	require.NoError(t, pool.QueryRowContext(t.Context(), "SELECT COUNT(*) FROM replan_fact").Scan(&count))
	require.Equal(t, 1, count)
	require.Equal(t, transaction.LocalCommitted, c.Confirm(t.Context(), next.Execution))
	// Confirm intentionally follows only the active execution after Replan.
	require.Equal(t, transaction.LocalUnknown, c.Confirm(t.Context(), previous.Execution))
	for _, ref := range previous.Execution.References() {
		require.Equal(t, transaction.Rollback, (transaction.StoreChecker{Store: c.store}).Check(t.Context(), ref), "exact old witness remains Aborted")
	}
	cases["actual_readable_publish_original_root_and_one_effect"] = true
	t.Log("READABLE_REPLAN_STAGE refuse_committed")
	input.OperationID += "-forbidden"
	forbidden, err := transaction.NewPlan(input)
	require.NoError(t, err)
	_, err = c.store.Replan(t.Context(), transaction.ReplanAuthorization{Previous: next.Execution, Candidate: forbidden}, transaction.ReserveOptions{Lease: time.Minute})
	require.ErrorIs(t, err, transaction.ErrStaleExecution)
	_, err = c.store.Replan(t.Context(), authorization, transaction.ReserveOptions{Lease: time.Minute})
	require.ErrorIs(t, err, transaction.ErrStaleExecution)
	require.Equal(t, int32(1), calls.Load())
	require.NoError(t, pool.QueryRowContext(t.Context(), "SELECT COUNT(*) FROM rm_tx_execution").Scan(&count))
	require.Equal(t, 2, count)
	cases["committed_replan_refused_no_duplicate_execution"] = true
	raw, err := json.Marshal(map[string]any{"passed": len(cases), "failed": 0, "skipped": 0, "cases": cases,
		"source_sha": os.Getenv("QS_M3_REPLAN_SOURCE_SHA"), "scope": "actual_mysql_host_root_and_readable_broker_no_provider_or_system"})
	require.NoError(t, err)
	fmt.Println("READABLE_REPLAN_RECEIPT " + string(raw))
}
