package server

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"os"
	"strconv"
	"strings"

	"github.com/google/uuid"
	networkv1 "github.com/zhangzhe-ctrl/ani-network-service/api/network/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/peer"
	"google.golang.org/grpc/status"
)

const GovernanceSAN = "ani-governance"
const GetVPCMethod = "/network.v1.NetworkService/GetVPC"

// GovernanceTLS requires a private CA, a server certificate and the fixed client SAN.
func GovernanceTLS(caFile, certFile, keyFile string) (*tls.Config, error) {
	ca, err := os.ReadFile(caFile)
	if err != nil {
		return nil, fmt.Errorf("read governance CA: %w", err)
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(ca) {
		return nil, fmt.Errorf("governance CA contains no certificates")
	}
	cert, err := tls.LoadX509KeyPair(certFile, keyFile)
	if err != nil {
		return nil, fmt.Errorf("load network server certificate: %w", err)
	}
	leaf, err := x509.ParseCertificate(cert.Certificate[0])
	if err != nil {
		return nil, err
	}
	if !exactDNS(leaf, "ani-network-service") {
		return nil, fmt.Errorf("network server certificate requires exact DNS SAN ani-network-service")
	}
	return &tls.Config{MinVersion: tls.VersionTLS13, Certificates: []tls.Certificate{cert}, ClientCAs: roots, ClientAuth: tls.RequireAndVerifyClientCert,
		VerifyConnection: func(cs tls.ConnectionState) error {
			if len(cs.VerifiedChains) == 0 || len(cs.PeerCertificates) == 0 || !exactDNS(cs.PeerCertificates[0], GovernanceSAN) {
				return fmt.Errorf("untrusted governance service identity")
			}
			return nil
		}}, nil
}

func exactDNS(cert *x509.Certificate, name string) bool {
	for _, dns := range cert.DNSNames {
		if dns == name {
			return true
		}
	}
	return false
}

// This identity is asserted by the authenticated Governance workload, not IAM.
type governancePrincipal struct{ TenantID, Actor, RequestID, Workload string }

type GovernanceResolver struct{}

func (GovernanceResolver) Resolve(ctx context.Context) (governancePrincipal, error) {
	denied := status.Error(codes.Unauthenticated, "trusted governance identity required")
	p, ok := peer.FromContext(ctx)
	if !ok {
		return governancePrincipal{}, denied
	}
	ti, ok := p.AuthInfo.(credentials.TLSInfo)
	if !ok || len(ti.State.VerifiedChains) == 0 || len(ti.State.PeerCertificates) == 0 || !exactDNS(ti.State.PeerCertificates[0], GovernanceSAN) {
		return governancePrincipal{}, denied
	}
	md, ok := metadata.FromIncomingContext(ctx)
	if !ok {
		return governancePrincipal{}, denied
	}
	value := func(key string) string {
		vals := md.Get(key)
		if len(vals) != 1 {
			return ""
		}
		return vals[0]
	}
	tenant, actor, request := value("x-ani-tenant-id"), value("x-ani-actor"), value("x-ani-request-id")
	validUUID := func(v string) bool { id, err := uuid.Parse(v); return err == nil && id != uuid.Nil && id.String() == v }
	idText := strings.TrimPrefix(actor, "governance:user:")
	id, err := strconv.ParseUint(idText, 10, 32)
	if !validUUID(tenant) || !validUUID(request) || err != nil || id == 0 || actor != "governance:user:"+strconv.FormatUint(id, 10) {
		return governancePrincipal{}, denied
	}
	return governancePrincipal{TenantID: tenant, Actor: actor, RequestID: request, Workload: GovernanceSAN}, nil
}

// GovernanceUnary admits one read method before any business handler or SQL runs.
func GovernanceUnary() grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, next grpc.UnaryHandler) (any, error) {
		p, err := (GovernanceResolver{}).Resolve(ctx)
		if err != nil {
			return nil, err
		}
		if info.FullMethod != GetVPCMethod {
			return nil, status.Error(codes.PermissionDenied, "governance credential only permits GetVPC")
		}
		r, ok := req.(*networkv1.GetVPCRequest)
		if !ok || r == nil || r.TenantId != p.TenantID {
			return nil, status.Error(codes.PermissionDenied, "request tenant differs from authenticated governance scope")
		}
		return next(ctx, req)
	}
}

func DenyVPCStreams(_ any, _ grpc.ServerStream, _ *grpc.StreamServerInfo, _ grpc.StreamHandler) error {
	return status.Error(codes.PermissionDenied, "vpc-read does not permit streaming RPCs")
}
