package kpol

import (
	"fmt"
	"sort"
	"strings"
)

// DefaultMaxEvents is the default limit on events processed by one Run call.
const DefaultMaxEvents = 10000

// EventInput is an external event with its named payload.
type EventInput struct {
	Name    string
	Payload map[string]Value
}

// RunResult is the outcome of one Run call (KPOL-DYN-5). The log slices cover
// the whole call, not a single event (D-K4).
type RunResult struct {
	State        map[string]Value
	Hazards      []string
	Alerts       []string
	Rejected     []string
	Diagnostics  []string
	GoalFailures []string
	Steps        int
}

type config struct {
	failClosed bool
	overrides  map[string]Value
	maxEvents  int
}

// Option configures NewInterpreter and Verify.
type Option func(*config)

// WithFailClosedHazards selects whether a Hazard (or unknown Hazard) blocks the
// transaction (default true; the language semantics and Proof use true).
func WithFailClosedHazards(on bool) Option { return func(c *config) { c.failClosed = on } }

// WithOverrides replaces the initial values of the named states (the reference
// parameter `initial`); an unknown name is an error.
func WithOverrides(o map[string]Value) Option { return func(c *config) { c.overrides = o } }

// WithMaxEvents sets the limit on events processed by one Run call
// (default DefaultMaxEvents).
func WithMaxEvents(n int) Option { return func(c *config) { c.maxEvents = n } }

func newConfig(opts []Option) config {
	c := config{failClosed: true, maxEvents: DefaultMaxEvents}
	for _, o := range opts {
		o(&c)
	}
	return c
}

// Interpreter is the reference interpreter of KPOL-DYN-4..8. It is not safe
// for concurrent use.
type Interpreter struct {
	m          *Module
	cfg        config
	events     map[string]*EventDecl
	stateTypes map[string]TypeRef
	watches    [][]string
	pending    bool
	state      map[string]Value
}

// queuedEvent is an entry of the event queue: an external event, or an
// internal change event carrying its observation tuple.
type queuedEvent struct {
	name    string
	payload map[string]Value
	watch   []string
}

func (q queuedEvent) isChange() bool { return q.watch != nil }

