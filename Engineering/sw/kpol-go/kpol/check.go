package kpol

import (
	"sort"
	"strings"
)

// triggerEvent returns the event a rule reacts to; "change" for rules over
// state changes (a rule with a non-empty Watch list and no Event is treated
// the same way).
func (r Rule) triggerEvent() string {
	if r.Event == "" && len(r.Watch) > 0 {
		return "change"
	}
	return r.Event
}

// Check performs the static semantic checks of KPOL-STA-1..13 (reference:
// check_module). It returns the first violation found, in the order fixed by
// the reference.
func Check(m *Module) error {
	if m == nil {
		return staticErr("module is nil")
	}
	if hasDuplicate(len(m.Events), func(i int) string { return m.Events[i].Name }) {
		return staticErr("duplicate event declaration")
	}
	if hasDuplicate(len(m.States), func(i int) string { return m.States[i].Name }) {
		return staticErr("duplicate state declaration")
	}
	if hasDuplicate(len(m.Rules), func(i int) string { return m.Rules[i].Name }) {
		return staticErr("duplicate rule declaration")
	}

	events := make(map[string]*EventDecl, len(m.Events))
	for i := range m.Events {
		events[m.Events[i].Name] = &m.Events[i]
	}
	stateTypes := make(map[string]ktype, len(m.States))
	for _, s := range m.States {
		stateTypes[s.Name] = asKType(s.Type)
	}

	for _, ev := range m.Events {
		if ev.Name == "change" {
			return staticErr("'change' is reserved for generated state-change events")
		}
		seen := make(map[string]bool, len(ev.Params))
		bad := false
		for _, p := range ev.Params {
			if seen[p.Name] {
				bad = true
			}
			seen[p.Name] = true
			if _, clash := stateTypes[p.Name]; clash {
				bad = true
			}
		}
		if bad {
			return staticErr("duplicate/colliding parameters in event %s", pyRepr(ev.Name))
		}
	}

	initTypes := make(map[string]ktype)
	for _, s := range m.States {
		actual, err := infer(s.Initial, initTypes)
		if err != nil {
			return err
		}
		expected := asKType(s.Type)
		ok, err := compatibleExpr(expected, actual, s.Initial)
		if err != nil {
			return err
		}
		if !ok {
			return staticErr("initial value of %s has type %s, expected %s", pyRepr(s.Name), actual, expected)
		}
		initTypes[s.Name] = expected
	}

	type reqKey struct{ kind, name string }
	seenReq := make(map[reqKey]bool, len(m.Requirements))
	for _, r := range m.Requirements {
		seenReq[reqKey{r.Kind, r.Name}] = true
	}
	if len(seenReq) != len(m.Requirements) {
		return staticErr("duplicate requirement name within a contract kind")
	}
	for _, req := range m.Requirements {
		if req.Event != "" {
			if _, ok := events[req.Event]; !ok {
				return staticErr("requirement %s references unknown event %s", pyRepr(req.Name), pyRepr(req.Event))
			}
		}
		if (req.Kind == KindInvariant || req.Kind == KindGoal) && req.Event != "" {
			return staticErr("%s %s must be a state-only predicate", req.Kind, pyRepr(req.Name))
		}
		if (req.Kind == KindHazard || req.Kind == KindAlert) && req.Event == "" {
			return staticErr("%s %s must be scoped to an event", req.Kind, pyRepr(req.Name))
		}
		if req.Target != "" && req.Kind != KindHazard {
			return staticErr("only Hazard may declare a response target (%s)", pyRepr(req.Name))
		}
		if req.Kind == KindHazard {
			if req.Target == "" {
				return staticErr("Hazard %s must declare a response target", pyRepr(req.Name))
			}
			if t, ok := stateTypes[req.Target]; !ok || t != tBool {
				return staticErr("Hazard %s target must be a declared Bool state", pyRepr(req.Name))
			}
		}
		ctx := contextFor(stateTypes, events, req.Event)
		t, err := infer(req.Expression, ctx)
		if err != nil {
			return err
		}
		if t != tBool {
			return staticErr("%s %s must have type Bool", req.Kind, pyRepr(req.Name))
		}
	}

	covered := make(map[string]bool)
	for _, rule := range m.Rules {
		trig := rule.triggerEvent()
		if trig == "change" {
			if rule.Reject || len(rule.Watch) == 0 {
				return staticErr("invalid change rule %s", pyRepr(rule.Name))
			}
			for _, w := range rule.Watch {
				if _, ok := stateTypes[w]; !ok {
					return staticErr("change rule %s watches unknown state", pyRepr(rule.Name))
				}
			}
		} else if _, ok := events[trig]; !ok {
			return staticErr("rule %s references unknown event %s", pyRepr(rule.Name), pyRepr(trig))
		}
		ctx := contextFor(stateTypes, events, trig)
		t, err := infer(rule.Guard, ctx)
		if err != nil {
			return err
		}
		if t != tBool {
			return staticErr("guard of rule %s must have type Bool", pyRepr(rule.Name))
		}
		for _, a := range rule.Actions {
			expected, ok := stateTypes[a.Name]
			if !ok {
				return staticErr("rule %s writes undeclared state %s", pyRepr(rule.Name), pyRepr(a.Name))
			}
			actual, err := infer(a.Expression, ctx)
			if err != nil {
				return err
			}
			ok, err = compatibleExpr(expected, actual, a.Expression)
			if err != nil {
				return err
			}
			if !ok {
				return staticErr("assignment to %s has type %s, expected %s", pyRepr(a.Name), actual, expected)
			}
		}
		if rule.Covers != "" {
			var matches []Requirement
			for _, req := range m.Requirements {
				if req.Kind == KindHazard && req.Name == rule.Covers {
					matches = append(matches, req)
				}
			}
			if len(matches) != 1 {
				return staticErr("rule %s covers unknown hazard %s", pyRepr(rule.Name), pyRepr(rule.Covers))
			}
			hz := matches[0]
			if hz.Event != trig || !exprEqual(hz.Expression, rule.Guard) {
				return staticErr("rule %s does not exactly implement hazard guard", pyRepr(rule.Name))
			}
			trueWrite := false
			for _, a := range rule.Actions {
				if lit, ok := a.Expression.(BoolLit); ok && lit.V && a.Name == hz.Target {
					trueWrite = true
				}
			}
			if !trueWrite {
				return staticErr("hazard rule %s must set target %s to true", pyRepr(rule.Name), pyRepr(hz.Target))
			}
			covered[hz.Name] = true
		}
	}

	var missing []string
	for _, req := range m.Requirements {
		if req.Kind == KindHazard && !covered[req.Name] {
			missing = append(missing, req.Name)
		}
	}
	if len(missing) > 0 {
		sort.Strings(missing)
		return staticErr("hazards without a covers rule: %s", strings.Join(dedupSorted(missing), ", "))
	}

	for _, item := range m.Proofs {
		switch p := item.(type) {
		case AssertProperty:
			if _, ok := events[p.Event]; !ok {
				return staticErr("assert %s references unknown event %s", pyRepr(p.Name), pyRepr(p.Event))
			}
			ctx := contextFor(stateTypes, events, p.Event)
			t, err := infer(p.Guard, ctx)
			if err != nil {
				return err
			}
			if t != tBool {
				return staticErr("guard of assert %s must have type Bool", pyRepr(p.Name))
			}
			t, err = infer(p.Expectation, ctx)
			if err != nil {
				return err
			}
			if t != tBool {
				return staticErr("expectation of assert %s must have type Bool", pyRepr(p.Name))
			}
		case Scenario:
			if err := checkScenario(p, stateTypes, events); err != nil {
				return err
			}
		}
	}
	return nil
}

