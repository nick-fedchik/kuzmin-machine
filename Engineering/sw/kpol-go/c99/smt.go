package c99

import "strings"

// smtDefs renders the QF_BV definitions of the CFG-P RTL specification
// (*_rtl) and of the parsed C99 implementation (*_c99). Operators and
// sign-extension choices are taken from the parsed C99 text, which is what
// makes mutations of the C source observable to Z3.
func smtDefs(p *ParsedModule) string {
	eqSMT := "(not (= ev_param operand))"
	if p.PredEqOp == "==" {
		eqSMT = "(= ev_param operand)"
	}
	neqSMT := "(= ev_param operand)"
	if p.PredNeqOp == "!=" {
		neqSMT = "(not (= ev_param operand))"
	}
	gtMap := map[string]string{
		">":  "(bvsgt ev_param operand)",
		">=": "(bvsge ev_param operand)",
		"<":  "(bvslt ev_param operand)",
		"<=": "(bvsle ev_param operand)",
		"==": "(= ev_param operand)",
	}
	ext := "zero_extend"
	if p.RangeSext {
		ext = "sign_extend"
	}
	loExt := "((_ " + ext + " 16) ((_ extract 15 0) operand))"
	hiExt := "((_ " + ext + " 16) ((_ extract 31 16) operand))"
	rngLo := "(bvsgt ev_param " + loExt + ")"
	if p.RangeLoOp == ">=" {
		rngLo = "(bvsge ev_param " + loExt + ")"
	}
	rngHi := "(bvslt ev_param " + hiExt + ")"
	if p.RangeHiOp == "<=" {
		rngHi = "(bvsle ev_param " + hiExt + ")"
	}

	pick := func(op, whenEq, a, b string) string {
		if op == whenEq {
			return a
		}
		return b
	}
	incSMT := pick(p.ActIncOp, "+", "(bvadd cur_state #x00000001)", "(bvsub cur_state #x00000001)")
	decSMT := pick(p.ActDecOp, "-", "(bvsub cur_state #x00000001)", "(bvadd cur_state #x00000001)")
	addSMT := pick(p.ActAddOp, "+", "(bvadd cur_state operand)", "(bvsub cur_state operand)")
	subSMT := pick(p.ActSubOp, "-", "(bvsub cur_state operand)", "(bvadd cur_state operand)")
	subOvfCond1 := pick(p.SubOvfXorOp, "!=",
		"(not (= (bvand (bvxor cur_state operand) #x80000000) #x00000000))",
		"(= (bvand (bvxor cur_state operand) #x80000000) #x00000000)")

	invParts := []string{"true"}
	if p.InvariantChecksOverflow {
		invParts = append(invParts, "(not ovf_c99)")
	}
	if p.InvariantChecksNonneg {
		invParts = append(invParts, "(= (bvand cand_c99 #x80000000) #x00000000)")
	}
	invTrueSMT := "(and " + strings.Join(invParts, " ") + ")"
	invOKSMT := "true"
	if p.CommitChecksInvariant {
		invOKSMT = "(and inv_known_c99 " + invTrueSMT + ")"
	}
	selfSupSMT := "true"
	if p.HasSelfSuppress {
		selfSupSMT = "(not (= ((_ extract 5 0) subscriber_cid) cid))"
	}

	r := strings.NewReplacer(
		"@EQ@", eqSMT,
		"@NEQ@", neqSMT,
		"@GT@", gtMap[p.PredGtOp],
		"@LT@", ltMapSMT(p.PredLtOp),
		"@RNG_LO@", rngLo,
		"@RNG_HI@", rngHi,
		"@INC@", incSMT,
		"@DEC@", decSMT,
		"@ADD@", addSMT,
		"@SUB@", subSMT,
		"@SUB_OVF1@", subOvfCond1,
		"@INV_OK@", invOKSMT,
		"@SELF_SUP@", selfSupSMT,
	)
	return r.Replace(smtTemplate)
}

func ltMapSMT(op string) string {
	switch op {
	case "<":
		return "(bvslt ev_param operand)"
	case "<=":
		return "(bvsle ev_param operand)"
	case ">":
		return "(bvsgt ev_param operand)"
	case ">=":
		return "(bvsge ev_param operand)"
	}
	return "(= ev_param operand)"
}

