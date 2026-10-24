//go:build integration

package authority

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/FangcunMount/reliable-messaging/transaction"
)

// Executes the compiled, fixed-tag CLI as a separate process against this
// already-owned original database. Native index/approval inputs are explicitly
// synthetic fixtures: no MQ, SDK runtime or production authority is implied.
func previewCLINative(t *testing.T, s Snapshot, databaseKind, uri, databaseName string, installNotice func([32]byte, [32]byte)) {
	t.Helper()
	binary := os.Getenv("NATIVE_TOOL_TEST_CLI")
	if !filepath.IsAbs(binary) {
		t.Fatal("required compiled CLI missing")
	}
	root := t.TempDir()
	if err := os.Chmod(root, 0700); err != nil {
		t.Fatal(err)
	}
	digest := func(raw []byte) string { sum := sha256.Sum256(raw); return hex.EncodeToString(sum[:]) }
	write := func(name string, value any) (string, string) {
		t.Helper()
		raw, err := json.Marshal(value)
		if err != nil {
			t.Fatal(err)
		}
		raw = append(raw, '\n')
		path := filepath.Join(root, name)
		if err = os.WriteFile(path, raw, 0600); err != nil {
			t.Fatal(err)
		}
		return path, digest(raw)
	}
	invoke := func(wantSuccess bool, args ...string) map[string]any {
		t.Helper()
		ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		cmd := exec.CommandContext(ctx, binary, args...)
		cmd.WaitDelay = time.Second
		raw, err := cmd.CombinedOutput()
		if (err == nil) != wantSuccess {
			t.Fatal("compiled CLI command failed its expected bounded outcome")
		}
		if strings.Contains(string(raw), uri) || strings.Contains(string(raw), "do-not-log") {
			t.Fatal("CLI exposed private connection")
		}
		if !wantSuccess {
			return nil
		}
		var value map[string]any
		if json.Unmarshal(raw, &value) != nil {
			t.Fatal("CLI returned non-JSON or raw diagnostics")
		}
		return value
	}
	version := invoke(true, "version")
	if version["sdk_version"] != "v0.5.0-rocketmq-tx.4" || version["effectful_commands"] != true {
		t.Fatal("wrong executable provenance or effect boundary")
	}
	export := map[string]any{"topic": "TRANS_CHECK_MAX_TIME_TOPIC", "key_sha256": strings.Repeat("1", 64), "records": []map[string]any{{"broker_message_id": strings.Repeat("A", 32), "queue_id": 0, "queue_offset": 1, "commitlog_offset": 2, "index_hour": 3}}, "raw_admin_sha256": strings.Repeat("2", 64), "read_only": true, "body_exported": false, "truncated_possible": false, "alert": "native_transaction_check_limit_reached", "severity": "critical"}
	exportPath, exportSHA := write("synthetic-index.json", export)
	// Shared host v1 vector; copying a client ID does not identify its position.
	indexBytes, err := hex.DecodeString("c17eef089ffe8dcd195b09d54c8d7af26283362fc173a6226b964a4a4c0968d3")
	if err != nil {
		t.Fatal(err)
	}
	var index, first [32]byte
	copy(index[:], indexBytes)
	firstBytes, err := hex.DecodeString(exportSHA)
	if err != nil {
		t.Fatal(err)
	}
	copy(first[:], firstBytes)
	installNotice(index, first)
	configPath, configSHA := write("original-config.json", map[string]any{"schema": "m3-native-recovery-config/v1", "owner": s.Binding.Owner, "store_id": s.Binding.StoreID, "writer_epoch": s.Binding.WriterEpoch, "database_kind": databaseKind, "database_uri": uri, "database_name": databaseName, "database_ca_pem": "", "endpoint": "127.0.0.1:1", "access_key": "synthetic-no-sdk-start", "secret_key": "do-not-log", "root_ca_pem": ""})
	accounts := map[string]any{}
	for _, name := range []string{"m3-iam", "m3-qs-apiserver", "m3-qs-worker", "m3-qs-mongo", "m3-ai"} {
		accounts[name] = map[string]any{"owner": "", "publish": []string{}, "subscriptions": []string{}}
	}
	manifestPath, manifestSHA := write("synthetic-reviewed-routes.json", map[string]any{"version": 2, "topic_options": map[string]int{"read_queue_nums": 1, "write_queue_nums": 1, "perm": 6}, "group_options": map[string]int{"retry_queue_nums": 8}, "routes": []map[string]any{{"id": "native-preview", "topic": s.Reference.LogicalTopic, "subscription": "", "message_type": "TRANSACTION", "owner": s.Binding.Owner, "route_revision": "m3-1", "physical_topic": s.Reference.PhysicalTopic, "consumer_group": ""}}, "accounts": accounts})
	selectionPath, selectionSHA := write("selection.json", map[string]any{"schema": "m3-native-recovery-selection/v1", "operation_id": s.Reference.OperationID, "branch_id": s.Reference.BranchID, "fence": s.Reference.Fence, "native_index_sha256": hex.EncodeToString(index[:]), "source_bundle_sha256": strings.Repeat("3", 64), "data_owner": "synthetic-data-owner", "recovery_owner": "synthetic-recovery-owner"})
	requestPath := filepath.Join(root, "request.json")
	args := []string{"preview", "--config", configPath, "--config-sha", configSHA, "--manifest", manifestPath, "--manifest-sha", manifestSHA, "--export", exportPath, "--export-sha", exportSHA, "--selection", selectionPath, "--selection-sha", selectionSHA, "--output", requestPath}
	result := invoke(true, args...)
	if result["database_read_only"] != true || result["sdk_started"] != false || result["native_admin_started"] != false || result["governance_written"] != false {
		t.Fatal("misstated CLI effects")
	}
	raw, err := os.ReadFile(requestPath)
	if err != nil || digest(raw) != result["request_sha256"] {
		t.Fatal("private request hash mismatch")
	}
	info, err := os.Lstat(requestPath)
	if err != nil || info.Mode().Perm() != 0600 {
		t.Fatal("request not private")
	}
	var request struct {
		Source   string    `json:"source_sha"`
		Binary   string    `json:"binary_sha256"`
		Nonce    string    `json:"invocation_nonce"`
		Expires  time.Time `json:"expires_at"`
		Snapshot struct {
			Reference string                   `json:"reference"`
			Database  string                   `json:"database_identity_sha256"`
			Final     transaction.FinalOutcome `json:"before_final"`
			FinalAt   *time.Time               `json:"before_final_at"`
			Index     string                   `json:"native_index_sha256"`
			Proof     string                   `json:"first_evidence_sha256"`
		} `json:"snapshot"`
	}
	if json.Unmarshal(raw, &request) != nil {
		t.Fatal("private request decode")
	}
	ref, err := transaction.EncodeReference(s.Reference)
	if err != nil || request.Source != version["source_sha"] || request.Binary != version["binary_sha256"] || len(request.Nonce) != 64 || request.Snapshot.Reference != string(ref) || request.Snapshot.Database != hex.EncodeToString(s.DatabaseIdentitySHA256[:]) || request.Snapshot.Final != s.BeforeFinal || request.Snapshot.Index != hex.EncodeToString(index[:]) || request.Snapshot.Proof != exportSHA || (s.BeforeFinalAt != nil && (request.Snapshot.FinalAt == nil || !request.Snapshot.FinalAt.Equal(*s.BeforeFinalAt))) {
		t.Fatal("CLI lost exact primary identity, first audit or frozen bytes")
	}
	approvalPath, approvalSHA := write("synthetic-named-approval.json", map[string]any{"schema": "m3-native-recovery-approval/v1", "action": "check", "request_sha256": result["request_sha256"], "receipt_sha256": "", "coordinator_binding_sha256": strings.Repeat("4", 64), "source_bundle_sha256": strings.Repeat("3", 64), "data_owner": "synthetic-data-owner", "recovery_owner": "synthetic-recovery-owner", "expires_at": request.Expires})
	verified := invoke(true, "verify-review", "--request", requestPath, "--request-sha", result["request_sha256"].(string), "--approval", approvalPath, "--approval-sha", approvalSHA, "--binding-sha", strings.Repeat("4", 64))
	if verified["review_graph_valid"] != true || verified["execution_authorized"] != false {
		t.Fatal("review claimed effect authorization")
	}
	invoke(false, args...) // Retrying preview cannot overwrite the first request.
	invoke(false, "check") // No hidden execution capability in the preview CLI.
	after, err := os.ReadFile(requestPath)
	if err != nil || digest(after) != digest(raw) {
		t.Fatal("duplicate request altered first private file")
	}
	t.Log("compiled_preview_cli_original_primary=true no_sdk_or_admin_started=true synthetic_index_and_approval=true")
}
