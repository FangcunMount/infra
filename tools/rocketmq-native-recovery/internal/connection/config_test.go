package connection

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"fangcunmount.infra/rocketmq-native-recovery/internal/authority"
	"fangcunmount.infra/rocketmq-native-recovery/internal/privatefile"
	"fangcunmount.infra/rocketmq-native-recovery/internal/review"
	"github.com/FangcunMount/reliable-messaging/transaction"
	"github.com/FangcunMount/reliable-messaging/transport"
)

func configFixture() Config {
	return Config{Schema: "m3-native-recovery-config/v1", Owner: "iam.mysql", StoreID: "original", WriterEpoch: "epoch-1", DatabaseKind: "mysql", DatabaseURI: "unit:do-not-log-secret@tcp(127.0.0.1:1)/original", DatabaseName: "original", Endpoint: "127.0.0.1:1", AccessKey: "unit", SecretKey: "do-not-log-secret"}
}
func TestConfigConstructionAndMySQLOpenAreInertAndBounded(t *testing.T) {
	c := configFixture()
	if c.Validate() != nil {
		t.Fatal("invalid fixture")
	}
	v, err := c.mysqlConfig()
	if err != nil || !v.ParseTime || v.Timeout != 2*time.Second || v.ReadTimeout != 5*time.Second || v.WriteTimeout != 5*time.Second || v.MultiStatements {
		t.Fatal("unbounded SQL config")
	}
	o, err := Open(context.Background(), c)
	if err != nil {
		t.Fatal(err)
	}
	if o.Authority == nil {
		t.Fatal("no original authority")
	}
	if err = o.Close(); err != nil {
		t.Fatal(err)
	}
}
func TestConfigRejectsWrongBindingAndUnsafeOverridesWithoutCredentialErrors(t *testing.T) {
	for _, name := range []string{"schema", "owner", "store", "epoch", "kind", "database", "root-ca", "database-ca", "endpoint", "empty-endpoint", "credentials", "multi-statements", "interpolate", "plaintext-fallback", "tls-skip", "unix-socket", "invalid-dsn", "mongo-kind", "mongo-uri", "mongo-ca"} {
		t.Run(name, func(t *testing.T) {
			c := configFixture()
			switch name {
			case "schema":
				c.Schema = "wrong"
			case "owner":
				c.Owner = "other"
			case "store":
				c.StoreID = ""
			case "epoch":
				c.WriterEpoch = ""
			case "kind":
				c.DatabaseKind = "mongo"
			case "database":
				c.DatabaseName = "wrong"
			case "root-ca":
				c.RootCA = "not a certificate"
			case "database-ca":
				c.DatabaseCA = "not a certificate"
			case "endpoint":
				c.Endpoint = "localhost:99999"
			case "empty-endpoint":
				c.Endpoint = ":1"
			case "credentials":
				c.SecretKey = ""
			case "multi-statements":
				c.DatabaseURI += "?multiStatements=true"
			case "interpolate":
				c.DatabaseURI += "?interpolateParams=true"
			case "plaintext-fallback":
				c.DatabaseURI += "?allowFallbackToPlaintext=true"
			case "tls-skip":
				c.DatabaseURI += "?tls=skip-verify"
			case "unix-socket":
				c.DatabaseURI = "unit:secret@unix(/tmp/not-opened.sock)/original"
			case "invalid-dsn":
				c.DatabaseURI = "invalid do-not-log-secret"
			case "mongo-kind":
				c.Owner = "qs.mongo"
			case "mongo-uri":
				c.Owner = "qs.mongo"
				c.DatabaseKind = "mongo"
				c.DatabaseURI = "invalid secret"
			case "mongo-ca":
				c.Owner = "qs.mongo"
				c.DatabaseKind = "mongo"
				c.DatabaseURI = "mongodb://localhost:1/original"
				c.DatabaseCA = "ignored-cert"
			}
			if err := c.Validate(); !errors.Is(err, ErrConfig) || strings.Contains(err.Error(), "secret") {
				t.Fatal("unsafe configuration accepted or credentials leaked")
			}
		})
	}
}

