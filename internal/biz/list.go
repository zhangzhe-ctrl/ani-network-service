package biz

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"
)

type ListVPCs struct {
	TenantID, Name, State, Cursor string
	Limit                         int
}

type VPCPage struct {
	Items      []VPC
	NextCursor string
}

type VPCFilter struct {
	Name, State, AfterID string
	AfterCreatedAt       time.Time
	Limit                int32
}

type vpcCursor struct {
	Version     int
	Kind        string
	TenantID    string
	Name, State string
	ID          string
	CreatedAt   time.Time
}

func (n *Network) ListVPCs(ctx context.Context, request ListVPCs) (VPCPage, error) {
	tenant, err := ParseTenant(request.TenantID)
	if err != nil {
		return VPCPage{}, err
	}
	if request.Limit == 0 {
		request.Limit = 20
	}
	if request.Limit < 1 || request.Limit > 100 {
		return VPCPage{}, Fail(InvalidArgument, "limit must be within 1..100")
	}
	request.Name = strings.TrimSpace(request.Name)
	if !utf8.ValidString(request.Name) || utf8.RuneCountInString(request.Name) > 128 {
		return VPCPage{}, Fail(InvalidArgument, "invalid name filter")
	}
	for _, value := range request.Name {
		if unicode.IsControl(value) {
			return VPCPage{}, Fail(InvalidArgument, "invalid name filter")
		}
	}
	switch ResourceState(request.State) {
	case "", Provisioning, Available, Degraded, Failed, Deleting, Deleted:
	default:
		return VPCPage{}, Fail(InvalidArgument, "invalid state filter")
	}
	filter := VPCFilter{Name: request.Name, State: request.State, Limit: int32(request.Limit + 1)}
	if request.Cursor != "" {
		cursor, err := n.decodeCursor(request.Cursor)
		if err != nil || cursor.Version != 1 || cursor.Kind != "vpc" ||
			cursor.TenantID != tenant || cursor.Name != request.Name || cursor.State != request.State ||
			!validVPCID(cursor.ID) || cursor.CreatedAt.IsZero() {
			return VPCPage{}, Fail(InvalidCursor, "cursor does not match this query")
		}
		filter.AfterCreatedAt, filter.AfterID = cursor.CreatedAt, cursor.ID
	}
	rows, err := n.repository.ListVPCs(ctx, tenant, filter)
	if err != nil {
		return VPCPage{}, err
	}
	page := VPCPage{Items: make([]VPC, 0, request.Limit)}
	for index, value := range rows {
		if index == request.Limit {
			last := rows[index-1]
			page.NextCursor = n.encodeCursor(vpcCursor{
				Version: 1, Kind: "vpc", TenantID: tenant, Name: request.Name, State: request.State,
				ID: last.ID, CreatedAt: last.CreatedAt,
			})
			break
		}
		page.Items = append(page.Items, n.observation(value))
	}
	return page, nil
}

func (n *Network) encodeCursor(cursor vpcCursor) string {
	body, _ := json.Marshal(cursor)
	mac := hmac.New(sha256.New, n.cursorKey)
	mac.Write(body)
	return base64.RawURLEncoding.EncodeToString(body) + "." + base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}

func (n *Network) decodeCursor(value string) (vpcCursor, error) {
	var cursor vpcCursor
	if len(value) > 2048 {
		return cursor, Fail(InvalidCursor, "cursor too long")
	}
	left, right, ok := strings.Cut(value, ".")
	if !ok {
		return cursor, Fail(InvalidCursor, "invalid cursor")
	}
	body, err := base64.RawURLEncoding.DecodeString(left)
	if err != nil || base64.RawURLEncoding.EncodeToString(body) != left {
		return cursor, Fail(InvalidCursor, "invalid cursor")
	}
	signature, err := base64.RawURLEncoding.DecodeString(right)
	if err != nil || base64.RawURLEncoding.EncodeToString(signature) != right {
		return cursor, Fail(InvalidCursor, "invalid cursor")
	}
	mac := hmac.New(sha256.New, n.cursorKey)
	mac.Write(body)
	if !hmac.Equal(signature, mac.Sum(nil)) || json.Unmarshal(body, &cursor) != nil {
		return cursor, Fail(InvalidCursor, "invalid cursor")
	}
	return cursor, nil
}
