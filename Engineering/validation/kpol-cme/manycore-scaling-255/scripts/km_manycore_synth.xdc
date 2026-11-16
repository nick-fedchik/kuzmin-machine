# ============================================================================
# OpenXC7 Physical Pin Constraints for Many-Core Scaling Wrapper (Issue #255)
# Target Device: xc7z020clg400-1 (20 user IOB pads <= 125 budget)
# ============================================================================

# MRCC Global Clock Input (Bank 35, 100 MHz STA target via --freq 100)
set_property LOC H16 [get_ports {clk_i}]
set_property IOSTANDARD LVCMOS33 [get_ports {clk_i}]

# Reset & Control Inputs
set_property LOC D19 [get_ports {rst_ni}]
set_property IOSTANDARD LVCMOS33 [get_ports {rst_ni}]
set_property LOC D20 [get_ports {cmd_valid_i}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmd_valid_i}]

set_property LOC L20 [get_ports {cmd_mode_i[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmd_mode_i[0]}]
set_property LOC L19 [get_ports {cmd_mode_i[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmd_mode_i[1]}]

set_property LOC M20 [get_ports {cmd_sel_i[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmd_sel_i[0]}]
set_property LOC M19 [get_ports {cmd_sel_i[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmd_sel_i[1]}]
set_property LOC H15 [get_ports {cmd_sel_i[2]}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmd_sel_i[2]}]

# 8-bit Frame Data Bus
set_property LOC Y18 [get_ports {cmd_data_i[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmd_data_i[0]}]
set_property LOC Y19 [get_ports {cmd_data_i[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmd_data_i[1]}]
set_property LOC Y16 [get_ports {cmd_data_i[2]}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmd_data_i[2]}]
set_property LOC Y17 [get_ports {cmd_data_i[3]}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmd_data_i[3]}]
set_property LOC W18 [get_ports {cmd_data_i[4]}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmd_data_i[4]}]
set_property LOC W19 [get_ports {cmd_data_i[5]}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmd_data_i[5]}]
set_property LOC U18 [get_ports {cmd_data_i[6]}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmd_data_i[6]}]
set_property LOC U19 [get_ports {cmd_data_i[7]}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmd_data_i[7]}]

# Status & Readout Outputs
set_property LOC R14 [get_ports {status_busy_o}]
set_property IOSTANDARD LVCMOS33 [get_ports {status_busy_o}]
set_property LOC P14 [get_ports {status_ready_o}]
set_property IOSTANDARD LVCMOS33 [get_ports {status_ready_o}]
set_property LOC N16 [get_ports {obs_data_o[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {obs_data_o[0]}]
set_property LOC M14 [get_ports {obs_data_o[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {obs_data_o[1]}]
set_property LOC G15 [get_ports {obs_data_o[2]}]
set_property IOSTANDARD LVCMOS33 [get_ports {obs_data_o[2]}]
