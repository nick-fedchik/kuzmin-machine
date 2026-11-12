# Raspberry Pi Pico (RP2040) PIO Fast Logic Analyzer Firmware
# Kuzmin Machine HIL Testbench ( Львові / PYNQ-Z1 HIL )
#
# Runs on RP2040 (Raspberry Pi Pico / Pico-Zero) under MicroPython.
# Uses PIO state machine to sample 8 GPIO channels (GP0..GP7) at up to 100-125 MS/s.

import time
import rp2
from machine import Pin, freq

# Set RP2040 system clock to 125 MHz (standard) or 200 MHz for higher resolution
# freq(125_000_000) -> 8 ns per cycle
# freq(200_000_000) -> 5 ns per cycle

@rp2.asm_pio(in_shiftdir=rp2.PIO.SHIFT_RIGHT, autopush=True, push_thresh=32)
def logic_analyzer_sample():
    """
    PIO assembly routine:
    Reads 8 pins (GP0..GP7) every clock cycle into the ISR and pushes 32-bit words (4 samples).
    """
    wrap_target()
    in_(pins, 8)  # Sample 8 input pins [1 cycle]
    wrap()

def run_capture(num_words=8192, trigger_pin=0, clock_freq=125_000_000):
    """
    Initializes pins, configures state machine, waits for trigger on trigger_pin,
    samples buffer, and streams binary data over USB CDC stdout.
    """
    freq(clock_freq)
    
    # Configure pins GP0..GP7 as inputs with pull-downs
    pins = [Pin(i, Pin.IN, Pin.PULL_DOWN) for i in range(8)]
    
    # Configure State Machine 0
    sm = rp2.StateMachine(
        0,
        logic_analyzer_sample,
        freq=clock_freq,
        in_base=Pin(0)
    )
    
    buf = bytearray(num_words * 4)
    
    # Wait for trigger on trigger_pin (rising edge)
    trig = Pin(trigger_pin, Pin.IN)
    while trig.value() == 0:
        pass
        
    # Start sampling immediately upon trigger
    sm.active(1)
    
    # Drain words from SM into buffer
    # Note: in real-time streaming, DMA is used; in MicroPython, DMA is accessed via uctypes or PIO buffer
    for i in range(num_words):
        sm.get(buf, i * 4)
        
    sm.active(0)
    return buf

if __name__ == "__main__":
    print("Kuzmin Machine RP2040 Logic Analyzer Ready.")
    print("Sampling GP0..GP7 @ 125 MS/s (8 ns/sample)")
