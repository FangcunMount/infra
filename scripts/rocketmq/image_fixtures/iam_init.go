// CI-only schema40 and controlled AuthZ seed, never a legacy message drain.
// Bootstrap events are retained in an explicit fixture archive in their source
// root, without constructing publication intents, witnesses or broker messages.
// This initializer is never shipped or used by production.
package main

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"os"
	"strings"

	"github.com/FangcunMount/iam/v5/internal/apiserver/maintenance/conditionretire"
	"github.com/FangcunMount/iam/v5/internal/apiserver/maintenance/rolemodel"
	dbmysql "github.com/FangcunMount/iam/v5/internal/pkg/database/mysql"
	"github.com/FangcunMount/iam/v5/internal/pkg/migration"
	"github.com/FangcunMount/iam/v5/pkg/event"
	mysql "github.com/go-sql-driver/mysql"
	gormmysql "gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

var preparationStage = "guard"
var seedEvents int

type fixtureSeedArchive struct{}

func (fixtureSeedArchive) Stage(ctx context.Context, events ...event.DomainEvent) error {
	tx, err := dbmysql.RequireTx(ctx)
	if err != nil {
		return err
	}
	for _, value := range events {
		body, err := json.Marshal(value.Payload())
		if err != nil {
			return err
		}
		digest := sha256.Sum256(body)
		if err = tx.Exec("INSERT INTO fixture_bootstrap_event_archive(event_id,event_type,payload_sha256) VALUES(?,?,?)",
			value.EventID(), value.EventType(), digest[:]).Error; err != nil {
			return err
		}
	}
	return nil
}

func prepare() error {
	if os.Getenv("GITHUB_ACTIONS") != "true" || os.Getenv("RUNNER_ENVIRONMENT") != "github-hosted" {
		return fmt.Errorf("owned GitHub fixture required")
	}
	cfg, err := mysql.ParseDSN(os.Getenv("IAM_IMAGE_FIXTURE_DSN"))
	if err != nil {
		return err
	}
	host, _, err := net.SplitHostPort(cfg.Addr)
	if err != nil || host != "mysql" || !strings.HasPrefix(cfg.DBName, "iam_m3_image_") {
		return fmt.Errorf("owned internal fixture schema required")
	}
	open := func() (*sql.DB, error) {
		c, err := mysql.NewConnector(cfg)
		if err != nil {
			return nil, err
		}
		return sql.OpenDB(c), nil
	}
	preparationStage = "open_pool"
	pool, err := open()
	if err != nil {
		return err
	}
	defer pool.Close()
	var tables int
	preparationStage = "check_empty"
	if err = pool.QueryRow("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()").Scan(&tables); err != nil {
		return err
	}
	if tables != 0 {
		return fmt.Errorf("empty fixture schema required")
	}
	preparationStage = "gorm"
	db, err := gorm.Open(gormmysql.New(gormmysql.Config{Conn: pool}), &gorm.Config{Logger: logger.Default.LogMode(logger.Silent)})
	if err != nil {
		return err
	}
	stager := fixtureSeedArchive{}
	ctx := context.Background()
	for _, target := range []uint{31, 33, 35, 40} {
		preparationStage = fmt.Sprintf("migrate_%d", target)
		migrationPool, err := open()
		if err != nil {
			return err
		}
		version, _, err := migration.NewMigrator(migrationPool, &migration.Config{Enabled: true, Database: cfg.DBName}).RunTo(target)
		if err != nil {
			return err
		}
		if version != target {
			return fmt.Errorf("original fixture migration version differs")
		}
		preparationStage = fmt.Sprintf("bootstrap_%d", target)
		switch target {
		case 31:
			if err = db.Exec("CREATE TABLE fixture_bootstrap_event_archive(event_id VARBINARY(128) PRIMARY KEY,event_type VARBINARY(255) NOT NULL,payload_sha256 BINARY(32) NOT NULL) ENGINE=InnoDB").Error; err != nil {
				return err
			}
			err = rolemodel.PrepareBootstrapTenant(ctx, db)
		case 33:
			err = rolemodel.BootstrapIndependentRoles(ctx, db, stager)
		case 35:
			err = conditionretire.Bootstrap(ctx, db, stager)
		}
		if err != nil {
			return err
		}
	}
	if err = db.Raw("SELECT COUNT(*) FROM fixture_bootstrap_event_archive").Scan(&seedEvents).Error; err != nil {
		return err
	}
	if seedEvents < 1 || seedEvents > 16 {
		return fmt.Errorf("bounded controlled seed archive required")
	}
	return nil
}

func main() {
	if err := prepare(); err != nil {
		// Never print migration SQL, DSNs or original error messages.
		var server *mysql.MySQLError
		code := uint16(0)
		if errors.As(err, &server) {
			code = server.Number
		}
		raw, _ := json.Marshal(map[string]any{"phase": preparationStage, "kind": fmt.Sprintf("%T", err), "server_code": code})
		fmt.Println("IAM_IMAGE_FIXTURE_FAILURE " + string(raw))
		os.Exit(1)
	}
	raw, _ := json.Marshal(map[string]any{"schema_version": 40, "seed_events_retained": seedEvents, "controlled_seed": true,
		"publication_intents_created": false, "witnesses_created": false, "legacy_drain_claimed": false})
	fmt.Println("IAM_IMAGE_FIXTURE_READY " + string(raw))
}
