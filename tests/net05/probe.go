// NET-05 ordinary-container fixture. No cluster credentials or network setup.
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"
)

func main() {
	if len(os.Args) > 1 && os.Args[1] == "request" {
		client := http.Client{Timeout: 3 * time.Second, Transport: &http.Transport{Proxy: nil}}
		resp, err := client.Get(os.Args[2])
		if err != nil {
			fmt.Println(err)
			os.Exit(2)
		}
		defer resp.Body.Close()
		fmt.Println("status", resp.StatusCode)
		io.Copy(os.Stdout, io.LimitReader(resp.Body, 4096))
		return
	}
	if len(os.Args) > 1 && os.Args[1] == "inspect" {
		addresses, _ := net.InterfaceAddrs()
		routes, _ := os.ReadFile("/proc/net/route")
		json.NewEncoder(os.Stdout).Encode(map[string]any{"addresses": addresses, "routes": string(routes)})
		return
	}
	port := os.Getenv("NET05_PORT")
	if port == "" {
		port = "18080"
	}
	host, _ := os.Hostname()
	if seconds, _ := strconv.Atoi(os.Getenv("NET05_TERMINATION_DELAY")); seconds > 0 && seconds <= 20 {
		stopping := make(chan os.Signal, 1)
		signal.Notify(stopping, syscall.SIGTERM)
		go func() {
			<-stopping
			time.Sleep(time.Duration(seconds) * time.Second)
			os.Exit(0)
		}()
	}
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{"fixture_id": os.Getenv("NET05_ID"),
			"instance_id": os.Getenv("ANI_WORKLOAD_ID"), "hostname": host, "nonce": r.URL.Query().Get("nonce"), "port": port})
	})
	if err := http.ListenAndServe(":"+port, nil); err != nil {
		panic(err)
	}
}
