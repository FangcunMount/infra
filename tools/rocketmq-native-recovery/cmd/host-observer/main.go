// host-observer is an isolated CI consumer, never a production recovery command.
package main

import (
	"bufio"
	"context"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"net"
	"os"
	"time"

	"fangcunmount.infra/rocketmq-native-recovery/internal/privatefile"
	"github.com/FangcunMount/reliable-messaging/transport"
	"github.com/FangcunMount/reliable-messaging/transport/rocketmq"
)

type config struct {
	Endpoint, AccessKey, SecretKey, CA, Subscription string
	Inputs                                           []transport.RouteBinding
}

func validate(c config, env func(string) string) error {
	host, _, e := net.SplitHostPort(c.Endpoint)
	if env("GITHUB_ACTIONS") != "true" || env("RUNNER_OS") != "Linux" || env("RUNNER_ENVIRONMENT") != "github-hosted" || env("GITHUB_REPOSITORY") != "FangcunMount/infra" || e != nil || !net.ParseIP(host).IsLoopback() || c.AccessKey == "" || c.SecretKey == "" || c.CA == "" || c.Subscription == "" || len(c.Inputs) != 1 {
		return errors.New("CI-owned original host observer required")
	}
	r := c.Inputs[0]
	if r.Topic != "iam.authz.version.v2" || r.Subscription != c.Subscription || r.Owner != "iam.mysql" || r.RouteRevision != "m3-1" || r.MessageType != transport.TransactionMessageType {
		return errors.New("explicit IAM original route required")
	}
	return nil
}
func emit(event, id, decision string) {
	raw, _ := json.Marshal(map[string]string{"event": event, "id": id, "decision": decision})
	fmt.Println("TXPROBE " + string(raw))
}
func run(path, expected string) error {
	// Before any file/client/network construction, deny ordinary workstations.
	if os.Getenv("GITHUB_ACTIONS") != "true" || os.Getenv("RUNNER_OS") != "Linux" || os.Getenv("RUNNER_ENVIRONMENT") != "github-hosted" || os.Getenv("GITHUB_REPOSITORY") != "FangcunMount/infra" {
		return errors.New("CI-only observer")
	}
	decoded, e := hex.DecodeString(expected)
	if e != nil || len(decoded) != 32 {
		return errors.New("exact private config digest required")
	}
	var digest [32]byte
	copy(digest[:], decoded)
	raw, e := privatefile.Read(path, digest)
	if e != nil {
		return e
	}
	var c config
	// The source probe config has extra fixture fields. Only this local CI config
	// selects the connection; a received message never selects an endpoint.
	if json.Unmarshal(raw, &c) != nil {
		return errors.New("observer config required")
	}
	if e = validate(c, os.Getenv); e != nil {
		return e
	}
	ca, e := os.ReadFile(c.CA)
	if e != nil {
		return errors.New("owned CA required")
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(ca) {
		return errors.New("owned CA required")
	}
	subscriber, e := rocketmq.NewSubscriber(rocketmq.SubscriberConfig{Config: rocketmq.Config{Endpoint: c.Endpoint, AccessKey: c.AccessKey, SecretKey: c.SecretKey, TLS: &tls.Config{MinVersion: tls.VersionTLS12, RootCAs: roots}, Routes: c.Inputs, RequestTimeout: 5 * time.Second, MaxInFlight: 1}, MaxAttempts: 8, InvisibleDuration: 15 * time.Second, HandlerTimeout: 10 * time.Second, RetryDelay: time.Second})
	if e != nil {
		return e
	}
	handler := func(_ context.Context, d transport.Delivery) error {
		message := d.Message()
		if message.ID == "" || message.Topic != c.Inputs[0].Topic || len(message.Wire) == 0 {
			return errors.New("original host wire required")
		}
		hash := sha256.Sum256(message.Wire)
		if err := d.Ack(); err != nil {
			return err
		}
		emit("received", message.ID, hex.EncodeToString(hash[:]))
		return nil
	}
	if e = subscriber.Subscribe(context.Background(), c.Inputs[0].Topic, c.Subscription, handler, func(context.Context, transport.Failure) error { return errors.New("unexpected host observer failure") }); e != nil {
		return e
	}
	emit("ready", "", "published_sdk_original_host_observer")
	scanner := bufio.NewScanner(os.Stdin)
	for scanner.Scan() {
		if scanner.Text() == "stop" {
			break
		}
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	if e = subscriber.Close(ctx); e != nil {
		return e
	}
	emit("closed", "", "drained")
	return nil
}
func main() {
	path := flag.String("config", "", "owned private fixture configuration")
	expected := flag.String("config-sha", "", "exact private fixture digest")
	flag.Parse()
	if run(*path, *expected) != nil {
		fmt.Fprintln(os.Stderr, "isolated host observer failed; private diagnostics withheld")
		os.Exit(1)
	}
}