func sameTuple(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

// NewInterpreter checks m (KPOL-DYN-4 step 1), computes the initial state σ₀
// and verifies the initial Assumptions and Invariants.
func NewInterpreter(m *Module, opts ...Option) (*Interpreter, error) {
	if err := Check(m); err != nil {
		return nil, err
	}
	in := &Interpreter{
		m:          m,
		cfg:        newConfig(opts),
		events:     make(map[string]*EventDecl, len(m.Events)),
		stateTypes: make(map[string]TypeRef, len(m.States)),
		pending:    true,
	}
	for i := range m.Events {
		in.events[m.Events[i].Name] = &m.Events[i]
	}
	for _, s := range m.States {
		in.stateTypes[s.Name] = s.Type
	}
	for _, r := range m.Rules {
		if r.triggerEvent() != "change" {
			continue
		}
		dup := false
		for _, w := range in.watches {
			if sameTuple(w, r.Watch) {
				dup = true
				break
			}
		}
		if !dup {
			in.watches = append(in.watches, r.Watch)
		}
	}
	var unknown []string
	for name := range in.cfg.overrides {
		if _, ok := in.stateTypes[name]; !ok {
			unknown = append(unknown, name)
		}
	}
	if len(unknown) > 0 {
		sort.Strings(unknown)
		return nil, &Error{Msg: "unknown initial state: " + strings.Join(unknown, ", ")}
	}
	in.state = make(map[string]Value, len(m.States))
	for _, s := range m.States {
		raw, err := eval(s.Initial, in.state)
		if err != nil {
			return nil, err
		}
		if ov, ok := in.cfg.overrides[s.Name]; ok {
			raw = ov
		}
		v, err := normalize(raw, s.Type, false)
		if err != nil {
			return nil, err
		}
		in.state[s.Name] = v
	}
	for _, req := range m.Requirements {
		if (req.Kind != KindAssumption && req.Kind != KindInvariant) || req.Event != "" {
			continue
		}
		v, err := eval(req.Expression, in.state)
		if err != nil {
			return nil, err
		}
		if !isTrue(v) {
			return nil, &Error{Msg: fmt.Sprintf("initial %s %s is not true", req.Kind, pyRepr(req.Name))}
		}
	}
	return in, nil
}

// InitialState returns σ₀ (KPOL-DYN-4 steps 1–2) without checking the initial
// Assumptions and Invariants. The map is keyed by state name.
func InitialState(m *Module) (map[string]Value, error) {
	if err := Check(m); err != nil {
		return nil, err
	}
	state := make(map[string]Value, len(m.States))
	for _, s := range m.States {
		raw, err := eval(s.Initial, state)
		if err != nil {
			return nil, err
		}
		v, err := normalize(raw, s.Type, false)
		if err != nil {
			return nil, err
		}
		state[s.Name] = v
	}
	return state, nil
}

// State returns a copy of the current state σ.
func (in *Interpreter) State() map[string]Value { return copyState(in.state) }

func copyState(s map[string]Value) map[string]Value {
	out := make(map[string]Value, len(s))
	for k, v := range s {
		out[k] = v
	}
	return out
}

func mergeEnv(state, payload map[string]Value) map[string]Value {
	env := make(map[string]Value, len(state)+len(payload))
	for k, v := range state {
		env[k] = v
	}
	for k, v := range payload {
		env[k] = v
	}
	return env
}

// Run processes events, together with the initial change events of the first
// call, until the queue is empty (KPOL-DYN-5). A returned error is a runtime
// error that aborts the whole call; the interpreter state then keeps the
// transactions committed so far.
func (in *Interpreter) Run(events []EventInput) (*RunResult, error) {
	res := &RunResult{
		Hazards: []string{}, Alerts: []string{}, Rejected: []string{},
		Diagnostics: []string{}, GoalFailures: []string{},
	}
	var queue []queuedEvent
	if in.pending {
		in.pending = false
		for _, w := range in.watches {
			queue = append(queue, queuedEvent{name: "change", watch: w})
		}
	}
	for _, e := range events {
		queue = append(queue, queuedEvent{name: e.Name, payload: e.Payload})
	}
	for len(queue) > 0 {
		if res.Steps >= in.cfg.maxEvents {
			return nil, &Error{Msg: fmt.Sprintf("event limit exceeded (%d)", in.cfg.maxEvents)}
		}
		ev := queue[0]
		queue = queue[1:]
		res.Steps++
		if !ev.isChange() && ev.name != "change" {
			if _, ok := in.events[ev.name]; !ok {
				return nil, &Error{Msg: fmt.Sprintf("unknown input event %s", pyRepr(ev.name))}
			}
		}
		payload, err := in.validatePayload(ev)
		if err != nil {
			return nil, err
		}
		if !ev.isChange() {
			env := mergeEnv(in.state, payload)
			reject, err := in.present(ev, env, res)
			if err != nil {
				return nil, err
			}
			if reject {
				if err := in.execute(ev, payload, res, true, &queue); err != nil {
					return nil, err
				}
				continue
			}
		}
		if err := in.execute(ev, payload, res, false, &queue); err != nil {
			return nil, err
		}
	}
	for _, req := range in.m.Requirements {
		if req.Kind != KindGoal {
			continue
		}
		v, err := eval(req.Expression, in.state)
		if err != nil {
			return nil, err
		}
		if !isTrue(v) {
			res.GoalFailures = append(res.GoalFailures, req.Name)
		}
	}
	res.State = copyState(in.state)
	return res, nil
}

// present runs phases A and B of KPOL-DYN-7. reject reports that the event
// must be executed as a rejection (the caller runs TX with rejecting = true).
func (in *Interpreter) present(ev queuedEvent, env map[string]Value, res *RunResult) (reject bool, err error) {
	reqs := in.m.Requirements
	for _, req := range reqs {
		if req.Kind != KindAssumption || req.Event != ev.name {
			continue
		}
		v, err := eval(req.Expression, env)
		if err != nil {
			return false, err
		}
		if isTrue(v) {
			continue
		}
		// Phase A: the input is rejected; hazards and alerts are still observed.
		for _, r := range reqs {
			switch {
			case r.Kind == KindHazard && r.Event == ev.name:
				obs, err := eval(r.Expression, env)
				if err != nil {
					return false, err
				}
				if isTrue(obs) {
					res.Hazards = append(res.Hazards, r.Name)
				} else if IsUnknown(obs) {
					res.Diagnostics = append(res.Diagnostics, "UnknownHazard:"+r.Name)
				}
			case r.Kind == KindAlert && r.Event == ev.name:
				obs, err := eval(r.Expression, env)
				if err != nil {
					return false, err
				}
				if isTrue(obs) {
					res.Alerts = append(res.Alerts, r.Name)
				}
			}
		}
		res.Rejected = append(res.Rejected, "RejectedInput:"+ev.name)
		return true, nil
	}

	// Phase B: hazards (fail-closed interlock) and alerts.
	blocked := false
	for _, r := range reqs {
		switch {
		case r.Kind == KindHazard && r.Event == ev.name:
			obs, err := eval(r.Expression, env)
			if err != nil {
				return false, err
			}
			if isTrue(obs) {
				res.Hazards = append(res.Hazards, r.Name)
				if in.cfg.failClosed {
					blocked = true
					res.Rejected = append(res.Rejected, "RejectedHazard:"+r.Name)
				}
			} else if IsUnknown(obs) {
				res.Diagnostics = append(res.Diagnostics, "UnknownHazard:"+r.Name)
				if in.cfg.failClosed {
					blocked = true
					res.Rejected = append(res.Rejected, "RejectedHazardUnknown:"+r.Name)
				}
			}
		case r.Kind == KindAlert && r.Event == ev.name:
			obs, err := eval(r.Expression, env)
			if err != nil {
				return false, err
			}
			if isTrue(obs) {
				res.Alerts = append(res.Alerts, r.Name)
			} else if IsUnknown(obs) {
				res.Diagnostics = append(res.Diagnostics, "UnknownAlert:"+r.Name)
			}
		}
	}
	return blocked, nil
}

// validatePayload is KPOL-DYN-6.
func (in *Interpreter) validatePayload(ev queuedEvent) (map[string]Value, error) {
	if ev.name == "change" {
		if !ev.isChange() {
			return nil, &Error{Msg: "invalid internal change event"}
		}
		return nil, nil
	}
	decl := in.events[ev.name]
	match := len(ev.payload) == len(decl.Params)
	if match {
		for _, p := range decl.Params {
			if _, ok := ev.payload[p.Name]; !ok {
				match = false
				break
			}
		}
	}
	if !match {
		names := make([]string, len(decl.Params))
		for i, p := range decl.Params {
			names[i] = p.Name
		}
		return nil, &Error{Msg: fmt.Sprintf("payload for %s must contain exactly %s", pyRepr(ev.name), strings.Join(names, ", "))}
	}
	out := make(map[string]Value, len(decl.Params))
	for _, p := range decl.Params {
		v, err := normalize(ev.payload[p.Name], p.Type, true)
		if err != nil {
			return nil, err
		}
		out[p.Name] = v
	}
	return out, nil
}

// execute is TX(ev, π, rejecting) of KPOL-DYN-8: an atomic transaction on a
// snapshot, with invariant checking and change cascade.
func (in *Interpreter) execute(ev queuedEvent, payload map[string]Value, res *RunResult, rejecting bool, queue *[]queuedEvent) error {
	snapshot := copyState(in.state)
	env := mergeEnv(snapshot, payload)
	var selected []Rule
	for _, r := range in.m.Rules {
		if ev.isChange() {
			if r.triggerEvent() == "change" && !r.Reject && sameTuple(r.Watch, ev.watch) {
				selected = append(selected, r)
			}
		} else if r.triggerEvent() == ev.name && r.Reject == rejecting {
			selected = append(selected, r)
		}
	}
	writes := map[string]Value{}
	for _, rule := range selected {
		guard, err := eval(rule.Guard, env)
		if err != nil {
			return err
		}
		if IsUnknown(guard) {
			res.Diagnostics = append(res.Diagnostics, "UnknownGuard:"+rule.Name)
			return nil
		}
		if !isTrue(guard) {
			continue
		}
		for _, a := range rule.Actions {
			v, err := eval(a.Expression, env)
			if err != nil {
				return err
			}
			if IsUnknown(v) {
				res.Diagnostics = append(res.Diagnostics, "UnknownWrite:"+rule.Name+":"+a.Name)
				return nil
			}
			v, err = normalize(v, in.stateTypes[a.Name], false)
			if err != nil {
				return err
			}
			if prev, ok := writes[a.Name]; ok && !Equal(prev, v) {
				res.Diagnostics = append(res.Diagnostics, "ConflictingWrites:"+a.Name)
				return nil
			}
			writes[a.Name] = v
		}
	}

	if rejecting {
		for _, req := range in.m.Requirements {
			if req.Kind != KindHazard || req.Event != ev.name || req.Target == "" {
				continue
			}
			if containsString(res.Hazards, req.Name) {
				if _, ok := writes[req.Target]; !ok {
					writes[req.Target] = Bool(true)
				}
			}
		}
	}

	candidate := copyState(snapshot)
	for k, v := range writes {
		candidate[k] = v
	}
	for _, req := range in.m.Requirements {
		if req.Kind != KindInvariant {
			continue
		}
		v, err := eval(req.Expression, candidate)
		if err != nil {
			return err
		}
		if !isTrue(v) {
			res.Diagnostics = append(res.Diagnostics, "InvariantViolation:"+req.Name)
			return nil
		}
	}

	changed := map[string]bool{}
	for name := range writes {
		if !Equal(candidate[name], snapshot[name]) {
			changed[name] = true
		}
	}
	in.state = candidate
	for _, w := range in.watches {
		for _, s := range w {
			if changed[s] {
				*queue = append(*queue, queuedEvent{name: "change", watch: w})
				break
			}
		}
	}
	return nil
}

func containsString(list []string, s string) bool {
	for _, x := range list {
		if x == s {
			return true
		}
	}
	return false
}
