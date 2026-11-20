package c99

import (
	"strings"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

// EmitC99 emits the self-contained MISRA-oriented C99 safety module for a
// descriptor table (emit_c99_safety_module). The table must be a strict DAG;
// unless Options.AllowUnverified is set, the module is certified with Z3
// before it is returned. Failures are *kpol.Error values with code
// "C99-Z3-REJECTED" (cycle, range, failed certificate) or "C99-SHAPE", or
// ErrZ3Required when Z3 is not installed (fail-closed).
func EmitC99(descriptors []kpol.Descriptor, opts Options) (string, error) {
	src, _, err := EmitC99WithCertificate(descriptors, opts)
	return src, err
}

// EmitC99FromImage is EmitC99 for a 1024-byte BRAM image.
func EmitC99FromImage(image []byte, opts Options) (string, error) {
	src, _, err := EmitC99FromImageWithCertificate(image, opts)
	return src, err
}

// EmitC99WithCertificate is EmitC99 that also returns the Z3 certificate for
// exactly the emitted text: the pair the reference CLI writes for
// --emit-c99 / --emit-z3-cert (emit followed by prove on the emitted source).
// With Options.Certificate set, that certificate is returned unchanged.
func EmitC99WithCertificate(descriptors []kpol.Descriptor, opts Options) (string, *Certificate, error) {
	descs, err := NormalizeDescriptors(descriptors, opts)
	if err != nil {
		return "", nil, err
	}
	return emit(descs, opts)
}

// EmitC99FromImageWithCertificate is EmitC99WithCertificate for a 1024-byte BRAM image.
func EmitC99FromImageWithCertificate(image []byte, opts Options) (string, *Certificate, error) {
	descs, err := NormalizeImage(image, opts)
	if err != nil {
		return "", nil, err
	}
	return emit(descs, opts)
}

func emit(descs []kpol.Descriptor, opts Options) (string, *Certificate, error) {
	imageSHA := tableSHA256(descs)
	active, edges := ExtractActiveCIDsAndEdges(descs)

	topo, err := ComputeTopologicalOrder(active, edges)
	if err != nil {
		if !opts.AllowUnverified {
			return "", nil, &kpol.Error{Code: "C99-Z3-REJECTED", Msg: err.Error()}
		}
		topo = append([]int(nil), active...)
	}

	sv, err := newSolver(opts)
	if err != nil {
		return "", nil, err
	}
	version, err := sv.version()
	if err != nil {
		return "", nil, err
	}

	source := renderC99(descs, topo, opts.moduleName(), imageSHA, defaultVerdictLabel, defaultSolverLabel)

	cert := opts.Certificate
	if cert == nil {
		cert, err = prove(sv, version, descs, source, opts)
		if err != nil {
			return "", nil, err
		}
	}
	if !opts.AllowUnverified && !cert.Passed {
		reasons := "unknown Z3 failure"
		if len(cert.Failures) > 0 {
			reasons = strings.Join(cert.Failures, "; ")
		}
		return "", nil, &kpol.Error{Code: "C99-Z3-REJECTED", Msg: reasons}
	}
	return source, cert, nil
}
