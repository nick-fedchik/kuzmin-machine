//go:build darwin

package vmk

import (
	"io"
	"os"
	"os/signal"
	"syscall"
	"unsafe"
)

// macOS (Darwin) ioctl constants for raw terminal mode and window size detection.
const (
	ioctlTIOCGETA   uintptr = 0x40487413
	ioctlTIOCSETA   uintptr = 0x80487414
	ioctlTIOCGWINSZ uintptr = 0x40087468
)

type termWinsize struct {
	Row    uint16
	Col    uint16
	Xpixel uint16
	Ypixel uint16
}

// GetTerminalSize queries TIOCGWINSZ on out if it is an *os.File, or returns (DefaultTUIRows, DefaultTUICols).
func GetTerminalSize(out io.Writer) (int, int) {
	f, ok := out.(*os.File)
	if !ok {
		return DefaultTUIRows, DefaultTUICols
	}
	var ws termWinsize
	_, _, errno := syscall.Syscall(
		syscall.SYS_IOCTL,
		f.Fd(),
		ioctlTIOCGWINSZ,
		uintptr(unsafe.Pointer(&ws)),
	)
	if errno != 0 || ws.Row < 20 || ws.Col < 80 {
		return DefaultTUIRows, DefaultTUICols
	}
	return int(ws.Row), int(ws.Col)
}

// EnableRawTerminal switches fd into non-canonical raw keystroke mode via macOS TIOCGETA/TIOCSETA ioctl,
// returning a restore callback that restores the original termios settings.
func EnableRawTerminal(fd uintptr) (func(), error) {
	var orig syscall.Termios
	_, _, errno := syscall.Syscall(
		syscall.SYS_IOCTL,
		fd,
		ioctlTIOCGETA,
		uintptr(unsafe.Pointer(&orig)),
	)
	if errno != 0 {
		return func() {}, errno
	}
	raw := orig
	raw.Iflag &^= syscall.IGNBRK | syscall.BRKINT | syscall.PARMRK | syscall.ISTRIP | syscall.INLCR | syscall.IGNCR | syscall.ICRNL | syscall.IXON
	raw.Lflag &^= syscall.ECHO | syscall.ECHONL | syscall.ICANON | syscall.ISIG | syscall.IEXTEN
	raw.Cflag &^= syscall.CSIZE | syscall.PARENB
	raw.Cflag |= syscall.CS8
	raw.Cc[syscall.VMIN] = 1
	raw.Cc[syscall.VTIME] = 0

	_, _, errno = syscall.Syscall(
		syscall.SYS_IOCTL,
		fd,
		ioctlTIOCSETA,
		uintptr(unsafe.Pointer(&raw)),
	)
	if errno != 0 {
		return func() {}, errno
	}
	restore := func() {
		_, _, _ = syscall.Syscall(
			syscall.SYS_IOCTL,
			fd,
			ioctlTIOCSETA,
			uintptr(unsafe.Pointer(&orig)),
		)
	}
	return restore, nil
}

func notifyTermSignals(ch chan<- os.Signal) {
	signal.Notify(ch, os.Interrupt, syscall.SIGTERM)
}

func tryFlockExclusive(fd uintptr) error {
	return syscall.Flock(int(fd), syscall.LOCK_EX|syscall.LOCK_NB)
}

func unlockFlock(fd uintptr) {
	_ = syscall.Flock(int(fd), syscall.LOCK_UN)
}
