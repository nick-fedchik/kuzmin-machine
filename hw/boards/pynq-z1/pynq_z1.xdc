# PYNQ-Z1 Constraints for Kuzmin Machine Hardware Demo

# Green User LEDs LD0..LD3
set_property LOC R14 [get_ports {led[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {led[0]}]
set_property LOC P14 [get_ports {led[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {led[1]}]
set_property LOC N16 [get_ports {led[2]}]
set_property IOSTANDARD LVCMOS33 [get_ports {led[2]}]
set_property LOC M14 [get_ports {led[3]}]
set_property IOSTANDARD LVCMOS33 [get_ports {led[3]}]

# RGB LED 4 (Status Alert: Green=Commit, Red=Invariant Reject, Blue=Hazard/Input)
set_property LOC N15 [get_ports rgb4_r]
set_property IOSTANDARD LVCMOS33 [get_ports rgb4_r]
set_property LOC G17 [get_ports rgb4_g]
set_property IOSTANDARD LVCMOS33 [get_ports rgb4_g]
set_property LOC L15 [get_ports rgb4_b]
set_property IOSTANDARD LVCMOS33 [get_ports rgb4_b]

# RGB LED 5 (Heartbeat Alive Monitor)
set_property LOC M15 [get_ports rgb5_r]
set_property IOSTANDARD LVCMOS33 [get_ports rgb5_r]
set_property LOC L14 [get_ports rgb5_g]
set_property IOSTANDARD LVCMOS33 [get_ports rgb5_g]
set_property LOC G14 [get_ports rgb5_b]
set_property IOSTANDARD LVCMOS33 [get_ports rgb5_b]

# PMODA (Pmod JA) Header: Pin 1 (JA1) = Stimulus In, Pin 2 (JA2) & Pin 3 (JA3) = Reactive Out, Pin 4 (JA4) = AXI Monitor
set_property LOC Y18 [get_ports ja1]
set_property IOSTANDARD LVCMOS33 [get_ports ja1]
set_property LOC Y19 [get_ports ja2]
set_property IOSTANDARD LVCMOS33 [get_ports ja2]
set_property LOC Y16 [get_ports ja3]
set_property IOSTANDARD LVCMOS33 [get_ports ja3]
set_property LOC Y17 [get_ports ja4]
set_property IOSTANDARD LVCMOS33 [get_ports ja4]

# Pushbuttons (BTN0 = Trigger, BTN1..3)
set_property LOC D19 [get_ports {btn[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {btn[0]}]
set_property LOC D20 [get_ports {btn[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {btn[1]}]
set_property LOC L20 [get_ports {btn[2]}]
set_property IOSTANDARD LVCMOS33 [get_ports {btn[2]}]
set_property LOC L19 [get_ports {btn[3]}]
set_property IOSTANDARD LVCMOS33 [get_ports {btn[3]}]

# Slide Switches (SW0 = Invariant Enable, SW1 = Input Enable)
set_property LOC M20 [get_ports {sw[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {sw[0]}]
set_property LOC M19 [get_ports {sw[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {sw[1]}]