func checkScenario(s Scenario, stateTypes map[string]ktype, events map[string]*EventDecl) error {
	for _, item := range s.Items {
		switch it := item.(type) {
		case StepAction:
			decl, ok := events[it.Event]
			if !ok {
				return staticErr("scenario %s references unknown event %s", pyRepr(s.Name), pyRepr(it.Event))
			}
			args := make(map[string]Expr, len(it.Args))
			for _, a := range it.Args {
				args[a.Name] = a.Value
			}
			if len(args) != len(decl.Params) {
				return staticErr("scenario %s step %s arguments do not match event parameters", pyRepr(s.Name), pyRepr(it.Event))
			}
			for _, p := range decl.Params {
				if _, ok := args[p.Name]; !ok {
					return staticErr("scenario %s step %s arguments do not match event parameters", pyRepr(s.Name), pyRepr(it.Event))
				}
			}
			for _, p := range decl.Params {
				expr := args[p.Name]
				at, err := infer(expr, stateTypes)
				if err != nil {
					return err
				}
				pt := asKType(p.Type)
				ok, err := compatibleExpr(pt, at, expr)
				if err != nil {
					return err
				}
				if !ok {
					return staticErr("scenario %s argument %s type %s incompatible with %s", pyRepr(s.Name), pyRepr(p.Name), at, pt)
				}
			}
		case ExpectCheck:
			t, err := infer(it.Expression, stateTypes)
			if err != nil {
				return err
			}
			if t != tBool {
				return staticErr("scenario %s expect expression must have type Bool", pyRepr(s.Name))
			}
		}
	}
	return nil
}

// contextFor builds the typing environment Γ of §5.1: all state types plus the
// parameters of the named event, if any.
func contextFor(states map[string]ktype, events map[string]*EventDecl, event string) map[string]ktype {
	ctx := make(map[string]ktype, len(states)+4)
	for k, v := range states {
		ctx[k] = v
	}
	if ev, ok := events[event]; ok && event != "" {
		for _, p := range ev.Params {
			ctx[p.Name] = asKType(p.Type)
		}
	}
	return ctx
}

func hasDuplicate(n int, name func(int) string) bool {
	seen := make(map[string]bool, n)
	for i := 0; i < n; i++ {
		seen[name(i)] = true
	}
	return len(seen) != n
}

func dedupSorted(s []string) []string {
	out := s[:0:0]
	for i, v := range s {
		if i == 0 || v != s[i-1] {
			out = append(out, v)
		}
	}
	return out
}
