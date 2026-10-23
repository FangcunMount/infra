package observation

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"testing"

	"fangcunmount.infra/rocketmq-native-recovery/internal/checkonly"
	"github.com/FangcunMount/reliable-messaging/transaction"
)

func identity() Identity {
	return Identity{RequestSHA256: [32]byte{1}, Nonce: [32]byte{2}, ReferenceSHA256: [32]byte{3}, SourceSHA: [20]byte{4}, Outcome: transaction.FinalCommitConfirmed}
}

func TestPrivateCurrentObservationIsExclusiveBoundedAndDigestExact(t *testing.T) {
	id := identity()
	r, err := New(t.TempDir(), id)
	if err != nil {
		t.Fatal(err)
	}
	info, err := os.Lstat(r.Directory())
	if err != nil || !info.IsDir() || info.Mode().Perm() != 0700 {
		t.Fatal("directory not private", err)
	}
	for range 2 {
		if err = r.Sink(context.Background(), checkonly.Event{ReferenceSHA256: id.ReferenceSHA256, Outcome: id.Outcome}); err != nil {
			t.Fatal(err)
		}
	}
	select {
	case <-r.First():
	default:
		t.Fatal("successful write did not wake observer")
	}
	files, err := r.Close()
	if err != nil || len(files) != 2 {
		t.Fatal(files, err)
	}
	for _, f := range files {
		path := filepath.Join(r.Directory(), f.Name)
		info, err = os.Lstat(path)
		if err != nil || !info.Mode().IsRegular() || info.Mode().Perm() != 0600 {
			t.Fatal("observation not private", err)
		}
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		sum := sha256.Sum256(raw)
		if f.SHA256 != hex.EncodeToString(sum[:]) {
			t.Fatal("receipt differs from actual file bytes")
		}
		var record Record
		if json.Unmarshal(raw, &record) != nil || record.RequestSHA256 != hex.EncodeToString(id.RequestSHA256[:]) || record.InvocationNonce != hex.EncodeToString(id.Nonce[:]) || record.ReferenceSHA256 != hex.EncodeToString(id.ReferenceSHA256[:]) || record.SourceSHA != hex.EncodeToString(id.SourceSHA[:]) || record.Outcome != id.Outcome || record.ObservedAt.IsZero() {
			t.Fatal("current invocation identity lost")
		}
	}
	if again, err := r.Close(); err != nil || len(again) != 2 {
		t.Fatal("repeated close lost outcome", err)
	}
}

func TestNoPositiveProofAfterCancellationCollisionMismatchOrLimit(t *testing.T) {
	for _, scenario := range []string{"no-callback", "cancelled", "collision", "symlink", "reference", "outcome", "limit"} {
		t.Run(scenario, func(t *testing.T) {
			id := identity()
			r, err := New(t.TempDir(), id)
			if err != nil {
				t.Fatal(err)
			}
			event := checkonly.Event{ReferenceSHA256: id.ReferenceSHA256, Outcome: id.Outcome}
			ctx := context.Background()
			switch scenario {
			case "cancelled":
				var cancel context.CancelFunc
				ctx, cancel = context.WithCancel(ctx)
				cancel()
			case "collision":
				if err = os.WriteFile(filepath.Join(r.Directory(), "rpc-01.json"), []byte("keep"), 0600); err != nil {
					t.Fatal(err)
				}
			case "symlink":
				if err = os.Symlink(filepath.Join(t.TempDir(), "outside"), filepath.Join(r.Directory(), "rpc-01.json")); err != nil {
					t.Fatal(err)
				}
			case "reference":
				event.ReferenceSHA256[0] ^= 1
			case "outcome":
				event.Outcome = transaction.FinalRollbackConfirmed
			case "limit":
				for range maxObservations {
					if err = r.Sink(ctx, event); err != nil {
						t.Fatal(err)
					}
				}
			}
			if scenario != "no-callback" && !errors.Is(r.Sink(ctx, event), ErrObservation) {
				t.Fatal("unsafe observation accepted")
			}
			if _, err = r.Close(); !errors.Is(err, ErrObservation) {
				t.Fatal("incomplete observation reported positive proof")
			}
			if scenario == "collision" {
				raw, _ := os.ReadFile(filepath.Join(r.Directory(), "rpc-01.json"))
				if string(raw) != "keep" {
					t.Fatal("existing evidence overwritten")
				}
			}
		})
	}
}

func TestConstructorRejectsIncompleteFrozenIdentityBeforeCreatingFiles(t *testing.T) {
	parent := t.TempDir()
	for _, change := range []func(*Identity){
		func(i *Identity) { i.RequestSHA256 = [32]byte{} }, func(i *Identity) { i.Nonce = [32]byte{} }, func(i *Identity) { i.ReferenceSHA256 = [32]byte{} }, func(i *Identity) { i.SourceSHA = [20]byte{} }, func(i *Identity) { i.Outcome = transaction.FinalUnknown },
	} {
		id := identity()
		change(&id)
		if _, err := New(parent, id); !errors.Is(err, ErrObservation) {
			t.Fatal("invalid identity accepted")
		}
	}
	entries, err := os.ReadDir(parent)
	if err != nil || len(entries) != 0 {
		t.Fatal("invalid identity created files", err)
	}
}
