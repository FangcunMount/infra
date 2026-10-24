// Package barrier validates the existing infra coordinator's issued step.
// It neither issues approvals nor resets or manufactures a start marker.
package barrier

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"syscall"

	"fangcunmount.infra/rocketmq-native-recovery/internal/privatefile"
)

var ErrIssued = errors.New("live reviewed coordinator step required before recovery effects")
var stepPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$`)

type Context struct {
	Directory                     string
	BindingSHA256, StepPlanSHA256 [32]byte
	Step                          string
}
type Issued struct{ context Context }

func (p Issued) Valid() bool {
	return p.context.BindingSHA256 != [32]byte{} && p.context.StepPlanSHA256 != [32]byte{}
}

type binding struct {
	Schema        string `json:"schema"`
	Operation     string `json:"operation_id"`
	Directory     string `json:"directory"`
	Scope         string `json:"scope_sha256"`
	Protection    string `json:"protection_sha256"`
	Restore       string `json:"restore_receipt_sha256"`
	Source        string `json:"source_bundle_sha256"`
	DataOwner     string `json:"data_owner"`
	RecoveryOwner string `json:"recovery_owner"`
}
type state struct {
	Binding string `json:"binding_sha256"`
	Phase   string `json:"phase"`
	Step    string `json:"step"`
}
type marker struct {
	Binding string `json:"binding_sha256"`
	Step    string `json:"first_step"`
}
type stepPlan struct {
	Schema    string `json:"schema"`
	Directory string `json:"directory"`
	Binding   string `json:"binding_sha256"`
	Host      string `json:"host"`
	Step      string `json:"step"`
	Kind      string `json:"kind"`
	Script    string `json:"script"`
	ScriptSHA string `json:"script_sha256"`
	CWD       string `json:"cwd"`
	Timeout   int    `json:"timeout_seconds"`
}

func digest(v string) bool {
	decoded, err := hex.DecodeString(v)
	return err == nil && len(decoded) == 32 && v == hex.EncodeToString(decoded)
}
func absolute(v string) bool {
	return filepath.IsAbs(v) && filepath.Clean(v) == v && len(v) <= 4096 && !strings.ContainsRune(v, 0)
}
func named(v string) bool {
	if strings.TrimSpace(v) == "" || len(v) > 128 {
		return false
	}
	for _, c := range v {
		if c < 32 {
			return false
		}
	}
	return true
}

// RequireIssued is only one gate: request/receipt approval, source/config,
// physical inspection, genuine SDK observations and all other preconditions
// remain separate. It requires the coordinator's live directory lock and the
// exact runtime/forward step it durably published before entering its callback.
func RequireIssued(c Context) (proof Issued, err error) {
	if !absolute(c.Directory) || !stepPattern.MatchString(c.Step) || c.BindingSHA256 == [32]byte{} || c.StepPlanSHA256 == [32]byte{} {
		return proof, ErrIssued
	}
	dir, e := os.OpenFile(c.Directory, os.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW, 0)
	if e != nil {
		return proof, ErrIssued
	}
	defer dir.Close()
	info, e := dir.Stat()
	if e != nil || !info.IsDir() || info.Mode().Perm() != 0700 {
		return proof, ErrIssued
	}
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok || stat.Uid != uint32(os.Geteuid()) || stat.Mode&(syscall.S_ISUID|syscall.S_ISGID|syscall.S_ISVTX) != 0 {
		return proof, ErrIssued
	}
	// The coordinator holds this lock while running the immutable script. An
	// unlocked old marker is history, not authorization for a new command.
	lockErr := syscall.Flock(int(dir.Fd()), syscall.LOCK_EX|syscall.LOCK_NB)
	if lockErr == nil {
		_ = syscall.Flock(int(dir.Fd()), syscall.LOCK_UN)
		return proof, ErrIssued
	}
	if !errors.Is(lockErr, syscall.EWOULDBLOCK) && !errors.Is(lockErr, syscall.EAGAIN) {
		return proof, ErrIssued
	}
	root, e := os.OpenRoot(c.Directory)
	if e != nil {
		return proof, ErrIssued
	}
	defer root.Close()
	pinned, e := root.Stat(".")
	if e != nil || !os.SameFile(info, pinned) {
		return proof, ErrIssued
	}
	read := func(name string, value any, expected *[32]byte) bool {
		raw, e := privatefile.ReadAt(root, name)
		return e == nil && (expected == nil || sha256.Sum256(raw) == *expected) && privatefile.Decode(raw, value) == nil
	}
	var b binding
	var s state
	var m marker
	var p stepPlan
	if !read("binding.json", &b, &c.BindingSHA256) || !read("state.json", &s, nil) || !read("first-runtime-start.json", &m, nil) || !read("reviewed-step-"+hex.EncodeToString(c.StepPlanSHA256[:])+".json", &p, &c.StepPlanSHA256) {
		return proof, ErrIssued
	}
	bound := hex.EncodeToString(c.BindingSHA256[:])
	host, e := os.Hostname()
	if e != nil {
		return proof, ErrIssued
	}
	if b.Schema != "m3-start-boundary/v1" || b.Directory != c.Directory || !stepPattern.MatchString(b.Operation) || !digest(b.Scope) || !digest(b.Protection) || !digest(b.Restore) || !digest(b.Source) || !named(b.DataOwner) || !named(b.RecoveryOwner) {
		return proof, ErrIssued
	}
	if s.Binding != bound || m.Binding != bound || !stepPattern.MatchString(m.Step) || s.Step != c.Step {
		return proof, ErrIssued
	}
	if p.Schema != "m3-cutover-step/v1" || p.Directory != c.Directory || p.Binding != bound || p.Host != host || p.Step != c.Step || !absolute(p.Script) || !absolute(p.CWD) || !digest(p.ScriptSHA) || p.Timeout < 1 || p.Timeout > 1200 {
		return proof, ErrIssued
	}
	if !((s.Phase == "runtime_start_issued" && p.Kind == "runtime-start") || (s.Phase == "forward_repair_issued" && p.Kind == "forward-repair")) {
		return proof, ErrIssued
	}
	if p.Kind == "forward-repair" {
		var approval struct {
			Binding string `json:"binding_sha256"`
			Step    string `json:"step"`
			SHA     string `json:"approval_sha256"`
		}
		sha := hex.EncodeToString(c.StepPlanSHA256[:])
		if !read("repair-approval-"+sha+".json", &approval, nil) || approval.Binding != bound || approval.Step != c.Step || approval.SHA != sha {
			return proof, ErrIssued
		}
	}
	return Issued{c}, nil
}
