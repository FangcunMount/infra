// Package preview builds a private read-only recovery request. It cannot start
// an SDK, re-enqueue a half message, record confirmation or resolve governance.
package preview

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"fangcunmount.infra/rocketmq-native-recovery/internal/authority"
	"fangcunmount.infra/rocketmq-native-recovery/internal/connection"
	"fangcunmount.infra/rocketmq-native-recovery/internal/privatefile"
	"fangcunmount.infra/rocketmq-native-recovery/internal/review"
	"github.com/FangcunMount/reliable-messaging/transaction"
)

type File struct {
	Path   string
	SHA256 [32]byte
}
type Input struct {
	Config, Manifest, Export, Selection File
	Output                              string
	SourceSHA                           string
	BinarySHA                           [32]byte
}
type Selection struct {
	Schema          string `json:"schema"`
	Operation       string `json:"operation_id"`
	Branch          string `json:"branch_id"`
	Fence           uint64 `json:"fence"`
	IndexSHA        string `json:"native_index_sha256"`
	SourceBundleSHA string `json:"source_bundle_sha256"`
	DataOwner       string `json:"data_owner"`
	RecoveryOwner   string `json:"recovery_owner"`
}

// Reader deliberately has no write, CheckStore or SDK capability.
type Reader interface {
	Snapshot(context.Context, authority.Locator, [32]byte) (authority.Snapshot, error)
}
type Owned struct {
	Reader Reader
	Close  func() error
}
type Open func(context.Context, connection.Config) (Owned, error)

func Original(ctx context.Context, c connection.Config) (Owned, error) {
	o, err := connection.Open(ctx, c)
	if err != nil {
		return Owned{}, err
	}
	return Owned{o.Authority, o.Close}, nil
}

func outputPrivate(path string) bool {
	if !filepath.IsAbs(path) || filepath.Clean(path) != path {
		return false
	}
	if _, err := os.Lstat(path); !os.IsNotExist(err) {
		return false
	}
	i, err := os.Lstat(filepath.Dir(path))
	if err != nil || !i.IsDir() || i.Mode().Perm() != 0700 {
		return false
	}
	s, ok := i.Sys().(*syscall.Stat_t)
	return ok && s.Uid == uint32(os.Geteuid()) && s.Mode&(syscall.S_ISUID|syscall.S_ISGID|syscall.S_ISVTX) == 0
}

// Run validates every private input and the complete owner route inventory
// before opening the original DB. It retains output on any close/sync failure.
func Run(ctx context.Context, in Input, now time.Time, open Open) (sum [32]byte, err error) {
	if open == nil || !review.Source(in.SourceSHA) || in.BinarySHA == [32]byte{} || !outputPrivate(in.Output) {
		return sum, review.ErrReview
	}
	c, err := connection.Load(in.Config.Path, in.Config.SHA256)
	if err != nil {
		return sum, review.ErrReview
	}
	routes, err := connection.Routes(in.Manifest.Path, in.Manifest.SHA256, c.Owner)
	if err != nil {
		return sum, review.ErrReview
	}
	raw, err := privatefile.Read(in.Selection.Path, in.Selection.SHA256)
	var s Selection
	if err != nil || privatefile.Decode(raw, &s) != nil || s.Schema != "m3-native-recovery-selection/v1" || strings.TrimSpace(s.Operation) == "" || strings.TrimSpace(s.Branch) == "" || len(s.Operation) > 4096 || len(s.Branch) > 4096 || s.Fence < 1 || s.Fence > transaction.MaxFence || !review.Named(s.DataOwner) || !review.Named(s.RecoveryOwner) {
		return sum, review.ErrReview
	}
	index, err := review.Digest(s.IndexSHA)
	if err != nil {
		return sum, review.ErrReview
	}
	source, err := review.Digest(s.SourceBundleSHA)
	if err != nil {
		return sum, review.ErrReview
	}
	i, err := review.SelectExport(in.Export.Path, in.Export.SHA256, index)
	if err != nil {
		return sum, review.ErrReview
	}
	owned, err := open(ctx, c)
	if err != nil {
		return sum, review.ErrReview
	}
	if owned.Close == nil {
		return sum, review.ErrReview
	}
	defer func() {
		if owned.Close() != nil {
			sum = [32]byte{}
			err = review.ErrReview
		}
	}()
	if owned.Reader == nil {
		return sum, review.ErrReview
	}
	a, err := owned.Reader.Snapshot(ctx, authority.Locator{OperationID: s.Operation, BranchID: s.Branch, Fence: s.Fence}, index)
	if err != nil || a.Binding != c.Binding() {
		return sum, review.ErrReview
	}
	matched := false
	for _, r := range routes {
		if r.LogicalTopic == a.Reference.LogicalTopic && r.PhysicalTopic == a.Reference.PhysicalTopic && r.Revision == a.Reference.RouteRevision {
			matched = true
		}
	}
	if !matched || ctx.Err() != nil {
		return sum, review.ErrReview
	}
	r, err := review.New(a, i, review.Inputs{SourceSHA: in.SourceSHA, BinarySHA: in.BinarySHA, SourceBundleSHA: source, ConfigSHA: in.Config.SHA256, ManifestSHA: in.Manifest.SHA256, ExportSHA: in.Export.SHA256, DataOwner: s.DataOwner, RecoveryOwner: s.RecoveryOwner, Now: now})
	if err != nil {
		return sum, review.ErrReview
	}
	sum, err = review.Write(in.Output, r)
	if err != nil || ctx.Err() != nil {
		return [32]byte{}, review.ErrReview
	}
	return sum, nil
}
