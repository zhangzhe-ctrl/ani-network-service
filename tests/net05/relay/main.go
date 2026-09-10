// NET-05 byte relay: forwards real TLS without interpreting or inventing replies.
package main

import (
	"io"
	"net"
	"os"
)

func main() {
	l, err := net.Listen("tcp", os.Args[1])
	if err != nil {
		panic(err)
	}
	for {
		c, err := l.Accept()
		if err != nil {
			panic(err)
		}
		go func() {
			defer c.Close()
			u, err := net.Dial("tcp", os.Args[2])
			if err != nil {
				return
			}
			defer u.Close()
			go func() { io.Copy(u, c); u.(*net.TCPConn).CloseWrite() }()
			io.Copy(c, u)
		}()
	}
}
