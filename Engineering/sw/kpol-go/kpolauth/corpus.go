package kpolauth

// CorpusExample is one KPOL-AUTH example with its source attribution and the
// expected result (CorpusExample of corpus.py).
type CorpusExample struct {
	ID         string
	Title      string
	SourceText string
	SourceRefs []string
	// ExpectedStatus is "ok" or "fail-closed".
	ExpectedStatus string
	// ExpectedCSTKind is the reference class name of the root node, empty when
	// the example is rejected.
	ExpectedCSTKind     string
	ExpectedDiagnostics []string
	SourceBoundaryNote  string
	InSourceScope       bool
	ShowToAuthor        bool
}

// AuthorCorpus returns the corpus EX-01..EX-18 of the reference (AUTHOR_CORPUS,
// specification Annex A.1).
func AuthorCorpus() []CorpusExample {
	out := make([]CorpusExample, len(corpusData))
	for i, ex := range corpusData {
		ex.SourceRefs = append([]string(nil), ex.SourceRefs...)
		ex.ExpectedDiagnostics = append([]string(nil), ex.ExpectedDiagnostics...)
		out[i] = ex
	}
	return out
}
