package kpolauth

import (
	"errors"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

// asKpolCode extracts the code through the *kpol.Error bridge.
func asKpolCode(err error) string {
	var ke *kpol.Error
	if errors.As(err, &ke) {
		return ke.Code
	}
	return ""
}
