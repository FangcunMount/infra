package privatefile

import (
	"crypto/sha256"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
)

func TestPrivateObjectRoundTripAndNoOverwrite(t *testing.T) {
	path := filepath.Join(t.TempDir(), "request.json")
	raw := []byte(`{"schema":"unit/v1","owner":"qs.mongo"}`)
	digest, err := Write(path, raw)
	if err != nil || digest != sha256.Sum256(raw) {
		t.Fatal(err)
	}
	info, err := os.Lstat(path)
	if err != nil || info.Mode().Perm() != 0600 {
		t.Fatal("object not private", err)
	}
	loaded, err := Read(path, digest)
	if err != nil || string(loaded) != string(raw) {
		t.Fatal("exact original bytes not preserved", err)
	}
	if _, err = Write(path, []byte("changed")); !errors.Is(err, ErrPrivate) {
		t.Fatal("overwrote old evidence")
	}
	loaded, err = Read(path, digest)
	if err != nil || string(loaded) != string(raw) {
		t.Fatal("old evidence altered", err)
	}
}

func TestPrivateObjectRejectsUnsafeOrChangedSource(t *testing.T) {
	for _, scenario := range []string{"digest", "no-digest", "mode", "empty", "large", "hardlink", "symlink", "fifo", "directory"} {
		t.Run(scenario, func(t *testing.T) {
			root := t.TempDir()
			path := filepath.Join(root, "input.json")
			raw := []byte(`{"schema":"unit/v1"}`)
			digest := sha256.Sum256(raw)
			switch scenario {
			case "symlink":
				if err := os.Symlink(filepath.Join(root, "outside"), path); err != nil {
					t.Fatal(err)
				}
			case "fifo":
				if err := syscall.Mkfifo(path, 0600); err != nil {
					t.Fatal(err)
				}
			case "directory":
				if err := os.Mkdir(path, 0700); err != nil {
					t.Fatal(err)
				}
			default:
				if scenario == "empty" {
					raw = nil
				}
				if scenario == "large" {
					raw = make([]byte, MaxBytes+1)
				}
				if err := os.WriteFile(path, raw, 0600); err != nil {
					t.Fatal(err)
				}
				if scenario == "mode" {
					if err := os.Chmod(path, 0644); err != nil {
						t.Fatal(err)
					}
				}
				if scenario == "hardlink" {
					if err := os.Link(path, filepath.Join(root, "alias")); err != nil {
						t.Fatal(err)
					}
				}
				if scenario == "digest" {
					digest[0] ^= 1
				}
				if scenario == "no-digest" {
					digest = [32]byte{}
				}
			}
			if raw, err := Read(path, digest); !errors.Is(err, ErrPrivate) || raw != nil {
				t.Fatal("unsafe object accepted")
			}
		})
	}
}

func TestStrictObjectDecodeRejectsAmbiguousProtocolWithoutEchoingValues(t *testing.T) {
	type object struct {
		Owner  string `json:"owner"`
		Nested struct {
			Count int `json:"count"`
		} `json:"nested"`
	}
	for _, raw := range []string{
		`{"owner":"secret","owner":"other"}`, `{"Owner":"secret"}`, `{"owner":"secret","Owner":"other"}`,
		`{"nested":{"count":1,"count":2}}`, `{"owner":"secret","unknown":1}`, `{"nested":{"count":1.5}}`,
		`{"owner":"secret"} {}`, `[]`, `null`, `"secret"`, strings.Repeat(`{"nested":`, 14) + `{}` + strings.Repeat(`}`, 14),
	} {
		var value object
		err := Decode([]byte(raw), &value)
		if !errors.Is(err, ErrPrivate) || strings.Contains(err.Error(), "secret") {
			t.Fatal("ambiguous object or private diagnostic accepted")
		}
	}
	var value object
	if err := Decode([]byte(`{"owner":"qs.mongo","nested":{"count":2}}`), &value); err != nil || value.Owner != "qs.mongo" || value.Nested.Count != 2 {
		t.Fatal("valid lower-snake object rejected", err)
	}
}