func TestManifestSelectsAllOwnerTopicsAndDeduplicatesFanout(t *testing.T) {
	raw, err := os.ReadFile("../../../../components/rocketmq/serverd-routes-m3-v2.json")
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "manifest.json")
	sum, err := privatefile.Write(path, raw)
	if err != nil {
		t.Fatal(err)
	}
	var m manifest
	if json.Unmarshal(raw, &m) != nil {
		t.Fatal("invalid fixture")
	}
	for _, owner := range []string{"iam.mysql", "qs.mysql", "qs.mongo", "ai.mysql"} {
		routes, err := Routes(path, sum, owner)
		if err != nil {
			t.Fatal(owner, err)
		}
		expected := map[string]bool{}
		for _, r := range m.Routes {
			if r.Owner == owner && r.Type == "TRANSACTION" {
				expected[r.Physical] = true
			}
		}
		if len(routes) != len(expected) {
			t.Fatal("missing idle owner routes or fanout duplicated")
		}
		for _, r := range routes {
			if !expected[r.PhysicalTopic] {
				t.Fatal("foreign or NORMAL topic")
			}
		}
	}
	if _, err := Routes(path, sum, "foreign"); err == nil {
		t.Fatal("accepted empty owner route inventory")
	}
	for _, name := range []string{"type", "physical", "revision", "group", "duplicate-id", "unknown-field"} {
		t.Run(name, func(t *testing.T) {
			var m manifest
			if json.Unmarshal(raw, &m) != nil {
				t.Fatal("fixture")
			}
			switch name {
			case "type":
				m.Routes[0].Type = "NORMAL"
			case "physical":
				m.Routes[0].Physical += "wrong"
			case "revision":
				m.Routes[0].Revision = "m3-2"
			case "group":
				m.Routes[0].Group = "wrong"
			case "duplicate-id":
				m.Routes = append(m.Routes, m.Routes[0])
			}
			p := filepath.Join(t.TempDir(), "manifest.json")
			b, e := json.Marshal(m)
			if e != nil {
				t.Fatal(e)
			}
			if name == "unknown-field" {
				b = append([]byte(`{"unexpected":true,`), b[1:]...)
			}
			sha, e := privatefile.Write(p, b)
			if e != nil {
				t.Fatal(e)
			}
			if _, e = Routes(p, sha, "iam.mysql"); e == nil {
				t.Fatal("accepted inconsistent complete manifest")
			}
		})
	}
}

func TestFreshSnapshotMatchPermitsOnlyAuditAdvancement(t *testing.T) {
	// This is a controlled snapshot test, not a database or current RPC proof.
	ref := transaction.Reference{Owner: "iam.mysql", Scope: "s", OperationID: "op", BranchID: "b", MessageID: "id", LogicalTopic: "logical", PhysicalTopic: "unused", RouteRevision: "m3-1", WriterEpoch: "e", Fence: 1, PlanDigest: [32]byte{1}, WireHash: [32]byte{2}, MessageFingerprint: [32]byte{3}}
	// Build a valid physical Topic using the same manifest-independent SDK rule.
	physical, e := transport.PhysicalTopicV2(ref.LogicalTopic, transport.TransactionMessageType, ref.Owner, ref.RouteRevision)
	if e != nil {
		t.Fatal(e)
	}
	ref.PhysicalTopic = physical
	b := transaction.Binding{Owner: ref.Owner, StoreID: "original", WriterEpoch: ref.WriterEpoch}
	index := [32]byte{4}
	s := authority.Snapshot{Binding: b, Reference: ref, DatabaseIdentitySHA256: [32]byte{5}, Decision: transaction.Commit, Half: transaction.HalfPrepared, BeforeFinal: transaction.FinalUnknown, Notice: authority.Notice{Key: authority.NoticeKey(b, index), IndexSHA256: index, FirstEvidenceSHA256: [32]byte{6}, Status: "blocked"}}
	f, err := review.Freeze(s)
	if err != nil {
		t.Fatal(err)
	}
	r := review.Request{Snapshot: f}
	at := time.Unix(1, 0).UTC()
	s.BeforeFinal = transaction.FinalCommitConfirmed
	s.BeforeFinalAt = &at
	if Match(r, s) != nil {
		t.Fatal("old positive audit cannot invalidate same authority")
	}
	s.DatabaseIdentitySHA256 = sha256.Sum256([]byte("other-primary"))
	if Match(r, s) == nil {
		t.Fatal("accepted foreign original DB")
	}
}