const smtTemplate = `
(define-fun pred_rtl ((ev_param (_ BitVec 32)) (operand (_ BitVec 32)) (pred_op (_ BitVec 8))) Bool
  (ite (= pred_op #x00) true
  (ite (= pred_op #x01) (= ev_param operand)
  (ite (= pred_op #x02) (not (= ev_param operand))
  (ite (= pred_op #x03) (bvsgt ev_param operand)
  (ite (= pred_op #x04) (bvslt ev_param operand)
  (ite (= pred_op #x05) (and (bvsge ev_param ((_ sign_extend 16) ((_ extract 15 0) operand)))
                             (bvsle ev_param ((_ sign_extend 16) ((_ extract 31 16) operand))))
  (ite (= pred_op #x06) (not (= (bvand ev_param operand) #x00000000))
       false))))))))

(define-fun cand_rtl ((cur_state (_ BitVec 32)) (ev_param (_ BitVec 32)) (operand (_ BitVec 32)) (act_op (_ BitVec 8))) (_ BitVec 32)
  (ite (= act_op #x00) ev_param
  (ite (= act_op #x01) (bvadd cur_state #x00000001)
  (ite (= act_op #x02) (bvsub cur_state #x00000001)
  (ite (= act_op #x03) (bvadd cur_state operand)
  (ite (= act_op #x04) (bvsub cur_state operand)
       cur_state))))))

(define-fun ovf_rtl ((cur_state (_ BitVec 32)) (operand (_ BitVec 32)) (act_op (_ BitVec 8))) Bool
  (let ((add_r (bvadd cur_state operand))
        (sub_r (bvsub cur_state operand)))
    (ite (= act_op #x01) (= cur_state #x7fffffff)
    (ite (= act_op #x02) (= cur_state #x80000000)
    (ite (= act_op #x03) (and (= ((_ extract 31 31) cur_state) ((_ extract 31 31) operand))
                              (not (= ((_ extract 31 31) add_r) ((_ extract 31 31) cur_state))))
    (ite (= act_op #x04) (and (not (= ((_ extract 31 31) cur_state) ((_ extract 31 31) operand)))
                              (not (= ((_ extract 31 31) sub_r) ((_ extract 31 31) cur_state))))
         false))))))

(define-fun commit_rtl ((cur_state (_ BitVec 32)) (ev_param (_ BitVec 32)) (operand (_ BitVec 32))
                        (pred_op (_ BitVec 8)) (guard_fl (_ BitVec 8)) (haz_lim (_ BitVec 8)) (act_op (_ BitVec 8))) Bool
  (let ((p_raw (pred_rtl ev_param operand pred_op))
        (cand (cand_rtl cur_state ev_param operand act_op))
        (ovf (ovf_rtl cur_state operand act_op))
        (act_ok (bvule act_op #x04))
        (assump_k (= ((_ extract 0 0) guard_fl) #b1))
        (inv_k (= ((_ extract 1 1) guard_fl) #b1))
        (haz_en (= ((_ extract 2 2) guard_fl) #b1))
        (inv_assump (= ((_ extract 3 3) guard_fl) #b1)))
    (and act_ok
         assump_k
         (ite inv_assump (not p_raw) p_raw)
         inv_k
         (not ovf)
         (bvsge cand #x00000000)
         (not (and haz_en (not (= haz_lim #x00)) (bvsgt ev_param ((_ zero_extend 24) haz_lim)))))))

(define-fun pred_c99 ((ev_param (_ BitVec 32)) (operand (_ BitVec 32)) (pred_op (_ BitVec 8))) Bool
  (ite (= pred_op #x00) true
  (ite (= pred_op #x01) @EQ@
  (ite (= pred_op #x02) @NEQ@
  (ite (= pred_op #x03) @GT@
  (ite (= pred_op #x04) @LT@
  (ite (= pred_op #x05) (and @RNG_LO@ @RNG_HI@)
  (ite (= pred_op #x06) (not (= (bvand ev_param operand) #x00000000))
       false))))))))

(define-fun cand_c99_fn ((cur_state (_ BitVec 32)) (ev_param (_ BitVec 32)) (operand (_ BitVec 32)) (act_op (_ BitVec 8))) (_ BitVec 32)
  (ite (= act_op #x00) ev_param
  (ite (= act_op #x01) @INC@
  (ite (= act_op #x02) @DEC@
  (ite (= act_op #x03) @ADD@
  (ite (= act_op #x04) @SUB@
       cur_state))))))

(define-fun ovf_c99_fn ((cur_state (_ BitVec 32)) (ev_param (_ BitVec 32)) (operand (_ BitVec 32)) (act_op (_ BitVec 8))) Bool
  (let ((cand_c99 (cand_c99_fn cur_state ev_param operand act_op)))
    (ite (= act_op #x01) (= cur_state #x7fffffff)
    (ite (= act_op #x02) (= cur_state #x80000000)
    (ite (= act_op #x03) (and (= (bvand (bvxor cur_state operand) #x80000000) #x00000000)
                              (not (= (bvand (bvxor cand_c99 cur_state) #x80000000) #x00000000)))
    (ite (= act_op #x04) (and @SUB_OVF1@
                              (not (= (bvand (bvxor cand_c99 cur_state) #x80000000) #x00000000)))
         false))))))

(define-fun commit_c99_fn ((cur_state (_ BitVec 32)) (ev_param (_ BitVec 32)) (operand (_ BitVec 32))
                           (pred_op (_ BitVec 8)) (guard_fl (_ BitVec 8)) (haz_lim (_ BitVec 8)) (act_op (_ BitVec 8))) Bool
  (let ((p_raw (pred_c99 ev_param operand pred_op))
        (cand_c99 (cand_c99_fn cur_state ev_param operand act_op))
        (ovf_c99 (ovf_c99_fn cur_state ev_param operand act_op))
        (act_ok (bvule act_op #x04))
        (assump_k (not (= (bvand guard_fl #x01) #x00)))
        (inv_known_c99 (not (= (bvand guard_fl #x02) #x00)))
        (haz_en (not (= (bvand guard_fl #x04) #x00)))
        (inv_assump (not (= (bvand guard_fl #x08) #x00))))
    (and act_ok
         assump_k
         (ite inv_assump (not p_raw) p_raw)
         @INV_OK@
         (not (and haz_en (not (= haz_lim #x00)) (bvsgt ev_param ((_ zero_extend 24) haz_lim)))))))

(define-fun trig_rtl ((cm Bool) (guard_fl (_ BitVec 8)) (subscriber_cid (_ BitVec 32)) (cid (_ BitVec 6))) Bool
  (and cm
       (bvult subscriber_cid #x00000040)
       (or (= ((_ extract 4 4) guard_fl) #b1) (not (= subscriber_cid #x00000000)))
       (not (= ((_ extract 5 0) subscriber_cid) cid))))

(define-fun trig_c99 ((cm Bool) (guard_fl (_ BitVec 8)) (subscriber_cid (_ BitVec 32)) (cid (_ BitVec 6))) Bool
  (and cm
       (bvult subscriber_cid #x00000040)
       (or (not (= (bvand guard_fl #x10) #x00)) (not (= subscriber_cid #x00000000)))
       @SELF_SUP@))
`
