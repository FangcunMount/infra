// Package connection selects the reviewed original database and the complete
// owner route inventory. Messages and request attributes never select a DSN.
package connection

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"database/sql"
	"errors"
	"net"
	"strconv"
	"time"

	"fangcunmount.infra/rocketmq-native-recovery/internal/authority"
	"fangcunmount.infra/rocketmq-native-recovery/internal/privatefile"
	"fangcunmount.infra/rocketmq-native-recovery/internal/review"
	"github.com/FangcunMount/reliable-messaging/transaction"
	"github.com/FangcunMount/reliable-messaging/transport"
	"github.com/FangcunMount/reliable-messaging/transport/rocketmq"
	"github.com/go-sql-driver/mysql"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

var ErrConfig = errors.New("explicit reviewed original database and complete owner routes required")

type Config struct {
	Schema       string `json:"schema"`
	Owner        string `json:"owner"`
	StoreID      string `json:"store_id"`
	WriterEpoch  string `json:"writer_epoch"`
	DatabaseKind string `json:"database_kind"`
	DatabaseURI  string `json:"database_uri"`
	DatabaseName string `json:"database_name"`
	DatabaseCA   string `json:"database_ca_pem"`
	Endpoint     string `json:"endpoint"`
	AccessKey    string `json:"access_key"`
	SecretKey    string `json:"secret_key"`
	RootCA       string `json:"root_ca_pem"`
}

func (c Config) Binding() transaction.Binding {
	return transaction.Binding{Owner: c.Owner, StoreID: c.StoreID, WriterEpoch: c.WriterEpoch}
}

func Load(path string, expected [32]byte) (c Config, err error) {
	raw, err := privatefile.Read(path, expected)
	if err != nil || privatefile.Decode(raw, &c) != nil || c.Validate() != nil {
		return Config{}, ErrConfig
	}
	return c, nil
}
func (c Config) Validate() error {
	if c.Schema != "m3-native-recovery-config/v1" || !c.Binding().Valid() || len(c.Owner) > 128 || len(c.StoreID) > 128 || len(c.WriterEpoch) > 128 || c.DatabaseURI == "" || c.DatabaseName == "" || len(c.DatabaseName) > 64 || c.AccessKey == "" || c.SecretKey == "" {
		return ErrConfig
	}
	host, port, err := net.SplitHostPort(c.Endpoint)
	n, e := strconv.Atoi(port)
	if err != nil || e != nil || host == "" || n < 1 || n > 65535 {
		return ErrConfig
	}
	switch c.Owner {
	case "iam.mysql", "qs.mysql", "ai.mysql":
		if c.DatabaseKind != "mysql" {
			return ErrConfig
		}
		if _, err = c.mysqlConfig(); err != nil {
			return ErrConfig
		}
	case "qs.mongo":
		options := options.Client().ApplyURI(c.DatabaseURI)
		if c.DatabaseKind != "mongo" || c.DatabaseCA != "" || options.Validate() != nil || (options.TLSConfig != nil && options.TLSConfig.InsecureSkipVerify) {
			return ErrConfig
		}
	default:
		return ErrConfig
	}
	if _, err = c.TLS(); err != nil {
		return ErrConfig
	}
	return nil
}
func verifiedTLS(pem string) (*tls.Config, error) {
	t := &tls.Config{MinVersion: tls.VersionTLS12}
	if pem != "" {
		t.RootCAs = x509.NewCertPool()
		if !t.RootCAs.AppendCertsFromPEM([]byte(pem)) {
			return nil, ErrConfig
		}
	}
	return t, nil
}
func (c Config) TLS() (*tls.Config, error) { return verifiedTLS(c.RootCA) }
func (c Config) mysqlConfig() (*mysql.Config, error) {
	v, err := mysql.ParseDSN(c.DatabaseURI)
	if err != nil || v.DBName != c.DatabaseName || v.Net != "tcp" || v.Addr == "" || v.User == "" || v.MultiStatements || v.InterpolateParams || v.AllowAllFiles || v.AllowCleartextPasswords || v.AllowFallbackToPlaintext || (v.TLSConfig != "" && v.TLSConfig != "true") {
		return nil, ErrConfig
	}
	// Direct instance TLS config avoids process-global registration. Plain TCP
	// remains explicit for existing private/isolated DB paths, never MQ TLS.
	if c.DatabaseCA != "" || v.TLSConfig == "true" {
		v.TLS, err = verifiedTLS(c.DatabaseCA)
		if err != nil {
			return nil, ErrConfig
		}
	}
	v.ParseTime = true
	v.Timeout, v.ReadTimeout, v.WriteTimeout = 2*time.Second, 5*time.Second, 5*time.Second
	return v, nil
}

type manifest struct {
	Version      int `json:"version"`
	TopicOptions struct {
		Read  int `json:"read_queue_nums"`
		Write int `json:"write_queue_nums"`
		Perm  int `json:"perm"`
	} `json:"topic_options"`
	GroupOptions struct {
		Retry int `json:"retry_queue_nums"`
	} `json:"group_options"`
	Routes   []route            `json:"routes"`
	Accounts map[string]account `json:"accounts"`
}
type account struct {
	Owner         string   `json:"owner"`
	Publish       []string `json:"publish"`
	Subscriptions []string `json:"subscriptions"`
}

var accountNames = []string{"m3-iam", "m3-qs-apiserver", "m3-qs-worker", "m3-qs-mongo", "m3-ai"}

type route struct {
	ID           string `json:"id"`
	Topic        string `json:"topic"`
	Subscription string `json:"subscription"`
	Type         string `json:"message_type"`
	Owner        string `json:"owner"`
	Revision     string `json:"route_revision"`
	Physical     string `json:"physical_topic"`
	Group        string `json:"consumer_group"`
}

