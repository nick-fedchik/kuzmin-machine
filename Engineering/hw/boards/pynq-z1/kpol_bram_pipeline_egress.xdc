# ============================================================================
# PYNQ-Z1 XDC Constraints for KPOL BRAM Pipeline + PMOD Event Egress (#241, #247)
# Target Device: xc7z020clg400-1
# Standards: Digilent PYNQ-Z1 Reference Manual, LVCMOS33 (3.3V)
#
# Inter-board Level Shifting (3.3V LVCMOS <-> 1.8V Jetson AGX Orin J501):
# 1. TI TXS0108E (SCES642I, Table 6.6 / 6.7 Switching Characteristics for
#    VCCA = 1.8V +/- 0.15V, VCCB = 3.3V +/- 0.3V):
#    - Maximum data rate in Push-Pull mode (1.8V <-> 3.3V): 60 Mbps (30 MHz
#      clock, 33.3 ns period; 110 Mbps applies only to VCCA >= 2.5V -> 3.3V);
#      Open-Drain mode: 2 Mbps.
#    - PAR8 mode (par_valid strobe 50 MHz / 10 ns half-period = 100 Mbps, or
#      2-cycle hold = 25 MHz / 50 Mbps) lies within or at the 60 Mbps limit;
#      SPI 50 MHz (100 Mbps on SCK) exceeds the 60 Mbps rating for 1.8V/3.3V
#      and is sensitive to jumper wire capacitance after the ~10 ns one-shot
#      edge-rate accelerator pulse ends (unbuffered ~10 kOhm pull-up).
#    - Choice between laboratory TXS0108E (at reduced SPI clock or PAR8 with
#      short leads) and buffered SN74AVC8T245 is formulated as an engineering
#      hypothesis and verification criterion for physical HIL (#226).
# 2. Buffered SN74AVC8T245 (SCES172) Hardware Checklist:
#    - VCCA = 3.3V (PYNQ-Z1 PMOD JA/JB rail), VCCB = 1.8V (Jetson J501 rail).
#    - 8-bit JB egress bus (A -> B, 3.3V -> 1.8V): tie DIR = HIGH (VCCA = 3.3V)
#      directly on the power rail (no FPGA GPIO needed for direction control;
#      for reverse ext_ready_i 1.8V -> 3.3V use a separate channel with
#      DIR = LOW (GND) or single-bit SN74AVC1T45).
#    - /OE (active-low): 10 kOhm pull-up to VCCA (3.3V) for guaranteed Hi-Z
#      during power-up (I_off partial-power-down protection until both VCCA
#      and VCCB stabilize), then tied to GND (or optional enable signal).
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
