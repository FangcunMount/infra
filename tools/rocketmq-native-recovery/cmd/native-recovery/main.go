// native-recovery currently exposes only read-only preview and review checking.
// No invocation of this binary can start an SDK or perform native/governance
// recovery yet; those effectful entrypoints require their own real-MQ gates.
package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"runtime/debug"
	"syscall"
	"time"

	"fangcunmount.infra/rocketmq-native-recovery/internal/preview"
	"fangcunmount.infra/rocketmq-native-recovery/internal/review"
)

// Set from the exact frozen infra commit with -ldflags -X main.sourceSHA=...
// A working-tree string or an unversioned build must not claim a release SHA.
var sourceSHA string

var errCommand = errors.New("native recovery input/build unavailable; no recovery action performed")

func identity() ([32]byte, error) {
	var sum [32]byte
	info, ok := debug.ReadBuildInfo()
	if !ok || !review.Source(sourceSHA) {
		return sum, errCommand
	}
	fixed := false
	for _, d := range info.Deps {
		if d.Path == "github.com/FangcunMount/reliable-messaging" {
			fixed = d.Version == "v0.5.0-rocketmq-tx.4" && d.Sum == "h1:PflI1oWRjU4RFKvpi8WE/8ICI/1IUp8q8EOsbW1DXCI=" && d.Replace == nil
		}
	}
	if !fixed {
		return sum, errCommand
	}
	revision, clean := "", false
	for _, setting := range info.Settings {
		switch setting.Key {
		case "vcs.revision":
			revision = setting.Value
		case "vcs.modified":
			clean = setting.Value == "false"
		}
	}
	if revision != sourceSHA || !clean {
		return sum, errCommand
	}
	path, err := os.Executable()
	if err != nil {
		return sum, errCommand
	}
	f, err := os.Open(path)
	if err != nil {
		return sum, errCommand
	}
	defer f.Close()
	i, err := f.Stat()
	if err != nil || !i.Mode().IsRegular() || i.Size() < 1 || i.Size() > 128<<20 {
		return sum, errCommand
	}
	h := sha256.New()
	n, err := io.Copy(h, io.LimitReader(f, (128<<20)+1))
	if err != nil || n != i.Size() {
		return sum, errCommand
	}
	copy(sum[:], h.Sum(nil))
	return sum, nil
}

type commandFile struct{ path, sha string }

func fileFlags(f *flag.FlagSet, name string) *commandFile {
	v := &commandFile{}
	f.StringVar(&v.path, name, "", "absolute private input path")
	f.StringVar(&v.sha, name+"-sha", "", "independently reviewed raw SHA-256")
	return v
}
func (v commandFile) value() (preview.File, error) {
	sum, err := review.Digest(v.sha)
	if v.path == "" || err != nil {
		return preview.File{}, errCommand
	}
	return preview.File{Path: v.path, SHA256: sum}, nil
}

func run(ctx context.Context, args []string, out, diagnostics io.Writer) error {
	if len(args) == 0 {
		return errCommand
	}
	f := flag.NewFlagSet(args[0], flag.ContinueOnError)
	f.SetOutput(io.Discard) // flag errors must not echo a secret/URI accidentally passed as a value.
	switch args[0] {
	case "version":
		if len(args) != 1 {
			return errCommand
		}
		sum, err := identity()
		if err != nil {
			return errCommand
		}
		return json.NewEncoder(out).Encode(map[string]any{"schema": "m3-native-recovery-build/v1", "source_sha": sourceSHA, "binary_sha256": hex.EncodeToString(sum[:]), "sdk_version": "v0.5.0-rocketmq-tx.4", "effectful_commands": false})
	case "preview":
		config, manifest, export, selection := fileFlags(f, "config"), fileFlags(f, "manifest"), fileFlags(f, "export"), fileFlags(f, "selection")
		output := f.String("output", "", "new request file under an existing private 0700 directory")
		if f.Parse(args[1:]) != nil || f.NArg() != 0 {
			return errCommand
		}
		binarySHA, err := identity()
		if err != nil {
			return errCommand
		}
		input := preview.Input{Output: *output, SourceSHA: sourceSHA, BinarySHA: binarySHA}
		for _, item := range []struct {
			in   *commandFile
			dest *preview.File
		}{{config, &input.Config}, {manifest, &input.Manifest}, {export, &input.Export}, {selection, &input.Selection}} {
			v, e := item.in.value()
			if e != nil {
				return errCommand
			}
			*item.dest = v
		}
		bounded, cancel := context.WithTimeout(ctx, 10*time.Second)
		defer cancel()
		sum, err := preview.Run(bounded, input, time.Now().UTC(), preview.Original)
		if err != nil {
			return errCommand
		}
		return json.NewEncoder(out).Encode(map[string]any{"schema": "m3-native-recovery-preview/v1", "request_sha256": review.Hex(sum), "database_read_only": true, "sdk_started": false, "native_admin_started": false, "governance_written": false})
	case "verify-review":
		request, approval := fileFlags(f, "request"), fileFlags(f, "approval")
		binding := f.String("binding-sha", "", "original coordinator binding SHA-256")
		if f.Parse(args[1:]) != nil || f.NArg() != 0 {
			return errCommand
		}
		binarySHA, err := identity()
		if err != nil {
			return errCommand
		}
		rf, err := request.value()
		if err != nil {
			return errCommand
		}
		af, err := approval.value()
		if err != nil {
			return errCommand
		}
		bs, err := review.Digest(*binding)
		if err != nil {
			return errCommand
		}
		now := time.Now().UTC()
		r, err := review.Load(rf.Path, rf.SHA256, now)
		if err != nil || r.SourceSHA != sourceSHA || r.BinarySHA != review.Hex(binarySHA) || review.Approve(af.Path, af.SHA256, r, rf.SHA256, [32]byte{}, bs, "check", now) != nil {
			return errCommand
		}
		// This command does not inspect a live issued barrier or authorize any
		// effect. It is an offline review aid, not the recovery execution gate.
		return json.NewEncoder(out).Encode(map[string]any{"schema": "m3-native-recovery-review/v1", "review_graph_valid": true, "execution_authorized": false, "sdk_started": false, "governance_written": false})
	case "help", "--help", "-h":
		_, err := fmt.Fprintln(out, "native-recovery: version | preview | verify-review\nRead-only request preparation; no SDK, native admin or governance recovery entrypoint.")
		return err
	default:
		_ = diagnostics // Reserved for generic stage-only diagnostics, never raw inputs.
		return errCommand
	}
}
func main() {
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	if run(ctx, os.Args[1:], os.Stdout, os.Stderr) != nil {
		fmt.Fprintln(os.Stderr, errCommand)
		os.Exit(1)
	}
}
