# ============================================================================
# PYNQ-Z1 Master XDC Constraints for KPOL BRAM Pipeline (CFG-P)
# Target Device: xc7z020clg400-1
# Standards: Digilent PYNQ-Z1 Reference Manual, ASPICE HWE.2
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

# PMODA (Pmod JA) Header (HIL Stimulus & Reactive Monitor)
# Pin 1 (JA1) = Stimulus In, Pin 2 (JA2) = Commit Out, Pin 3 (JA3) = Reject Out, Pin 4 (JA4) = Busy Out
set_property LOC Y18 [get_ports {ja1}]
set_property IOSTANDARD LVCMOS33 [get_ports {ja1}]
set_property LOC Y19 [get_ports {ja2}]
set_property IOSTANDARD LVCMOS33 [get_ports {ja2}]
set_property LOC Y16 [get_ports {ja3}]
set_property IOSTANDARD LVCMOS33 [get_ports {ja3}]
set_property LOC Y17 [get_ports {ja4}]
set_property IOSTANDARD LVCMOS33 [get_ports {ja4}]

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
