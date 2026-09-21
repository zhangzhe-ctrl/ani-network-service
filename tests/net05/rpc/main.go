// NET-05 supplemental client for the existing internal attachment contract.
package main

import (
	"context"
	"encoding/json"
	"io"
	"os"
	"time"

	networkv1 "github.com/zhangzhe-ctrl/ani-resource-service/api/network/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/reflect/protoreflect"
	"google.golang.org/protobuf/types/dynamicpb"
)

func main() {
	method := os.Args[2]
	service := networkv1.File_network_v1_network_proto.Services().ByName("NetworkService")
	if method == "GetSubmission" {
		service = networkv1.File_network_v1_network_proto.Services().ByName("InstanceNetworkConsumerService")
	}
	descriptor := service.Methods().ByName(protoreflect.Name(method))
	if descriptor == nil {
		panic("unknown fixed method")
	}
	input, _ := io.ReadAll(io.LimitReader(os.Stdin, 32768))
	request, response := dynamicpb.NewMessage(descriptor.Input()), dynamicpb.NewMessage(descriptor.Output())
	if err := protojson.Unmarshal(input, request); err != nil {
		panic(err)
	}
	connection, err := grpc.NewClient(os.Args[1], grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		panic(err)
	}
	defer connection.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	err = connection.Invoke(ctx, "/"+string(service.FullName())+"/"+method, request, response)
	output := map[string]any{"code": status.Code(err).String()}
	if err != nil {
		output["error"] = status.Convert(err).Message()
	} else {
		encoded, e := protojson.MarshalOptions{UseProtoNames: true, EmitUnpopulated: true}.Marshal(response)
		if e != nil {
			panic(e)
		}
		output["response"] = json.RawMessage(encoded)
	}
	json.NewEncoder(os.Stdout).Encode(output)
}
