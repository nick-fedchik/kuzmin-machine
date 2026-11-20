package kpol

import "fmt"

// Error is a KPOL source, static, contract, profile or runtime error.
// Code carries the diagnostic prefix defined by the specification (for example
// "B3-SHAPE", "CME2-ACTION"); it may be empty for plain parser/runtime errors,
// whose message text must match the reference implementation. Error() returns
// "<Code>: <Msg>" when Code is set, otherwise Msg.
type Error struct {
	Code string
	Msg  string
}

func (e *Error) Error() string {
	if e.Code == "" {
		return e.Msg
	}
	return fmt.Sprintf("%s: %s", e.Code, e.Msg)
}
