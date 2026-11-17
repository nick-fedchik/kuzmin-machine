# ============================================================================
# PYNQ-Z1 XDC Constraints for KPOL BRAM Pipeline + PMOD Event Egress (#241, #247)
# Target Device: xc7z020clg400-1
# Standards: Digilent PYNQ-Z1 Reference Manual, LVCMOS33 (3.3V)
#
# Inter-board Level Shifting (3.3V LVCMOS <-> 1.8V Jetson AGX Orin J501):
# 1. TI TXS0108E (SCES642L, November 2024):
#    - Maximum data rate in Push-Pull mode for VCCA = 1.8V +/- 0.15V,
#      VCCB = 3.3V +/- 0.3V: 60 Mbps in Switching Characteristics (Table 5.11,
#      30 MHz clock / 33.3 ns period; also 60 Mbps in Table 5.12 for VCCA = 2.5V,
#      VCCB = 3.3V) and 70 Mbps in Timing Requirements (Table 5.7); 110 Mbps
#      applies only to VCCA = 3.3V -> VCCB = 5.0V (Table 5.9 / Table 5.13).
#    - Maximum data rate in Open-Drain mode for VCCA = 1.8V, VCCB = 3.3V:
#      0.8 Mbps (Table 5.11; up to 1.2 Mbps in document header for 3.3V -> 5.0V).
#    - Current km_pmod_event_egress.sv RTL rates vs TXS0108E 1.8V <-> 3.3V rating:
#      both SPI (50 MHz SCK = 100 Mbps) and PAR8 strobe (par_valid / par_clk at
#      50 MHz, 10 ns HIGH / 10 ns LOW = 100 Mbps equivalent on the strobe line)
#      exceed the 60 Mbps (Table 5.11) / 70 Mbps (Table 5.7) datasheet rating,
#      whereas PAR8 data lines par_data[7:0] change once every 2 clock cycles
#      (20 ns per byte = 50 Mbps, within 60 Mbps). Operating within TXS0108E
#      datasheet limits would require stretching the PAR8 strobe phase / SPI
#      divider, or verifying the actual edge rate on the HIL bench (#226) given
#      jumper wire capacitance after the ~10 ns one-shot accelerator ends
#      (unbuffered ~10 kOhm pull-up).
#    - Choice between laboratory TXS0108E and buffered SN74AVC8T245 is formulated
#      as an engineering hypothesis and verification criterion for HIL (#226).
# 2. Buffered SN74AVC8T245 (SCES172) Hardware Checklist:
#    - VCCA = 3.3V (PYNQ-Z1 PMOD JA/JB rail), VCCB = 1.8V (Jetson J501 rail).
#    - DIR (shared across all 8 channels of SN74AVC8T245): tie DIR = HIGH
#      (VCCA = 3.3V) so the entire 8-bit JB chip operates A -> B (3.3V -> 1.8V).
#      For reverse signal ext_ready_i (1.8V -> 3.3V), a separate single-channel
#      translator IC (e.g. SN74AVC1T45 or a second package) is required, not a
#      channel of the same SN74AVC8T245.
#    - /OE (active-low, TI SCES172 recommendation): 10 kOhm pull-up resistor to
#      VCCA (3.3V) for guaranteed Hi-Z during power-up/down (I_off protection),
#      driven LOW by a dedicated enable output (GPIO or inverted Power-Good of
#      the 1.8V VCCB domain) only after both VCCA and VCCB have stabilized.
#    - Receiver-side strobe pull-downs (1.8V B-side): weak 47..100 kOhm
#      pull-down resistors to GND on par_valid / spi_cs_n (or pull-up on active-low
#      CS) so strobe lines do not float while SN74AVC8T245 outputs are Hi-Z
#      (/OE = HIGH during power sequencing).
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
