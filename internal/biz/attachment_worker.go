package biz

import (
	"context"
	"errors"
	"fmt"
	"github.com/google/uuid"
	"slices"
	"time"
)

type AttachmentWork struct {
	Attachment      Attachment
	Plan            PodPrimaryPlan
	Relations       []byte
	ConsumerPodUIDs []string
	ProtocolBlocked bool
	Owner           string
	Epoch           int64
}
type AttachmentProgress struct {
	State                           AttachmentState
	Reason                          Reason
	PodName, PodUID, FinalizationID string
	Relations                       []byte
	Observed, ProtocolBlocked       bool
	NextDelay                       time.Duration
}
type AttachmentWorkRepository interface {
	ClaimAttachment(context.Context, string, time.Duration) (AttachmentWork, bool, error)
	FinishAttachment(context.Context, AttachmentWork, AttachmentProgress) error
}
type AttachmentObservation struct {
	Exists, HasDependencies bool
	PodName, PodUID         string
	Relations               []byte
}
type AttachmentProvider interface {
	ObserveAttachment(context.Context, AttachmentWork) (AttachmentObservation, error)
}
type ConsumerSubmission struct {
	ProtocolVersion                                                        int32
	TenantID, InstanceID, SubmissionID, AttachmentID, ClusterID, Namespace string
	Generation                                                             int64
	State, FinalizationID                                                  string
	PodUIDs, ControllerUIDs                                                []string
	ClosedAt                                                               *time.Time
}
type InstanceConsumer interface {
	GetSubmission(context.Context, Attachment) (ConsumerSubmission, error)
}
type AttachmentWorker struct {
	repository AttachmentWorkRepository
	provider   AttachmentProvider
	consumer   InstanceConsumer
	owner      string
	policy     WorkerPolicy
}

func NewAttachmentWorker(r AttachmentWorkRepository, p AttachmentProvider, c InstanceConsumer, owner string, policy WorkerPolicy) (*AttachmentWorker, error) {
	id, e := uuid.Parse(owner)
	if e != nil || id == uuid.Nil || r == nil || p == nil || c == nil || policy.RequestTimeout <= 0 || policy.Lease < 3*policy.RequestTimeout || policy.ObserveEvery <= 0 {
		return nil, fmt.Errorf("invalid attachment worker dependencies")
	}
	return &AttachmentWorker{r, p, c, owner, policy}, nil
}
func (w *AttachmentWorker) Step(ctx context.Context) (bool, error) {
	ctx, cancel := context.WithTimeout(ctx, w.policy.Lease)
	defer cancel()
	work, found, err := w.repository.ClaimAttachment(ctx, w.owner, w.policy.Lease)
	if err != nil || !found {
		return found, err
	}
	a := work.Attachment
	p := AttachmentProgress{State: a.State, Reason: a.Reason, PodName: a.PodName, PodUID: a.PodUID, FinalizationID: a.FinalizationID, Relations: work.Relations, ProtocolBlocked: work.ProtocolBlocked, NextDelay: w.policy.ObserveEvery}
	call, cancel := context.WithTimeout(ctx, w.policy.RequestTimeout)
	consumer, consumerErr := w.consumer.GetSubmission(call, a)
	cancel()
	if consumerErr == nil && validConsumer(a, consumer) {
		work.ConsumerPodUIDs = consumer.PodUIDs
	}
	call, cancel = context.WithTimeout(ctx, w.policy.RequestTimeout)
	o, observeErr := w.provider.ObserveAttachment(call, work)
	cancel()
	if observeErr != nil {
		p.Reason = providerReason(observeErr)
		if providerKind(observeErr) == ProviderConflict {
			p.Reason = AttachmentProtocol
			p.ProtocolBlocked = true
		}
	} else {
		p.Observed = true
		p.Relations = o.Relations
		if o.Exists && (o.PodUID == "" || (a.PodUID != "" && a.PodUID != o.PodUID) || (a.ConfirmUID != "" && a.ConfirmUID != o.PodUID)) {
			p.Reason = AttachmentProtocol
			p.ProtocolBlocked = true
		} else {
			if o.Exists {
				p.PodName = o.PodName
				p.PodUID = o.PodUID
				if a.State == Reserved {
					p.State = Attached
				}
				p.Reason = ""
			}
			if a.State == Released && (o.Exists || o.HasDependencies) {
				p.Reason = AttachmentProtocol
				p.ProtocolBlocked = true
			}
			if consumerErr != nil {
				if a.State == Releasing || (!o.Exists && a.State == Reserved) {
					p.Reason = ConsumerUnavailable
				}
			} else if !validConsumer(a, consumer) {
				p.Reason = AttachmentProtocol
				p.ProtocolBlocked = true
			} else if consumer.State == "closing" || consumer.State == "closed" {
				if a.State != Released {
					p.State = Releasing
					p.FinalizationID = consumer.FinalizationID
					p.Reason = ConsumerUnclosed
				}
				if (p.PodUID != "" && !slices.Contains(consumer.PodUIDs, p.PodUID)) && consumer.State == "closed" {
					p.Reason = AttachmentProtocol
					p.ProtocolBlocked = true
				} else if consumer.State == "closed" && !o.Exists && !o.HasDependencies && !p.ProtocolBlocked {
					p.State = Released
					p.Reason = ""
				}
				if o.Exists || o.HasDependencies {
					if a.State != Released {
						p.Reason = CleanupPending
					}
				}
			} else if a.State == Releasing {
				p.Reason = ConsumerUnclosed
			} else if !o.Exists && a.State == Attached {
				p.Reason = ProviderMissing
			}
		}
	}
	if p.ProtocolBlocked {
		p.Reason = AttachmentProtocol
	}
	err = w.repository.FinishAttachment(ctx, work, p)
	if errors.Is(err, ErrLeaseLost) {
		err = nil
	}
	return true, err
}
func validConsumer(a Attachment, c ConsumerSubmission) bool {
	if len(c.PodUIDs) > 1 {
		return false
	}
	for _, id := range c.PodUIDs {
		if id == "" {
			return false
		}
	}
	if c.ProtocolVersion != 1 || c.TenantID != a.TenantID || c.InstanceID != a.InstanceID || c.SubmissionID != a.SubmissionID || c.Generation != a.Generation || c.AttachmentID != a.ID || c.ClusterID != a.ClusterID || c.Namespace != a.Namespace {
		return false
	}
	if c.State != "open" && c.State != "closing" && c.State != "closed" {
		return false
	}
	if a.FinalizationID != "" && c.FinalizationID != a.FinalizationID {
		return false
	}
	if c.State != "open" {
		id, e := uuid.Parse(c.FinalizationID)
		if e != nil || id == uuid.Nil {
			return false
		}
	}
	return c.State != "closed" || (c.ClosedAt != nil && !c.ClosedAt.IsZero())
}
