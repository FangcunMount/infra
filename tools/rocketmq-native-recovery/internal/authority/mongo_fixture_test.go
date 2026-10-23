package authority

import (
	"crypto/sha256"
	_ "embed"
	"encoding/hex"
	"testing"
)

// Frozen test-only copy; the recovery operator never installs this resource.
//
//go:embed testdata/qs-000043-governance.json
var nativeMongoNoticeSchema string

func TestFrozenMongoGovernanceFixtureMatchesRecordedHostMigration(t *testing.T) {
	sum := sha256.Sum256([]byte(nativeMongoNoticeSchema))
	if hex.EncodeToString(sum[:]) != "d6904ab7c3ab3c4a310314dc7f532eb321679a0e7a31c0b867c11a9280bfc4fa" {
		t.Fatal("frozen QS43 governance fixture changed")
	}
}
