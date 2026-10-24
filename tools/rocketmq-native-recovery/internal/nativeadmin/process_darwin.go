//go:build darwin

package nativeadmin

import "syscall"

// macOS is only used for pure child/process contracts. Real execution and the
// existing coordinator's execute command require Linux and its owned cgroup.
func childAttributes() *syscall.SysProcAttr { return &syscall.SysProcAttr{Setpgid: true} }
