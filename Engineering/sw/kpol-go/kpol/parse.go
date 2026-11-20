package kpol

// Parse lexes, parses and statically checks a KPOL module (reference:
// parse_module): ParseUnchecked followed by Check.
func Parse(src string) (*Module, error) {
	m, err := ParseUnchecked(src)
	if err != nil {
		return nil, err
	}
	if err := Check(m); err != nil {
		return nil, err
	}
	return m, nil
}
