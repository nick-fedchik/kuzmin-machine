package kpolauth

import (
	"compress/gzip"
	"io"
	"os"
	"strings"
)

// readGoldenFile reads a golden file; names ending in ".gz" are gzip-compressed
// (testdata/goldenio.py), anything else is plain JSON.
func readGoldenFile(path string) ([]byte, error) {
	if !strings.HasSuffix(path, ".gz") {
		return os.ReadFile(path)
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	zr, err := gzip.NewReader(f)
	if err != nil {
		return nil, err
	}
	defer zr.Close()
	return io.ReadAll(zr)
}
