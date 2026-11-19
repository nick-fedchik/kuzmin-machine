//go:build public

package vmk

// IsPublicBuild reports whether VMK was compiled with `-tags public` (sim-only standalone build).
const IsPublicBuild = true

func targetFlagUsage() string {
	return "machine target: 'sim' (standalone public VMK)"
}

func validateTarget(target string) error {
	if target != "sim" {
		return &TargetIOError{Target: target, Detail: ErrStandaloneSimOnly}
	}
	return nil
}

// ExecutePYNQSession is disabled in public standalone builds (`-tags public`), returning VMK-TARGET-IO.
func (c *MachineConnection) ExecutePYNQSession(_ []byte, _ []int32, _, _ []string) (map[string]any, error) {
	return nil, &TargetIOError{Target: c.Target, Detail: ErrStandaloneSimOnly}
}
