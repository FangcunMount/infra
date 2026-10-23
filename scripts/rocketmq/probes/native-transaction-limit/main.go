// Isolated CI fault generator through the fixed published SDK. Not a domain host proof.
package main

import (
	"bufio"
	"context"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/FangcunMount/reliable-messaging/message"
	txmysql "github.com/FangcunMount/reliable-messaging/storage/transaction/mysql"
	"github.com/FangcunMount/reliable-messaging/transaction"
	"github.com/FangcunMount/reliable-messaging/transport/rocketmq"
	driver "github.com/go-sql-driver/mysql"
)

type config struct{ Project, Endpoint, CAFile, AccessKey, SecretKey, Topic, LogicalTopic, Owner, Key, DSN, Database string }

var phase = "configuration" // Main goroutine only; never a payload or database error.

func readConfig(path string) (config, error) {
	var c config
	if !filepath.IsAbs(path) {
		return c, errors.New("absolute private configuration required")
	}
	f, e := os.Open(path)
	if e != nil {
		return c, e
	}
	defer f.Close()
	s, e := f.Stat()
	if e != nil || !s.Mode().IsRegular() || s.Mode().Perm()&0077 != 0 || s.Size() > 65536 {
		return c, errors.New("private bounded configuration required")
	}
	d := json.NewDecoder(io.LimitReader(f, 65537))
	d.DisallowUnknownFields()
	if d.Decode(&c) != nil {
		return c, errors.New("invalid private configuration")
	}
	var trailing any
	if d.Decode(&trailing) != io.EOF {
		return c, errors.New("one configuration required")
	}
	host, _, e := net.SplitHostPort(c.Endpoint)
	if e != nil || !net.ParseIP(host).IsLoopback() || !strings.HasPrefix(c.Project, "rocketmq-m2-") || !filepath.IsAbs(c.CAFile) || len(c.Topic) == 0 || len(c.Topic) > 255 || len(c.LogicalTopic) == 0 || len(c.Key) == 0 || len(c.Key) > 128 || len(c.AccessKey) == 0 || len(c.SecretKey) == 0 || !regexp.MustCompile(`^native_limit_fault_[a-f0-9]{24}$`).MatchString(c.Database) {
		return c, errors.New("owned isolated loopback fixture required")
	}
	switch c.Owner {
	case "iam.mysql", "qs.mysql", "qs.mongo", "ai.mysql":
	default:
		return c, errors.New("frozen fixture owner required")
	}
	sqlConfig, e := driver.ParseDSN(c.DSN)
	if e != nil {
		return c, errors.New("invalid fixture primary")
	}
	sqlHost, _, e := net.SplitHostPort(sqlConfig.Addr)
	if e != nil || sqlConfig.Net != "tcp" || !net.ParseIP(sqlHost).IsLoopback() || sqlConfig.DBName != "" {
		return c, errors.New("owned loopback SQL server required")
	}
	return c, nil
}
func run(c config) (result error) {
	ctx, cancel := context.WithTimeout(context.Background(), 170*time.Second)
	defer cancel()
	ca, e := os.ReadFile(c.CAFile)
	if e != nil {
		return e
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(ca) {
		return errors.New("invalid fixture CA")
	}
	host, _, _ := net.SplitHostPort(c.Endpoint)
	tc := &tls.Config{MinVersion: tls.VersionTLS12, RootCAs: roots, ServerName: host}
	cfg, e := driver.ParseDSN(c.DSN)
	if e != nil {
		return e
	}
	phase = "install_owned_schema"
	admin, e := sql.Open("mysql", cfg.FormatDSN())
	if e != nil {
		return e
	}
	defer admin.Close()
	if _, e = admin.ExecContext(ctx, "CREATE DATABASE `"+c.Database+"`"); e != nil {
		return e
	}
	dropped := false
	defer func() {
		if !dropped {
			cleanup, stop := context.WithTimeout(context.Background(), 10*time.Second)
			defer stop()
			_, err := admin.ExecContext(cleanup, "DROP DATABASE `"+c.Database+"`")
			result = errors.Join(result, err)
		}
	}()
	cfg.DBName = c.Database
	cfg.ParseTime = true
	db, e := sql.Open("mysql", cfg.FormatDSN())
	if e != nil {
		return e
	}
	defer db.Close()
	db.SetMaxOpenConns(4)
	db.SetMaxIdleConns(2)
	// Explicit installer for this owned temporary fault schema, never a constructor.
	for statement := range strings.SplitSeq(txmysql.Schema, ";") {
		if strings.TrimSpace(statement) != "" {
			if _, e = db.ExecContext(ctx, statement); e != nil {
				return e
			}
		}
	}
	binding := transaction.Binding{Owner: c.Owner, StoreID: "owned-native-limit-fault", WriterEpoch: "m3-1"}
	if _, e = db.ExecContext(ctx, "INSERT INTO rm_tx_binding VALUES(?,?,?,1)", []byte(binding.Owner), []byte(binding.StoreID), []byte(binding.WriterEpoch)); e != nil {
		return e
	}
	phase = "construct_fixed_sdk"
	store, e := txmysql.New(db, binding)
	if e != nil {
		return e
	}
	limits := transaction.DefaultLimits()
	limits.Lease = time.Hour
	limits.Sends = 1
	limits.CheckWorkers = 1
	limits.CheckQueue = 4
	limits.RPCTimeout = 5 * time.Second
	limits.CheckTimeout = 2 * time.Second
	sender, e := rocketmq.NewTransactionalSender(rocketmq.TransactionConfig{Endpoint: c.Endpoint, AccessKey: c.AccessKey, SecretKey: c.SecretKey, TLS: tc, Owner: c.Owner, Routes: []rocketmq.TransactionRoute{{LogicalTopic: c.LogicalTopic, PhysicalTopic: c.Topic, Revision: "m3-1"}}, Limits: limits}, store)
	if e != nil {
		return e
	}
	closed := false
	defer func() {
		if !closed {
			cleanup, stop := context.WithTimeout(context.Background(), 15*time.Second)
			defer stop()
			result = errors.Join(result, sender.Close(cleanup))
		}
	}()
	phase = "start_fixed_sdk"
	if e = sender.Start(ctx); e != nil {
		return e
	}
	payload := []byte("private-native-limit-fault")
	msg, e := message.New(message.Input{Producer: "infra.native-limit", ID: c.Key, Destination: c.LogicalTopic, EventType: "isolated.native.limit", SchemaVersion: "1", Scope: "owned-fault", ContentType: "application/octet-stream", OccurredAt: time.Now().UTC().Format(time.RFC3339Nano), Payload: payload})
	if e != nil {
		return e
	}
	plan, e := transaction.NewPlan(transaction.PlanInput{Owner: c.Owner, Scope: "owned-fault", OperationID: c.Key, IdempotencyKey: c.Key, InputHash: sha256.Sum256(payload), Branches: []transaction.BranchInput{{ID: "fault", PhysicalTopic: c.Topic, RouteRevision: "m3-1", Message: msg, Wire: payload}}})
	if e != nil {
		return e
	}
	phase = "reserve_fault"
	reserved, e := sender.Reserve(ctx, transaction.RequestFor(plan), plan)
	if e != nil || !reserved.Acquired {
		return errors.New("fault reservation unavailable")
	}
	callbacks := 0
	phase = "execute_fault_unknown"
	observed, _ := sender.Execute(ctx, reserved.Execution, func(context.Context, transaction.Execution) (transaction.LocalOutcome, error) {
		callbacks++
		return transaction.LocalUnknown, errors.New("isolated fault deliberately has no business transaction")
	})
	if callbacks != 1 || observed.Local != transaction.LocalUnknown || len(observed.Branches) != 1 || observed.Branches[0].Half != transaction.HalfPrepared || observed.Branches[0].Final != transaction.FinalNotAttempted {
		return errors.New("exact Unknown prepared fault absent")
	}
	phase = "wait_private_index"
	fmt.Println(`M3_NATIVE_LIMIT_FAULT {"event":"ready","prepared":1}`)
	scanner := bufio.NewScanner(os.Stdin)
	scanner.Buffer(make([]byte, 128), 128)
	if !scanner.Scan() || scanner.Text() != "stop" {
		return errors.New("explicit fault fixture stop required")
	}
	phase = "close_fixed_sdk"
	if e = sender.Close(ctx); e != nil {
		return e
	}
	closed = true
	stats := sender.Stats()
	if !stats.Stopped || stats.RunningChecks != 0 || stats.QueuedChecks != 0 || stats.HalfPreparedResults != 1 || stats.CheckUnknown < 1 || stats.FinalCommitResults > 0 || stats.FinalRollbackResults > 0 || stats.CheckCommit > 0 || stats.CheckRollback > 0 {
		return errors.New("fault SDK lifecycle incomplete")
	}
	if e = db.Close(); e != nil {
		return e
	}
	phase = "drop_owned_fault_schema"
	if _, e = admin.ExecContext(ctx, "DROP DATABASE `"+c.Database+"`"); e != nil {
		return e
	}
	dropped = true
	fmt.Printf("M3_NATIVE_LIMIT_FAULT {\"event\":\"closed\",\"prepared\":1,\"unknown_checks\":%d,\"business_calls\":0,\"local_fault_callbacks\":1,\"owned_database_dropped\":true,\"final_confirmation_calls\":0}\n", stats.CheckUnknown)
	return nil
}
func main() {
	if len(os.Args) != 2 {
		os.Exit(2)
	}
	c, e := readConfig(os.Args[1])
	if e != nil {
		fmt.Fprintln(os.Stderr, "invalid isolated fault configuration")
		os.Exit(2)
	}
	if run(c) != nil {
		fmt.Printf("M3_NATIVE_LIMIT_FAULT {\"event\":\"failed\",\"stage\":\"%s\"}\n", phase)
		fmt.Fprintln(os.Stderr, "isolated native-limit fault failed")
		os.Exit(1)
	}
}
