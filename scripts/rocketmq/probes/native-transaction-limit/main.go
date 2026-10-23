// Isolated CI fault generator only. This is not a business SDK acceptance probe.
package main

import (
	"bufio"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"time"

	rmq "github.com/apache/rocketmq-clients/golang/v5"
	"github.com/apache/rocketmq-clients/golang/v5/credentials"
)

type config struct{ Project, Endpoint, CAFile, AccessKey, SecretKey, Topic, Key string }

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
	if e != nil || !net.ParseIP(host).IsLoopback() || !strings.HasPrefix(c.Project, "rocketmq-m2-") || !filepath.IsAbs(c.CAFile) || len(c.Topic) == 0 || len(c.Topic) > 255 || len(c.Key) == 0 || len(c.Key) > 128 || len(c.AccessKey) == 0 || len(c.SecretKey) == 0 {
		return c, errors.New("owned isolated loopback fixture required")
	}
	return c, nil
}
func run(c config) error {
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
	var checks atomic.Int64
	client := func(c *rmq.Config, opts ...rmq.ClientOption) (rmq.Client, error) {
		opts = append(opts, rmq.WithConnOptions(rmq.WithTLSConfig(tc)), rmq.WithRpcClientOptions(rmq.WithRpcClientConnOption(rmq.WithTLSConfig(tc)), rmq.WithRpcClientTimeout(5*time.Second)))
		return rmq.NewClient(c, opts...)
	}
	producer, e := rmq.NewProducer(&rmq.Config{Endpoint: c.Endpoint, Credentials: &credentials.SessionCredentials{AccessKey: c.AccessKey, AccessSecret: c.SecretKey}}, rmq.WithClientFunc(client), rmq.WithTopics(c.Topic), rmq.WithMaxAttempts(1), rmq.WithTransactionChecker(&rmq.TransactionChecker{Check: func(*rmq.MessageView) rmq.TransactionResolution { checks.Add(1); return rmq.UNKNOWN }}))
	if e != nil {
		return errors.New("isolated fault producer construction failed")
	}
	if producer.Start() != nil {
		return errors.New("isolated fault producer start failed")
	}
	defer producer.GracefulStop()
	msg := &rmq.Message{Topic: c.Topic, Body: []byte("private-native-limit-fault")}
	msg.SetKeys(c.Key)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	receipts, e := producer.SendWithTransaction(ctx, msg, producer.BeginTransaction())
	if e != nil || len(receipts) != 1 {
		return errors.New("isolated fault half not confirmed")
	}
	fmt.Println(`M3_NATIVE_LIMIT_FAULT {"event":"ready","prepared":1}`)
	scanner := bufio.NewScanner(os.Stdin)
	scanner.Buffer(make([]byte, 128), 128)
	if !scanner.Scan() || scanner.Text() != "stop" {
		return errors.New("explicit fault fixture stop required")
	}
	fmt.Printf("M3_NATIVE_LIMIT_FAULT {\"event\":\"closed\",\"prepared\":1,\"unknown_checks\":%d,\"business_calls\":0,\"final_confirmation_calls\":0}\n", checks.Load())
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
		fmt.Fprintln(os.Stderr, "isolated native-limit fault failed")
		os.Exit(1)
	}
}