// Routes validates the entire frozen v2 manifest before selecting/deduplicating
// all this owner's transaction Topics, including idle fanout routes.
func Routes(path string, expected [32]byte, owner string) ([]rocketmq.TransactionRoute, error) {
	raw, err := privatefile.Read(path, expected)
	var m manifest
	if err != nil || privatefile.DecodeNamed(raw, &m, accountNames...) != nil || m.Version != 2 || m.TopicOptions.Read < 1 || m.TopicOptions.Write < 1 || m.TopicOptions.Perm != 6 || m.GroupOptions.Retry < 1 || len(m.Routes) < 1 || len(m.Routes) > 256 || len(m.Accounts) != len(accountNames) {
		return nil, ErrConfig
	}
	ids := map[string]bool{}
	physical := map[string]rocketmq.TransactionRoute{}
	var routes []rocketmq.TransactionRoute
	for _, r := range m.Routes {
		if r.ID == "" || ids[r.ID] || r.Revision != "m3-1" {
			return nil, ErrConfig
		}
		ids[r.ID] = true
		expected, e := transport.PhysicalTopicV2(r.Topic, r.Type, r.Owner, r.Revision)
		if e != nil || expected != r.Physical {
			return nil, ErrConfig
		}
		if r.Subscription != "" {
			group, e := transport.ConsumerGroupV2(r.Topic, r.Subscription)
			if e != nil || group != r.Group {
				return nil, ErrConfig
			}
		} else if r.Group != "" {
			return nil, ErrConfig
		}
		if r.Owner != owner || r.Type != transport.TransactionMessageType {
			continue
		}
		v := rocketmq.TransactionRoute{LogicalTopic: r.Topic, PhysicalTopic: r.Physical, Revision: r.Revision}
		if old, ok := physical[r.Physical]; ok {
			if old != v {
				return nil, ErrConfig
			}
			continue
		}
		physical[r.Physical] = v
		routes = append(routes, v)
	}
	if len(routes) == 0 {
		return nil, ErrConfig
	}
	byID := map[string]route{}
	for _, r := range m.Routes {
		byID[r.ID] = r
	}
	for _, name := range accountNames {
		a, ok := m.Accounts[name]
		if !ok {
			return nil, ErrConfig
		}
		for _, list := range []struct {
			ids     []string
			publish bool
		}{{a.Publish, true}, {a.Subscriptions, false}} {
			seen := map[string]bool{}
			for _, id := range list.ids {
				r, ok := byID[id]
				if !ok || seen[id] || (list.publish && (a.Owner == "" || r.Owner != a.Owner)) || (!list.publish && r.Subscription == "") {
					return nil, ErrConfig
				}
				seen[id] = true
			}
		}
	}
	return routes, nil
}

type Authority interface {
	Snapshot(context.Context, authority.Locator, [32]byte) (authority.Snapshot, error)
	CheckStore() (transaction.PreparedStore, error)
	ResolveNotice(context.Context, authority.Resolution) (authority.ResolutionResult, error)
	VerifyResolution(context.Context, authority.Resolution) error
}
type Opened struct {
	Authority Authority
	close     func() error
}

func (o Opened) Close() error {
	if o.close == nil {
		return nil
	}
	return o.close()
}

// Open never installs schema, bindings or indexes. MySQL sql.OpenDB is inert;
// Mongo's owned topology resources are closed on every constructor failure.
func Open(ctx context.Context, c Config) (out Opened, err error) {
	if c.Validate() != nil {
		return out, ErrConfig
	}
	if c.DatabaseKind == "mysql" {
		v, e := c.mysqlConfig()
		if e != nil {
			return out, ErrConfig
		}
		connector, e := mysql.NewConnector(v)
		if e != nil {
			return out, ErrConfig
		}
		db := sql.OpenDB(connector)
		db.SetMaxOpenConns(4)
		db.SetMaxIdleConns(1)
		db.SetConnMaxLifetime(5 * time.Minute)
		a, e := authority.NewMySQL(db, c.Binding())
		if e != nil {
			_ = db.Close()
			return out, ErrConfig
		}
		return Opened{a, db.Close}, nil
	}
	client, e := mongo.Connect(ctx, options.Client().ApplyURI(c.DatabaseURI).SetMaxPoolSize(4).SetMinPoolSize(0).SetServerSelectionTimeout(2*time.Second).SetConnectTimeout(2*time.Second))
	closeClient := func() error {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		return client.Disconnect(ctx)
	}
	if e != nil {
		return out, ErrConfig
	}
	a, e := authority.NewMongo(client.Database(c.DatabaseName), c.Binding())
	if e != nil {
		_ = closeClient()
		return out, ErrConfig
	}
	return Opened{a, closeClient}, nil
}

// Match binds fresh primary evidence to the request; audit may have advanced
// since preview, but identity, terminal decision and first native proof cannot.
func Match(r review.Request, s authority.Snapshot) error {
	original, err := r.Snapshot.Authority()
	if err != nil || authority.ValidateReview(s) != nil || original.Binding != s.Binding || original.Reference != s.Reference || original.Decision != s.Decision || original.DatabaseIdentitySHA256 != s.DatabaseIdentitySHA256 || original.Notice.Key != s.Notice.Key || original.Notice.IndexSHA256 != s.Notice.IndexSHA256 || original.Notice.FirstEvidenceSHA256 != s.Notice.FirstEvidenceSHA256 {
		return review.ErrReview
	}
	return nil
}
