package testenv

import (
	"crypto/rand"
	"encoding/base64"
)

// SigningKey creates a fresh test-only value at execution time; no reusable
// credential or signing material is committed with the fixtures.
func SigningKey() string {
	value := make([]byte, 32)
	if _, err := rand.Read(value); err != nil {
		panic(err)
	}
	return base64.StdEncoding.EncodeToString(value)
}
