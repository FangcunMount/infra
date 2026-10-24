// Package execution composes the reviewed request, real coordinator barrier,
// check-only SDK, native physical recheck and exact governance primitives. It
// grants no application retry, business write or automatic admission reopening.
package execution

import (
	"time"

	"fangcunmount.infra/rocketmq-native-recovery/internal/barrier"
	"fangcunmount.infra/rocketmq-native-recovery/internal/connection"
	"fangcunmount.infra/rocketmq-native-recovery/internal/preview"
	"fangcunmount.infra/rocketmq-native-recovery/internal/review"
	"github.com/FangcunMount/reliable-messaging/transport/rocketmq"
)

type Input struct {
	Config, Manifest, Export, Request, Approval preview.File
	Receipt                                     preview.File
	Barrier                                     barrier.Context
	SourceSHA                                   string
	BinarySHA                                   [32]byte
}
type reviewed struct {
	request review.Request
	config  connection.Config
	routes  []rocketmq.TransactionRoute
	issued  barrier.Issued
}

func load(in Input, action string, now time.Time) (out reviewed, err error) {
	r, err := review.Load(in.Request.Path, in.Request.SHA256, now)
	if action == "verify" {
		r, err = review.LoadRecorded(in.Request.Path, in.Request.SHA256, now)
	}
	if err != nil || r.SourceSHA != in.SourceSHA || r.BinarySHA != review.Hex(in.BinarySHA) || r.ConfigSHA != review.Hex(in.Config.SHA256) || r.ManifestSHA != review.Hex(in.Manifest.SHA256) || r.ExportSHA != review.Hex(in.Export.SHA256) {
		return out, review.ErrReview
	}
	c, err := connection.Load(in.Config.Path, in.Config.SHA256)
	if err != nil {
		return out, review.ErrReview
	}
	s, err := r.Snapshot.Authority()
	if err != nil || s.Binding != c.Binding() {
		return out, review.ErrReview
	}
	routes, err := connection.Routes(in.Manifest.Path, in.Manifest.SHA256, c.Owner)
	if err != nil {
		return out, review.ErrReview
	}
	matched := false
	for _, route := range routes {
		if route.PhysicalTopic == s.Reference.PhysicalTopic && route.LogicalTopic == s.Reference.LogicalTopic && route.Revision == s.Reference.RouteRevision {
			matched = true
		}
	}
	if !matched {
		return out, review.ErrReview
	}
	if _, err = review.SelectExport(in.Export.Path, in.Export.SHA256, s.Notice.IndexSHA256); err != nil {
		return out, review.ErrReview
	}
	reviewAt := now
	if action == "verify" {
		reviewAt = r.CreatedAt
	}
	if review.Approve(in.Approval.Path, in.Approval.SHA256, r, in.Request.SHA256, in.Receipt.SHA256, in.Barrier.BindingSHA256, action, reviewAt) != nil {
		return out, review.ErrReview
	}
	issued, err := barrier.RequireIssued(in.Barrier)
	if err != nil || !issued.Matches(r.DataOwner, r.RecoveryOwner, r.SourceBundleSHA) {
		return out, review.ErrReview
	}
	return reviewed{r, c, routes, issued}, nil
}

func stillIssued(in Input, r review.Request) error {
	if r.Validate(time.Now().UTC()) != nil {
		return review.ErrReview
	}
	return issuedForRecordedRead(in, r)
}

func issuedForRecordedRead(in Input, r review.Request) error {
	p, err := barrier.RequireIssued(in.Barrier)
	if err != nil || !p.Matches(r.DataOwner, r.RecoveryOwner, r.SourceBundleSHA) {
		return review.ErrReview
	}
	return nil
}
