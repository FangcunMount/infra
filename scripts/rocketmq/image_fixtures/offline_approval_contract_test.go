// Synthetic cross-language contract, not database/restore/production evidence.
package migration

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"strings"
	"testing"
	"time"
)

func TestM3ImageOfflineApprovalContract(t *testing.T) {
	path := os.Getenv("M3_OFFLINE_APPROVAL_FIXTURE")
	source := os.Getenv("M3_EXPECTED_QS_SHA")
	if path == "" || len(source) != 40 {
		t.Fatal("explicit synthetic fixture and source required")
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var value offlineAuthorization
	if err := json.Unmarshal(raw, &value); err != nil {
		t.Fatal(err)
	}
	resources, err := compiledMigrationResources()
	if err != nil {
		t.Fatal(err)
	}
	initial := OfflineSnapshot{SourceSHA: source, MigrationResourcesSHA256: strings.Repeat("b", 64),
		MySQLDatabase: "qs_m3_image_contract", MongoDatabase: "qs_m3_image_contract",
		MySQLIdentitySHA256: strings.Repeat("c", 64), MongoClusterSHA256: strings.Repeat("d", 64),
		MySQLVersion: 105, MongoVersion: 40, TargetMySQLVersion: resources.sql.head, TargetMongoVersion: resources.mongo.head}
	digest := sha256.Sum256(raw)
	if _, err := readOfflineAuthorization(OfflineConfig{AuthorizationFile: path, AuthorizationSHA256: hex.EncodeToString(digest[:])}, initial); err != nil {
		t.Fatal("original Go reader rejected Python-generated synthetic approval:", err)
	}
	bad := value
	bad.OperationID = "m3-image-owned"
	if validateOfflineAuthorization(bad, initial, time.Now()) == nil {
		t.Fatal("Compose name accepted as schema operation")
	}
	bad = value
	bad.TargetMongoVersion++
	if validateOfflineAuthorization(bad, initial, time.Now()) == nil {
		t.Fatal("wrong compiled target accepted")
	}
}
