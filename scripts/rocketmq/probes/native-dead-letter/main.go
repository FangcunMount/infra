// This executable belongs only to an explicitly selected isolated CI fixture.
package main

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/FangcunMount/reliable-messaging/message"
	"github.com/FangcunMount/reliable-messaging/transport"
	"github.com/FangcunMount/reliable-messaging/transport/rocketmq"
	"github.com/FangcunMount/reliable-messaging/wire/legacy"
)

type config struct {
	Project, Endpoint, CAFile, AccessKey, SecretKey, Key string
	Route                                                transport.RouteBinding
}

func readConfig(path string) (config, error) {
	var c config
	if !filepath.IsAbs(path) {
		return c, errors.New("absolute private configuration required")
	}
	f, err := os.Open(path)
	if err != nil {
		return c, errors.New("private configuration unavailable")
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0077 != 0 || info.Size() > 65536 {
		return c, errors.New("bounded private configuration required")
	}
	decoder := json.NewDecoder(io.LimitReader(f, 65537))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&c) != nil {
		return c, errors.New("private configuration invalid")
	}
	var trailing any
	if decoder.Decode(&trailing) != io.EOF {
		return c, errors.New("one configuration required")
	}
	host, port, err := net.SplitHostPort(c.Endpoint)
	number, portErr := strconv.Atoi(port)
	if err != nil || portErr != nil || number < 1 || number > 65535 || !(host == "localhost" || net.ParseIP(host).IsLoopback()) ||
		!strings.HasPrefix(c.Project, "rocketmq-m2-") || !filepath.IsAbs(c.CAFile) ||
		c.AccessKey == "" || len(c.AccessKey) > 256 || c.SecretKey == "" || len(c.SecretKey) > 512 ||
		c.Key == "" || len(c.Key) > 128 || c.Route.Subscription == "" ||
		c.Route.MessageType != transport.NormalMessageType || c.Route.RouteRevision != "m3-1" {
		return c, errors.New("explicit isolated normal route required")
	}
	if transport.ValidateRoutes([]transport.RouteBinding{c.Route}) != nil {
		return c, errors.New("canonical isolated route required")
	}
	return c, nil
}

func emit(values map[string]any) {
	fmt.Print("M3_NATIVE_DLQ_PROBE ")
	_ = json.NewEncoder(os.Stdout).Encode(values)
}

func run(c config) (result error) {
	ca, err := os.ReadFile(c.CAFile)
	if err != nil {
		return errors.New("fixture CA unavailable")
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(ca) {
		return errors.New("fixture CA invalid")
	}
	options := rocketmq.Config{Endpoint: c.Endpoint, AccessKey: c.AccessKey, SecretKey: c.SecretKey,
		TLS: &tls.Config{MinVersion: tls.VersionTLS12, RootCAs: roots}, Routes: []transport.RouteBinding{c.Route},
		RequestTimeout: 5 * time.Second, MaxInFlight: 1}
	encoded, err := legacy.Encode(legacy.Envelope{UUID: c.Key, Payload: []byte("private-native-dlq-payload")}, legacy.Revision2)
	if err != nil {
		return errors.New("fixture envelope invalid")
	}
	intent, err := message.New(message.Input{Producer: "infra.native-dlq", ID: c.Key,
		Destination: c.Route.Topic, EventType: "audit.poison", SchemaVersion: "1", Scope: "isolated:" + c.Project,
		ContentType: "application/json", OccurredAt: time.Now().UTC().Format(time.RFC3339Nano), Payload: encoded})
	if err != nil {
		return errors.New("fixture intent invalid")
	}
	subscriber, err := rocketmq.NewSubscriber(rocketmq.SubscriberConfig{Config: options, MaxAttempts: 1,
		InvisibleDuration: 10 * time.Second, HandlerTimeout: 5 * time.Second, RetryDelay: time.Second})
	if err != nil {
		return errors.New("fixture subscriber invalid")
	}
	publisher, err := rocketmq.NewPublisher(options)
	if err != nil {
		return errors.New("fixture publisher invalid")
	}
	var closeOnce sync.Once
	var closeErr error
	closeOwned := func() error {
		closeOnce.Do(func() {
			ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
			defer cancel()
			closeErr = errors.Join(subscriber.Close(ctx), publisher.Close(ctx))
		})
		return closeErr
	}
	defer func() { result = errors.Join(result, closeOwned()) }()
	var handlers, failures, mismatches atomic.Int64
	matches := func(received transport.Received) bool {
		return received.ID == c.Key && bytes.Equal(received.Wire, encoded)
	}
	handler := func(_ context.Context, d transport.Delivery) error {
		handlers.Add(1)
		if !matches(d.Message()) {
			mismatches.Add(1)
		}
		return errors.New("isolated poison")
	}
	failed := func(_ context.Context, f transport.Failure) error {
		failures.Add(1)
		if !matches(f.Message) {
			mismatches.Add(1)
		}
		// Deliberately do not Ack an unavailable durable handoff. Broker's
		// explicitly limited ISOLATED group supplies native DLQ fallback.
		return errors.New("isolated durable failure unavailable")
	}
	if err = subscriber.Subscribe(context.Background(), c.Route.Topic, c.Route.Subscription, handler, failed); err != nil {
		return errors.New("fixture subscription unavailable")
	}
	if err = publisher.Start(); err != nil {
		return errors.New("fixture publisher unavailable")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	outcome := publisher.Publish(ctx, intent)
	cancel()
	if outcome.Outcome != transport.Confirmed {
		return errors.New("fixture publish unconfirmed")
	}
	digest := sha256.Sum256(encoded)
	emit(map[string]any{"event": "ready", "ready": true, "published": 1, "wire_sha256": hex.EncodeToString(digest[:]), "max_inflight": 1})
	stop := make(chan bool, 1)
	go func() {
		scanner := bufio.NewScanner(os.Stdin)
		stop <- scanner.Scan() && scanner.Text() == "stop"
	}()
	select {
	case ok := <-stop:
		if !ok {
			return errors.New("explicit fixture stop required")
		}
	case <-time.After(120 * time.Second):
		return errors.New("fixture audit budget exhausted")
	}
	if err = closeOwned(); err != nil {
		return errors.New("fixture drain incomplete")
	}
	if handlers.Load() < 1 || failures.Load() < 1 || mismatches.Load() != 0 {
		return errors.New("fixture delivery evidence incomplete")
	}
	emit(map[string]any{"event": "closed", "closed": true, "published": 1, "handler_calls": handlers.Load(),
		"failed_handoff_calls": failures.Load(), "wire_mismatches": mismatches.Load(), "application_ack_calls": 0})
	return nil
}

func main() {
	if len(os.Args) != 2 {
		emit(map[string]any{"event": "failed", "status": "invalid_fixture"})
		os.Exit(1)
	}
	c, err := readConfig(os.Args[1])
	if err == nil {
		err = run(c)
	}
	if err != nil {
		emit(map[string]any{"event": "failed", "status": "fixture_failed"})
		os.Exit(1)
	}
}
