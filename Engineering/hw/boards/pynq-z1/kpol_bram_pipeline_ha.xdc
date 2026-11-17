# ============================================================================
# PYNQ-Z1 XDC Constraints for Dual-Bank KPOL BRAM Pipeline (CFG-P-HA, #253)
# Target Device: xc7z020clg400-1
# Standards: Digilent PYNQ-Z1 Reference Manual, LVCMOS33 (3.3V), EXP-GPU-02
# ============================================================================

# Green User LEDs LD0..LD3
set_property LOC R14 [get_ports {led[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {led[0]}]
set_property LOC P14 [get_ports {led[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {led[1]}]
set_property LOC N16 [get_ports {led[2]}]
set_property IOSTANDARD LVCMOS33 [get_ports {led[2]}]
set_property LOC M14 [get_ports {led[3]}]
set_property IOSTANDARD LVCMOS33 [get_ports {led[3]}]

# PMODA (Pmod JA) Header (HIL Stimulus & Stretched Reactive Monitor)
# Pin 1 (JA1) = Stimulus In, Pin 2 (JA2) = Commit Out, Pin 3 (JA3) = Reject Out, Pin 4 (JA4) = Busy Out
set_property LOC Y18 [get_ports {ja1}]
set_property IOSTANDARD LVCMOS33 [get_ports {ja1}]
set_property LOC Y19 [get_ports {ja2}]
set_property IOSTANDARD LVCMOS33 [get_ports {ja2}]
set_property LOC Y16 [get_ports {ja3}]
set_property IOSTANDARD LVCMOS33 [get_ports {ja3}]
set_property LOC Y17 [get_ports {ja4}]
set_property IOSTANDARD LVCMOS33 [get_ports {ja4}]

# PMODB (Pmod JB) Header (EXP-GPU-02 Unstretched 1-cycle 10 ns Strobes for RP2040 PIO GP0..GP4 + Active Bank)
# JB1 (W14, Pin 1) = inject_strobe_o     (GP0: INJECT_STROBE)
# JB2 (Y14, Pin 2) = bank_swap_commit_o  (GP1: BANK_SWAP_COMMIT)
# JB3 (T11, Pin 3) = stimulus_accepted_o (GP2: STIMULUS_EVENT)
# JB4 (T10, Pin 4) = reaction_out_o      (GP3: REACTION_OUT)
# JB7 (V16, Pin 7) = seq_cycle_done_o    (GP4: SEQ_CYCLE_DONE)
# JB8 (W16, Pin 8) = active_bank_o       (Active Bank 0/1 visual monitor)
set_property LOC W14 [get_ports {jb1}]
set_property IOSTANDARD LVCMOS33 [get_ports {jb1}]
set_property LOC Y14 [get_ports {jb2}]
set_property IOSTANDARD LVCMOS33 [get_ports {jb2}]
set_property LOC T11 [get_ports {jb3}]
set_property IOSTANDARD LVCMOS33 [get_ports {jb3}]
set_property LOC T10 [get_ports {jb4}]
set_property IOSTANDARD LVCMOS33 [get_ports {jb4}]
set_property LOC V16 [get_ports {jb7}]
set_property IOSTANDARD LVCMOS33 [get_ports {jb7}]
set_property LOC W16 [get_ports {jb8}]
set_property IOSTANDARD LVCMOS33 [get_ports {jb8}]

# Pushbuttons BTN0..BTN3 (BTN0 = Manual Hardware Trigger)
set_property LOC D19 [get_ports {btn[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {btn[0]}]
set_property LOC D20 [get_ports {btn[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {btn[1]}]
set_property LOC L20 [get_ports {btn[2]}]
set_property IOSTANDARD LVCMOS33 [get_ports {btn[2]}]
set_property LOC L19 [get_ports {btn[3]}]
set_property IOSTANDARD LVCMOS33 [get_ports {btn[3]}]

# Slide Switches SW0..SW1 (SW[1:0] = Target Concept ID 0..3)
set_property LOC M20 [get_ports {sw[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {sw[0]}]
set_property LOC M19 [get_ports {sw[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {sw[1]}]
