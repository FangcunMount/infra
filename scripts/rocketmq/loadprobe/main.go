// Command loadprobe measures the SDK against an explicitly provisioned,
// non-business acceptance route. It creates no resources or database effects.
package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/FangcunMount/reliable-messaging/transport"
	"github.com/FangcunMount/reliable-messaging/transport/rocketmq"
	"github.com/FangcunMount/reliable-messaging/wire/legacy"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "RocketMQ load acceptance failed:", err)
		os.Exit(1)
	}
}
func run() error {
	endpoint := flag.String("endpoint", "", "explicit private Proxy host:port")
	file := flag.String("credentials", "", "private account JSON file")
	caFile := flag.String("ca", "", "trusted CA file")
	duration := flag.Duration("duration", 10*time.Minute, "load interval")
	rate := flag.Int("rate", 300, "scheduled messages/second")
	flag.Parse()
	if *duration < time.Second || *duration > time.Hour || *rate < 1 || *rate > 1000 {
		return errors.New("bounded duration/rate required")
	}
	var account struct{ Username, Password string }
	raw, err := os.ReadFile(*file)
	if err != nil {
		return errors.New("credential file unavailable")
	}
	if json.Unmarshal(raw, &account) != nil {
		return errors.New("credential file invalid")
	}
	ca, err := os.ReadFile(*caFile)
	if err != nil {
		return errors.New("CA unavailable")
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(ca) {
		return errors.New("invalid CA")
	}
	topic, subscription := "infra.rocketmq.load.v1", "infra-load"
	c := rocketmq.Config{Endpoint: *endpoint, AccessKey: account.Username, SecretKey: account.Password, MaxInFlight: 48, RequestTimeout: 5 * time.Second, TLS: &tls.Config{MinVersion: tls.VersionTLS12, RootCAs: roots}, Routes: []transport.RouteBinding{{Topic: topic, Subscription: subscription, PhysicalTopic: transport.PhysicalTopic(topic), ConsumerGroup: transport.ConsumerGroup(topic, subscription)}}}
	var nonce [12]byte
	if _, err = rand.Read(nonce[:]); err != nil {
		return err
	}
	runID := "load-" + hex.EncodeToString(nonce[:]) + "-"
	body := bytes.Repeat([]byte("x"), 1024)
	var mu sync.Mutex
	seen := map[string]bool{}
	duplicates, invalid, acked := 0, 0, 0
	s, err := rocketmq.NewSubscriber(rocketmq.SubscriberConfig{Config: c, MaxAttempts: 8, InvisibleDuration: 60 * time.Second, HandlerTimeout: 30 * time.Second, RetryDelay: 10 * time.Second})
	if err != nil {
		return err
	}
	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
		defer cancel()
		_ = s.Close(ctx)
	}()
	if err = s.Subscribe(context.Background(), topic, subscription, func(_ context.Context, d transport.Delivery) error {
		m := d.Message()
		if !strings.HasPrefix(m.ID, runID) {
			return d.Ack()
		} // same owned test route, older acceptance run
		if !bytes.Equal(m.Payload, body) || m.PhysicalTopic != transport.PhysicalTopic(topic) {
			mu.Lock()
			invalid++
			mu.Unlock()
			return errors.New("load body or source mismatch")
		}
		if err := d.Ack(); err != nil {
			return err
		}
		mu.Lock()
		defer mu.Unlock()
		acked++
		if seen[m.ID] {
			duplicates++
		}
		seen[m.ID] = true
		return nil
	}, func(context.Context, transport.Failure) error {
		return errors.New("load probe has no durable business failure owner")
	}); err != nil {
		return errors.New("load subscription failed")
	}
	p, err := rocketmq.NewPublisher(c)
	if err != nil {
		return err
	}
	if err = p.Start(); err != nil {
		return errors.New("load publisher startup failed")
	}
	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
		defer cancel()
		_ = p.Close(ctx)
	}()
	jobs := make(chan int, 48)
	var workers sync.WaitGroup
	confirmed, unknown, rejected, dropped := 0, 0, 0, 0
	var latencies []time.Duration
	for i := 0; i < 48; i++ {
		workers.Add(1)
		go func() {
			defer workers.Done()
			for n := range jobs {
				id := fmt.Sprintf("%s%08d", runID, n)
				wire, e := legacy.Encode(legacy.Envelope{UUID: id, Payload: body}, legacy.Revision2)
				if e != nil {
					panic(e)
				}
				began := time.Now()
				ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
				result := p.PublishRaw(ctx, topic, wire)
				cancel()
				mu.Lock()
				latencies = append(latencies, time.Since(began))
				switch result.Outcome {
				case transport.Confirmed:
					confirmed++
				case transport.Rejected:
					rejected++
				default:
					unknown++
				}
				mu.Unlock()
			}
		}()
	}
	total := int(duration.Seconds() * float64(*rate))
	ticker := time.NewTicker(time.Second / time.Duration(*rate))
	began := time.Now()
	for n := 0; n < total; n++ {
		<-ticker.C
		select {
		case jobs <- n:
		default:
			dropped++
		}
	}
	ticker.Stop()
	close(jobs)
	workers.Wait()
	publishSeconds := time.Since(began).Seconds()
	deadline := time.Now().Add(60 * time.Second)
	for time.Now().Before(deadline) {
		mu.Lock()
		n := len(seen)
		mu.Unlock()
		if n == confirmed {
			break
		}
		time.Sleep(200 * time.Millisecond)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	err = p.Close(ctx)
	cancel()
	if err != nil {
		return errors.New("publisher drain failed")
	}
	ctx, cancel = context.WithTimeout(context.Background(), 20*time.Second)
	err = s.Close(ctx)
	cancel()
	if err != nil {
		return errors.New("subscriber drain failed")
	}
	sort.Slice(latencies, func(i, j int) bool { return latencies[i] < latencies[j] })
	percentile := func(p float64) float64 {
		if len(latencies) == 0 {
			return 0
		}
		return float64(latencies[int(float64(len(latencies)-1)*p)]) / float64(time.Millisecond)
	}
	p95, p99 := percentile(.95), percentile(.99)
	passed := confirmed == total && unknown == 0 && rejected == 0 && dropped == 0 && invalid == 0 && len(seen) == total && p95 <= 500 && p99 <= 2000 && publishSeconds <= duration.Seconds()*1.05
	report := map[string]any{"run_id": runID, "payload_bytes": len(body), "scheduled": total, "confirmed": confirmed, "unknown": unknown, "rejected": rejected, "local_capacity_dropped": dropped, "unique_received": len(seen), "acknowledged_deliveries": acked, "redeliveries": duplicates, "invalid": invalid, "publish_seconds": publishSeconds, "latency_p95_ms": p95, "latency_p99_ms": p99, "passed": passed}
	if err = json.NewEncoder(os.Stdout).Encode(report); err != nil {
		return err
	}
	if !passed {
		return errors.New("required load thresholds not met")
	}
	return nil
}
