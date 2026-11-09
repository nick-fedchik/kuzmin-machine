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
set_property LOC V16 [get_ports rgb4_r]
set_property IOSTANDARD LVCMOS33 [get_ports rgb4_r]
set_property LOC F17 [get_ports rgb4_g]
set_property IOSTANDARD LVCMOS33 [get_ports rgb4_g]
set_property LOC M17 [get_ports rgb4_b]
set_property IOSTANDARD LVCMOS33 [get_ports rgb4_b]

# RGB LED 5 (Heartbeat Alive Monitor)
set_property LOC W15 [get_ports rgb5_r]
set_property IOSTANDARD LVCMOS33 [get_ports rgb5_r]
set_property LOC W16 [get_ports rgb5_g]
set_property IOSTANDARD LVCMOS33 [get_ports rgb5_g]
set_property LOC Y17 [get_ports rgb5_b]
set_property IOSTANDARD LVCMOS33 [get_ports rgb5_b]

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
