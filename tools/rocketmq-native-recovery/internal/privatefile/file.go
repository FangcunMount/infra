// Package privatefile handles bounded, independently hashed operation objects.
// A matching digest is integrity evidence, never operator authorization.
package privatefile

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"syscall"
)

var ErrPrivate = errors.New("bounded private operation object required")

const MaxBytes = 65536

func Read(path string, expected [32]byte) (raw []byte, err error) {
	if expected == [32]byte{} {
		return nil, ErrPrivate
	}
	raw, err = ReadCurrent(path)
	if err != nil || sha256.Sum256(raw) != expected {
		return nil, ErrPrivate
	}
	return raw, nil
}

// ReadCurrent is only for the coordinator's mutable, derived state/markers.
// It does not turn them into an independently approved request or plan.
func ReadCurrent(path string) (raw []byte, err error) {
	if !filepath.IsAbs(path) || filepath.Clean(path) != path {
		return nil, ErrPrivate
	}
	fd, e := syscall.Open(path, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK, 0)
	if e != nil {
		return nil, ErrPrivate
	}
	f := os.NewFile(uintptr(fd), path)
	return readFile(f)
}

// ReadAt keeps the coordinator directory inode pinned across all its reads.
// Only literal leaf names are accepted; this is not an approval constructor.
func ReadAt(root *os.Root, name string) ([]byte, error) {
	if root == nil || name == "" || filepath.Base(name) != name || name == "." || name == ".." {
		return nil, ErrPrivate
	}
	f, err := root.OpenFile(name, os.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK, 0)
	if err != nil {
		return nil, ErrPrivate
	}
	return readFile(f)
}

func readFile(f *os.File) (raw []byte, err error) {
	defer func() {
		if f.Close() != nil {
			err = ErrPrivate
		}
		if err != nil {
			raw = nil
		}
	}()
	info, e := f.Stat()
	if e != nil || !info.Mode().IsRegular() || info.Mode().Perm() != 0600 || info.Size() < 1 || info.Size() > MaxBytes {
		return nil, ErrPrivate
	}
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok || stat.Uid != uint32(os.Geteuid()) || stat.Nlink != 1 || stat.Mode&(syscall.S_ISUID|syscall.S_ISGID|syscall.S_ISVTX) != 0 {
		return nil, ErrPrivate
	}
	raw, e = io.ReadAll(io.LimitReader(f, MaxBytes+1))
	if e != nil || len(raw) > MaxBytes {
		return nil, ErrPrivate
	}
	return raw, nil
}

// Write creates one object without replacing, truncating, or removing old data.
// Files are retained on sync/close failures; no successful digest is returned.
func Write(path string, raw []byte) (digest [32]byte, err error) {
	if !filepath.IsAbs(path) || filepath.Clean(path) != path || len(raw) < 1 || len(raw) > MaxBytes {
		return digest, ErrPrivate
	}
	f, e := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL|syscall.O_NOFOLLOW, 0600)
	if e != nil {
		return digest, ErrPrivate
	}
	_, writeErr := f.Write(raw)
	syncErr := f.Sync()
	closeErr := f.Close()
	if errors.Join(writeErr, syncErr, closeErr) != nil {
		return digest, ErrPrivate
	}
	d, e := os.Open(filepath.Dir(path))
	if e != nil {
		return digest, ErrPrivate
	}
	syncErr = d.Sync()
	closeErr = d.Close()
	if errors.Join(syncErr, closeErr) != nil {
		return digest, ErrPrivate
	}
	return sha256.Sum256(raw), nil
}

// Decode rejects duplicate/case-alias keys, extra values, excessive depth,
// non-object roots and unknown fields before any side effect. Protocol object
// keys use lower snake case; SDK canonical Reference bytes remain opaque strings.
func Decode(raw []byte, target any) error {
	if len(raw) < 2 || len(raw) > MaxBytes || target == nil {
		return ErrPrivate
	}
	d := json.NewDecoder(bytes.NewReader(raw))
	d.UseNumber()
	if err := fields(d, 0); err != nil {
		return err
	}
	if _, err := d.Token(); err != io.EOF {
		return ErrPrivate
	}
	typed := json.NewDecoder(bytes.NewReader(raw))
	typed.DisallowUnknownFields()
	if typed.Decode(target) != nil {
		return ErrPrivate
	}
	return nil
}
func fields(d *json.Decoder, depth int) error {
	if depth > 12 {
		return ErrPrivate
	}
	token, err := d.Token()
	if err != nil {
		return ErrPrivate
	}
	if depth == 0 && token != json.Delim('{') {
		return ErrPrivate
	}
	delim, container := token.(json.Delim)
	if !container {
		return nil
	}
	switch delim {
	case '{':
		seen := map[string]bool{}
		for d.More() {
			token, e := d.Token()
			if e != nil {
				return ErrPrivate
			}
			key, ok := token.(string)
			if !ok || !protocolKey(key) || seen[key] {
				return ErrPrivate
			}
			seen[key] = true
			if fields(d, depth+1) != nil {
				return ErrPrivate
			}
		}
		end, e := d.Token()
		if e != nil || end != json.Delim('}') {
			return ErrPrivate
		}
	case '[':
		for d.More() {
			if fields(d, depth+1) != nil {
				return ErrPrivate
			}
		}
		end, e := d.Token()
		if e != nil || end != json.Delim(']') {
			return ErrPrivate
		}
	default:
		return ErrPrivate
	}
	return nil
}
func protocolKey(key string) bool {
	if key == "" || len(key) > 128 || key != strings.ToLower(key) {
		return false
	}
	for i, c := range key {
		if c < 'a' || c > 'z' {
			if i == 0 || (c != '_' && (c < '0' || c > '9')) {
				return false
			}
		}
	}
	return true
}
