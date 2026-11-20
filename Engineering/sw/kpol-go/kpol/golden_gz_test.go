package kpol

import (
	"compress/gzip"
	"io"
	"os"
)

// readGoldenGz reads a gzip-compressed golden file produced by testdata/goldenio.py.
func readGoldenGz(path string) ([]byte, error) {
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
