//go:build integration

// Copied into the exact QS migration test package only on an owned CI runner.
// Pre-M3 fixtures apply unchanged original templates through105/40; journals
// are written by the original migrator, never force-set. Not a production tool.
package migration

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io/fs"
	"net"
	"net/url"
	"os"
	"regexp"
	"strconv"
	"strings"
	"testing"
	"testing/fstest"
	"time"

	"github.com/FangcunMount/qs-server/pkg/version"
	drivermysql "github.com/go-sql-driver/mysql"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

func TestM3ImagePreparePair(t *testing.T) {
	if os.Getenv("GITHUB_ACTIONS") != "true" || os.Getenv("RUNNER_ENVIRONMENT") != "github-hosted" {
		t.Fatal("owned GitHub fixture required")
	}
	phase := "guard"
	check := func(err error) {
		t.Helper()
		if err != nil {
			t.Fatalf("QS_IMAGE_FAILURE phase=%s kind=%T", phase, err)
		}
	}
	name := os.Getenv("QS_IMAGE_DATABASE")
	if !regexp.MustCompile(`^qs_m3_image_[a-z0-9_]{1,36}$`).MatchString(name) || !offlineSourceSHA.MatchString(version.GitCommit) {
		t.Fatal("exact source and owned schema required")
	}
	cfg, err := drivermysql.ParseDSN(os.Getenv("QS_IMAGE_MYSQL_DSN"))
	check(err)
	host, _, err := net.SplitHostPort(cfg.Addr)
	check(err)
	uri := os.Getenv("QS_IMAGE_MONGO_URI")
	u, err := url.Parse(uri)
	check(err)
	if host != "mysql" || cfg.DBName != name || u.Hostname() != "mongo" {
		t.Fatal("owned internal database endpoints required")
	}
	profile := os.Getenv("QS_IMAGE_PROFILE")
	if profile != "current" && profile != "pre_m3" {
		t.Fatal("explicit fixture profile required")
	}
	phase = "connections"
	cfg.MultiStatements = true
	cfg.Timeout, cfg.ReadTimeout, cfg.WriteTimeout = 5*time.Second, 15*time.Second, 15*time.Second
	connector, err := drivermysql.NewConnector(cfg)
	check(err)
	db := sql.OpenDB(connector)
	defer db.Close()
	ctx, cancel := context.WithTimeout(t.Context(), 5*time.Minute)
	defer cancel()
	check(db.PingContext(ctx))
	client, err := mongo.Connect(ctx, options.Client().ApplyURI(uri).SetServerSelectionTimeout(5*time.Second))
	check(err)
	defer func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer closeCancel()
		_ = client.Disconnect(closeCtx)
	}()
	var tables int
	check(db.QueryRowContext(ctx, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()").Scan(&tables))
	collections, err := client.Database(name).ListCollectionNames(ctx, bson.D{})
	check(err)
	if tables != 0 || len(collections) != 0 {
		t.Fatal("pristine owned pair required")
	}
	phase = "resources"
	resources, err := compiledMigrationResources()
	check(err)
	if profile == "pre_m3" {
		selected := fstest.MapFS{}
		for _, item := range []struct {
			directory string
			maximum   uint
		}{{"mysql", 105}, {"mongodb", 40}} {
			entries, err := fs.ReadDir(migrations, "migrations/"+item.directory)
			check(err)
			for _, entry := range entries {
				if entry.IsDir() || !regexp.MustCompile(`^[0-9]{6}_`).MatchString(entry.Name()) {
					continue
				}
				n, err := strconv.ParseUint(entry.Name()[:6], 10, 32)
				check(err)
				if uint(n) > item.maximum {
					continue
				}
				path := "migrations/" + item.directory + "/" + entry.Name()
				raw, err := fs.ReadFile(migrations, path)
				check(err)
				selected[path] = &fstest.MapFile{Data: raw, Mode: 0444}
			}
		}
		var pairs []schemaVersionPair
		for _, pair := range declaredSchemaPairs {
			if pair.SQL <= 105 && pair.Mongo <= 40 {
				pairs = append(pairs, pair)
			}
		}
		resources, err = readMigrationResources(selected, pairs)
		check(err)
		if resources.sql.head != 105 || resources.mongo.head != 40 {
			t.Fatal("unchanged pre-M3 template heads required")
		}
	}
	phase = "pristine_approval"
	input, approval := testBootstrapApproval(t, resources)
	input.MySQLDatabase, input.MongoDatabase, input.ExpectedSourceSHA = name, name, version.GitCommit
	approval.MySQLDatabase, approval.MongoDatabase, approval.ApprovedSourceSHA = name, name, version.GitCommit
	approval.OperationID = os.Getenv("GITHUB_RUN_ID") + "-" + os.Getenv("GITHUB_RUN_ATTEMPT")
	approval.MySQLIdentitySHA256, approval.MongoClusterSHA256, err = pairIdentity(ctx, db, client, name, name)
	check(err)
	provenance, err := json.Marshal(map[string]string{"scope": "owned controlled pristine fixture, not production", "source": version.GitCommit, "resources": resources.sha256, "mysql": approval.MySQLIdentitySHA256, "mongo": approval.MongoClusterSHA256})
	check(err)
	digest := sha256.Sum256(provenance)
	approval.ApprovalSummarySHA256 = hex.EncodeToString(digest[:])
	writeBootstrapApproval(t, &input, approval)
	pair, err := preflightCompatibilityPair(ctx, db, client, input, resources)
	check(err)
	phase = "original_mysql_migrations"
	sqlConfig := pair.MySQLConfig(false)
	sqlConfig.runContext = ctx
	sqlVersion, _, err := NewMigrator(db, sqlConfig).Run()
	check(err)
	phase = "original_mongo_migrations"
	mongoConfig := pair.MongoConfig(false)
	mongoConfig.runContext = ctx
	mongoVersion, _, err := NewMongoMigrator(client, mongoConfig).Run()
	check(err)
	phase = "readback"
	check(pair.VerifyComplete(ctx))
	if sqlVersion != resources.sql.head || mongoVersion != resources.mongo.head {
		t.Fatal("actual migration heads differ")
	}
	raw, err := json.Marshal(map[string]any{"source_sha": version.GitCommit, "profile": profile, "mysql": sqlVersion, "mongo": mongoVersion, "resources_sha256": resources.sha256,
		"original_templates_applied": true, "journal_force_used": false, "production": false})
	check(err)
	fmt.Println("QS_IMAGE_INIT " + strings.TrimSpace(string(raw)))
}
