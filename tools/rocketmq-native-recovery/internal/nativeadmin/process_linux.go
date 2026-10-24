//go:build linux

package nativeadmin

import "syscall"

func childAttributes() *syscall.SysProcAttr {
	// The reviewed production runner execs Java directly. Its owned group is
	// also killed if this helper is terminated by the outer coordinator. The
	// final helper container/cgroup must be independently drained at T29.
	return &syscall.SysProcAttr{Setpgid: true, Pdeathsig: syscall.SIGKILL}
}
