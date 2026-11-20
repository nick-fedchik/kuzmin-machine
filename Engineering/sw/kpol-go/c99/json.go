package c99

import (
	"fmt"
	"strconv"
	"strings"
)

// jKV and jObj model an insertion-ordered JSON object (Python dict order).
type jKV struct {
	Key string
	Val any
}

type jObj []jKV

// marshalPythonJSON renders v exactly like Python's
// json.dumps(v, indent=2, ensure_ascii=False): two-space indentation,
// "key": value pairs, raw non-ASCII text and insertion-ordered objects.
func marshalPythonJSON(v any) string {
	var b strings.Builder
	writeJSON(&b, v, 0)
	return b.String()
}

func writeJSON(b *strings.Builder, v any, level int) {
	pad := func(n int) { b.WriteString(strings.Repeat("  ", n)) }
	switch x := v.(type) {
	case nil:
		b.WriteString("null")
	case bool:
		b.WriteString(strconv.FormatBool(x))
	case int:
		b.WriteString(strconv.Itoa(x))
	case uint32:
		b.WriteString(strconv.FormatUint(uint64(x), 10))
	case string:
		writeJSONString(b, x)
	case []int:
		items := make([]any, len(x))
		for i, e := range x {
			items[i] = e
		}
		writeJSON(b, items, level)
	case []string:
		items := make([]any, len(x))
		for i, e := range x {
			items[i] = e
		}
		writeJSON(b, items, level)
	case []any:
		if len(x) == 0 {
			b.WriteString("[]")
			return
		}
		b.WriteString("[\n")
		for i, e := range x {
			pad(level + 1)
			writeJSON(b, e, level+1)
			if i < len(x)-1 {
				b.WriteString(",")
			}
			b.WriteString("\n")
		}
		pad(level)
		b.WriteString("]")
	case jObj:
		if len(x) == 0 {
			b.WriteString("{}")
			return
		}
		b.WriteString("{\n")
		for i, kv := range x {
			pad(level + 1)
			writeJSONString(b, kv.Key)
			b.WriteString(": ")
			writeJSON(b, kv.Val, level+1)
			if i < len(x)-1 {
				b.WriteString(",")
			}
			b.WriteString("\n")
		}
		pad(level)
		b.WriteString("}")
	default:
		panic(fmt.Sprintf("c99: unsupported JSON value %T", v))
	}
}

func writeJSONString(b *strings.Builder, s string) {
	b.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			b.WriteString(`\"`)
		case '\\':
			b.WriteString(`\\`)
		case '\n':
			b.WriteString(`\n`)
		case '\r':
			b.WriteString(`\r`)
		case '\t':
			b.WriteString(`\t`)
		case '\b':
			b.WriteString(`\b`)
		case '\f':
			b.WriteString(`\f`)
		default:
			if r < 0x20 {
				fmt.Fprintf(b, `\u%04x`, r)
			} else {
				b.WriteRune(r)
			}
		}
	}
	b.WriteByte('"')
}
