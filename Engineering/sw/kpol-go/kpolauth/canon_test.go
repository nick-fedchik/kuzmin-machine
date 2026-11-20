package kpolauth

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
)

// Canonical serializers shared with testdata/gen_kpolauth_golden.py: strings
// are hex-coded UTF-8, nodes are S-expressions with all spans.

func hx(s string) string { return hex.EncodeToString([]byte(s)) }

func shaHex(b []byte) string {
	sum := sha256.Sum256(b)
	return hex.EncodeToString(sum[:])
}

func shaStr(s string) string { return shaHex([]byte(s)) }

func spanVal(sp Span) string {
	return fmt.Sprintf("%d,%d,%d,%d,%d,%d,%d,%d",
		sp.Line, sp.Column, sp.Offset, sp.Length, sp.EndLine, sp.EndColumn, sp.ByteOffset, sp.ByteEnd)
}

func spanPtrS(sp *Span) string {
	if sp == nil {
		return "-"
	}
	return spanVal(*sp)
}

func tokS(t Token) string {
	return fmt.Sprintf("T(%s,%s,%s)", t.Kind, hx(t.Value), spanVal(t.Span))
}

func nodeS(n Node) string {
	name, sp := n.CSTName(), spanVal(n.Span())
	switch n := n.(type) {
	case *Identifier:
		return fmt.Sprintf("(%s %s %s)", name, sp, tokS(n.Token))
	case *Literal:
		return fmt.Sprintf("(%s %s %s)", name, sp, tokS(n.Token))
	case *Uninit:
		return fmt.Sprintf("(%s %s %s)", name, sp, tokS(n.Token))
	case *Param:
		return fmt.Sprintf("(%s %s %s %s)", name, sp, tokS(n.AtToken), nodeS(n.Target))
	case *BracketGroup:
		elems := make([]string, len(n.Elements))
		for i, e := range n.Elements {
			elems[i] = nodeS(e)
		}
		commas := make([]string, len(n.CommaTokens))
		for i, c := range n.CommaTokens {
			commas[i] = tokS(c)
		}
		stub := 0
		if n.HasStubBrackets {
			stub = 1
		}
		return fmt.Sprintf("(%s %s %s %s %s %d [%s] [%s])", name, sp, tokS(n.OpenToken), tokS(n.CloseToken),
			n.Kind, stub, strings.Join(elems, " "), strings.Join(commas, " "))
	case *Construct:
		return fmt.Sprintf("(%s %s %s %s)", name, sp, nodeS(n.Name), nodeS(n.Group))
	case *GroupBounds:
		return fmt.Sprintf("(%s %s %s %s %s %s %s %s)", name, sp, nodeS(n.Target), nodeS(n.Group),
			n.MinRaw, n.MaxRaw, n.MinEffective, n.MaxEffective)
	case *DefLayout:
		bits := make([]string, len(n.Bits))
		for i, b := range n.Bits {
			bits[i] = b.String()
		}
		return fmt.Sprintf("(%s %s %s %s [%s] %s)", name, sp, nodeS(n.Keyword), nodeS(n.Group),
			strings.Join(bits, ","), n.BitOrder)
	case *SubscriptionSeq:
		return fmt.Sprintf("(%s %s %s %s %s)", name, sp, nodeS(n.Left), tokS(n.DotToken), nodeS(n.Right))
	case *Assignment:
		return fmt.Sprintf("(%s %s %s %s %s)", name, sp, nodeS(n.Target), tokS(n.OpToken), nodeS(n.Value))
	case *BinaryExpr:
		return fmt.Sprintf("(%s %s %s %s %s)", name, sp, nodeS(n.Left), tokS(n.OpToken), nodeS(n.Right))
	}
	panic("unknown node " + name)
}

func diagS(d Diagnostic) string {
	unc, ref := "-", "-"
	if d.UncertaintyCode != "" {
		unc = d.UncertaintyCode
	}
	if d.SourceRef != "" {
		ref = hx(d.SourceRef)
	}
	return fmt.Sprintf("D(%s,%s,%s,%s,%s,%s)", d.Code, d.Severity, hx(d.Message), spanPtrS(d.Span), unc, ref)
}

// parseCanon is the canonical form of a Parse result.
func parseCanon(prog *Program, err error) string {
	if err != nil {
		e, ok := err.(*Error)
		if !ok || e.Diagnostic == nil {
			return "X|" + err.Error()
		}
		return "E|" + diagS(*e.Diagnostic)
	}
	items := make([]string, len(prog.Items))
	for i, n := range prog.Items {
		items[i] = nodeS(n)
	}
	diags := make([]string, len(prog.Diagnostics))
	for i, d := range prog.Diagnostics {
		diags[i] = diagS(d)
	}
	return fmt.Sprintf("K|%d|%s|%s", len(prog.Items), strings.Join(items, ";"), strings.Join(diags, ";"))
}

// lowerCanon is the canonical form of a Lower result.
func lowerCanon(art *Artifact, err error) string {
	if err != nil {
		e, ok := err.(*Error)
		if !ok {
			return "X|" + err.Error()
		}
		return fmt.Sprintf("E|%s|%s|%s", e.Code, hx(e.Msg), spanPtrS(e.Span))
	}
	doc, _ := art.DoGoJSON()
	return fmt.Sprintf("K|%s|%s", shaHex(doc), shaHex(art.BRAMImage()))
}
