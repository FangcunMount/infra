// CI-only preparation of a disposable full IAM schema41. Copied into the
// reviewed IAM module to call its original migrations/bootstrap, never shipped.
package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"os"
	"strings"

	"github.com/FangcunMount/iam/v5/internal/apiserver/infra/mysql/eventoutbox"
	"github.com/FangcunMount/iam/v5/internal/apiserver/maintenance/conditionretire"
	"github.com/FangcunMount/iam/v5/internal/apiserver/maintenance/rolemodel"
	"github.com/FangcunMount/iam/v5/internal/pkg/migration"
	"github.com/FangcunMount/iam/v5/pkg/eventcatalog"
	mysql "github.com/go-sql-driver/mysql"
	gormmysql "gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

var preparationStage = "guard"

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
	preparationStage = "catalog"
	catalog, err := eventcatalog.Load("configs/events.yaml")
	if err != nil {
		return err
	}
	preparationStage = "bootstrap_stager"
	stager, err := eventoutbox.NewBootstrapStager(eventcatalog.NewCatalog(catalog))
	if err != nil {
		return err
	}
	ctx := context.Background()
	for _, target := range []uint{31, 33, 35, 41} {
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
	fmt.Println("original schema41 fixture prepared; bootstrap messages still require real NSQ drain")
}
