//go:build !linux && !darwin

package vmk

import (
	"io"
	"os"
	"os/signal"
)

// GetTerminalSize returns the standard 36x124 TUI geometry on non-POSIX platforms (e.g. Windows).
func GetTerminalSize(_ io.Writer) (int, int) {
	return DefaultTUIRows, DefaultTUICols
}

// EnableRawTerminal is a cross-platform fallback on platforms without POSIX termios ioctls;
// ReadNextKeyEvent reads directly from os.Stdin without POSIX syscall.Syscall.
func EnableRawTerminal(_ uintptr) (func(), error) {
	return func() {}, nil
}

func notifyTermSignals(ch chan<- os.Signal) {
	signal.Notify(ch, os.Interrupt)
}

func tryFlockExclusive(_ uintptr) error {
	return nil
}

func unlockFlock(_ uintptr) {}
