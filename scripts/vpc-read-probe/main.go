// vpc-read-probe exercises the real deployed mTLS receiver. It neither creates
// VPCs nor asserts that a returned fixture represents working cloud networking.
package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"time"

	"github.com/google/uuid"
	networkv1 "github.com/zhangzhe-ctrl/ani-network-service/api/network/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/encoding/protojson"
)

func main() {
	address := flag.String("address", "", "Network host:port")
	caFile := flag.String("ca", "", "trusted server CA file")
	certFile := flag.String("cert", "", "client certificate file; omit to test missing identity")
	keyFile := flag.String("key", "", "client private key file")
	tenant := flag.String("tenant", "", "RPC tenant UUID")
	headerTenant := flag.String("header-tenant", "", "trusted header tenant UUID; defaults to RPC tenant")
	actor := flag.String("actor", "governance:access-key:1", "delegated actor")
	vpcID := flag.String("vpc", "", "persisted VPC ID")
	want := flag.String("want", "OK", "expected gRPC code")
	flag.Parse()
	if err := run(*address, *caFile, *certFile, *keyFile, *tenant, *headerTenant, *actor, *vpcID, *want); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(address, caFile, certFile, keyFile, tenant, headerTenant, actor, vpcID, want string) error {
	ca, err := os.ReadFile(caFile)
	if err != nil {
		return err
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(ca) {
		return fmt.Errorf("CA file has no certificate")
	}
	cfg := &tls.Config{MinVersion: tls.VersionTLS13, RootCAs: roots, ServerName: "ani-network-service"}
	if certFile != "" || keyFile != "" {
		cert, err := tls.LoadX509KeyPair(certFile, keyFile)
		if err != nil {
			return err
		}
		cfg.Certificates = []tls.Certificate{cert}
	}
	conn, err := grpc.NewClient(address, grpc.WithTransportCredentials(credentials.NewTLS(cfg)))
	if err != nil {
		return err
	}
	defer conn.Close()
	if headerTenant == "" {
		headerTenant = tenant
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	ctx = metadata.NewOutgoingContext(ctx, metadata.Pairs("x-ani-tenant-id", headerTenant, "x-ani-actor", actor, "x-ani-request-id", uuid.NewString()))
	response, callErr := networkv1.NewNetworkServiceClient(conn).GetVPC(ctx, &networkv1.GetVPCRequest{TenantId: tenant, VpcId: vpcID})
	code := status.Code(callErr).String()
	result := map[string]any{"code": code, "expected_code": want, "pass": code == want}
	if callErr == nil {
		body, err := (protojson.MarshalOptions{UseProtoNames: true}).Marshal(response)
		if err != nil {
			return err
		}
		result["response"] = json.RawMessage(body)
	}
	if err := json.NewEncoder(os.Stdout).Encode(result); err != nil {
		return err
	}
	if code != want {
		return fmt.Errorf("gRPC code %s differs from %s", code, want)
	}
	return nil
}
