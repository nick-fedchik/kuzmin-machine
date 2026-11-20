package kpolauth

import (
	"bytes"
	"errors"
	"fmt"
	"strconv"
	"unicode/utf8"
)

// DoGoFormat is the "format" value of the Do/Go JSON artifact.
const DoGoFormat = "kpol-auth-dogo-0.1.0"

// DoGoJSON returns the Do/Go artifact as the CLI writes it for
// "--emit-dogo OUT.json": the same keys, key order and two-space indentation as
// json.dumps(payload, ensure_ascii=False, indent=2) + "\n" of the reference.
func (a *Artifact) DoGoJSON() ([]byte, error) {
	if a == nil {
		return nil, errors.New("kpolauth: nil artifact")
	}
	concepts := make([]any, len(a.Concepts))
	for i, c := range a.Concepts {
		concepts[i] = jsonObject{
			{"cid", c.CID}, {"name", c.Name}, {"init_val", c.InitVal}, {"flags", c.Flags},
			{"lower_bound", c.LowerBound}, {"upper_bound", c.UpperBound},
			{"first_sub_idx", c.FirstSubIdx}, {"sub_count", c.SubCount},
		}
	}
	subs := make([]any, len(a.Subscriptions))
	for i, s := range a.Subscriptions {
		subs[i] = jsonObject{
			{"sub_idx", s.SubIdx}, {"owner_cid", s.OwnerCID}, {"target_cid", s.TargetCID},
			{"phase", s.Phase}, {"trigger_mask", s.TriggerMask},
			{"line_start_pc", s.LineStartPC}, {"line_len", s.LineLen},
		}
	}
	code := make([]any, len(a.codeO))
	hex := make([]any, len(a.codeO))
	for i, w := range a.codeO {
		code[i] = w
		hex[i] = fmt.Sprintf("0x%08X", w)
	}
	var buf bytes.Buffer
	writeJSON(&buf, jsonObject{
		{"format", DoGoFormat},
		{"concepts", concepts},
		{"subscriptions", subs},
		{"code_o", code},
		{"code_o_hex", hex},
	}, 0)
	buf.WriteByte('\n')
	return buf.Bytes(), nil
}

type jsonPair struct {
	key   string
	value any
}

// jsonObject is an object with a fixed key order.
type jsonObject []jsonPair

func writeJSON(buf *bytes.Buffer, v any, level int) {
	switch v := v.(type) {
	case nil:
		buf.WriteString("null")
	case *int64:
		if v == nil {
			buf.WriteString("null")
		} else {
			buf.WriteString(strconv.FormatInt(*v, 10))
		}
	case int:
		buf.WriteString(strconv.Itoa(v))
	case int64:
		buf.WriteString(strconv.FormatInt(v, 10))
	case uint32:
		buf.WriteString(strconv.FormatUint(uint64(v), 10))
	case string:
		writeJSONString(buf, v)
	case []any:
		if len(v) == 0 {
			buf.WriteString("[]")
			return
		}
		buf.WriteString("[\n")
		for i, item := range v {
			buf.WriteString(indent(level + 1))
			writeJSON(buf, item, level+1)
			if i < len(v)-1 {
				buf.WriteByte(',')
			}
			buf.WriteByte('\n')
		}
		buf.WriteString(indent(level) + "]")
	case jsonObject:
		buf.WriteString("{\n")
		for i, p := range v {
			buf.WriteString(indent(level + 1))
			writeJSONString(buf, p.key)
			buf.WriteString(": ")
			writeJSON(buf, p.value, level+1)
			if i < len(v)-1 {
				buf.WriteByte(',')
			}
			buf.WriteByte('\n')
		}
		buf.WriteString(indent(level) + "}")
	default:
		panic(fmt.Sprintf("kpolauth: unsupported JSON value %T", v))
	}
}

func indent(level int) string {
	b := make([]byte, 2*level)
	for i := range b {
		b[i] = ' '
	}
	return string(b)
}

// writeJSONString writes s like json.dumps(s, ensure_ascii=False).
func writeJSONString(buf *bytes.Buffer, s string) {
	buf.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			buf.WriteString(`\"`)
		case '\\':
			buf.WriteString(`\\`)
		case '\n':
			buf.WriteString(`\n`)
		case '\r':
			buf.WriteString(`\r`)
		case '\t':
			buf.WriteString(`\t`)
		case '\b':
			buf.WriteString(`\b`)
		case '\f':
			buf.WriteString(`\f`)
		default:
			if r < 0x20 {
				fmt.Fprintf(buf, `\u%04x`, r)
			} else {
				var enc [utf8.UTFMax]byte
				buf.Write(enc[:utf8.EncodeRune(enc[:], r)])
			}
		}
	}
	buf.WriteByte('"')
}
