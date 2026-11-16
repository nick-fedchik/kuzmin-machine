# ============================================================================
# PYNQ-Z1 XDC Constraints for KPOL BRAM Pipeline + PMOD Event Egress (#241)
# Target Device: xc7z020clg400-1
# Standards: Digilent PYNQ-Z1 Reference Manual, LVCMOS33 (3.3V)
# Note: Inter-board connection to Jetson J501 (1.8V) requires an external
# directional push-pull level shifter (SN74AVC8T245 / SN74LVC8T245) for 50 MHz.
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

# PMODA (Pmod JA) Header
# JA1..JA4: HIL Stimulus & Pipeline Status
set_property LOC Y18 [get_ports {ja1}]
set_property IOSTANDARD LVCMOS33 [get_ports {ja1}]
set_property LOC Y19 [get_ports {ja2}]
set_property IOSTANDARD LVCMOS33 [get_ports {ja2}]
set_property LOC Y16 [get_ports {ja3}]
set_property IOSTANDARD LVCMOS33 [get_ports {ja3}]
set_property LOC Y17 [get_ports {ja4}]
set_property IOSTANDARD LVCMOS33 [get_ports {ja4}]

# JA7..JA10: Egress Mode & Control Strobes
set_property LOC U18 [get_ports {egress_par8_mode_i}]
set_property IOSTANDARD LVCMOS33 [get_ports {egress_par8_mode_i}]
set_property PULLDOWN true [get_ports {egress_par8_mode_i}]
set_property LOC U19 [get_ports {ja8_egress_start}]
set_property IOSTANDARD LVCMOS33 [get_ports {ja8_egress_start}]
set_property LOC W18 [get_ports {ja9_par_valid}]
set_property IOSTANDARD LVCMOS33 [get_ports {ja9_par_valid}]
set_property LOC W19 [get_ports {ja10_par_clk}]
set_property IOSTANDARD LVCMOS33 [get_ports {ja10_par_clk}]

# PMODB (Pmod JB) Header: JB1..JB4 = jb[3:0], JB7..JB10 = jb[7:4]
set_property LOC W14 [get_ports {jb[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {jb[0]}]
set_property LOC Y14 [get_ports {jb[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {jb[1]}]
set_property LOC T11 [get_ports {jb[2]}]
set_property IOSTANDARD LVCMOS33 [get_ports {jb[2]}]
set_property LOC T10 [get_ports {jb[3]}]
set_property IOSTANDARD LVCMOS33 [get_ports {jb[3]}]
set_property LOC V16 [get_ports {jb[4]}]
set_property IOSTANDARD LVCMOS33 [get_ports {jb[4]}]
set_property LOC W16 [get_ports {jb[5]}]
set_property IOSTANDARD LVCMOS33 [get_ports {jb[5]}]
set_property LOC V12 [get_ports {jb[6]}]
set_property IOSTANDARD LVCMOS33 [get_ports {jb[6]}]
set_property LOC W13 [get_ports {jb[7]}]
set_property IOSTANDARD LVCMOS33 [get_ports {jb[7]}]

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
