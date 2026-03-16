
# FPGA Control Firmware for VLSI Test Platform

This directory contains the SystemVerilog modules that implement the control firmware for the VLSI Module Project IC test platform. The design runs on the DE10-Lite FPGA board and provides the following core functionality:

- **ADC Configuration**: Configures the bias voltages for the PLL via I2C protocol
- **UART-to-JTAG Bridge**: Bridges serial communication to JTAG for IC programming and testing
- **Generated Clock Output**: Provides a configurable clock signal for testing

## Module Overview

| Module | File | Purpose |
|--------|------|---------|
| `DE10Top` | `DE10Top.sv` | Top-level module integrating all components |
| `adc_commander` | `adc_commander.sv` | Manages I2C communication with the ADC for PLL bias voltage configuration |
| `i2c_master` | `i2c_master.sv` | I2C protocol controller |
| `jtag_uart_bridge` | `jtag_uart_bridge.sv` | Converts UART byte stream to JTAG signals (TMS, TDI, TCK, TDO) |
| `jtag_engine` | `jtag_engine.sv` | Low-level JTAG state machine controller |
| `uart_rx` / `uart_tx` | `uart_rx.sv`, `uart_tx.sv` | UART serial communication |
| `rx_fifo` / `tx_fifo` | `rx_fifo.sv`, `tx_fifo.sv` | Synchronous FIFOs for UART buffering |

## Clock Generation

The design generates an internal 10 MHz clock using the Quartus PLL IP (`pll_clk`). An additional output clock (`clk_out`) is generated at 100 kHz and output to pin Y5 (IC package pin 43). The output clock frequency can be modified by changing the `OUTPUT_CLK_FREQ` parameter in `DE10Top.sv`.

**Note**: The Quartus IP generator may not generate the PLL IP correctly. Verify that the output frequency matches the expected value before deployment.

## I2C and ADC Commander

The ADC on the test board configures the PLL bias voltages via the I2C protocol. The `adc_commander` module orchestrates this configuration by sending commands through the `i2c_master` module.

- **Bias Voltage Configuration**: Two 12-bit voltage values are configured via I2C
- **Experimental Tuning**: Voltage values should be calibrated based on measurements on the actual IC

For details on command sequences, refer to `adc_commander.sv`.

## UART Connectivity

The test board includes a USB-UART bridge IC (CP2102N) connected to the FPGA:

| FPGA Port | CP2102N Pin | Direction |
|-----------|------------|-----------|
| `uart_rx` | Y6 | Input (from host) |
| `uart_tx` | Y7 | Output (to host) |

**Note**: Pin assignments swap the physical connections; the FPGA perspective labels (`uart_rx`, `uart_tx`) correctly represent the data flow.

Pin assignments in the `.qpf` file:
```
set_location_assignment PIN_Y6 -to uart_rx
set_location_assignment PIN_Y7 -to uart_tx
```

## UART-to-JTAG Bridge

The `jtag_uart_bridge` module converts UART byte stream to JTAG protocol signals for IC programming and testing. Each UART byte is interpreted as:
- **High nibble (bits 7-4)**: Four TMS bits
- **Low nibble (bits 3-0)**: Four TDI bits

The `jtag_engine` module implements the JTAG state machine and handles TCK generation.

A Python driver for communicating with the bridge is provided in the `/sw` folder.

## Customizing the Design

The FPGA can be extended to drive IC inputs and process outputs based on project specifications:
- **UART Redirection**: Redirect UART ports to IC GPIO through the FPGA fabric
- **Preserve ADC Configuration**: The `adc_commander` module is required for correct PLL operation
- **Extending Functionality**: Additional logic can be instantiated in parallel with existing modules


### Pin Assignments

The following pin constraints are required for the test board:

```
set_location_assignment PIN_V7 -to rst_n
set_location_assignment PIN_P11 -to pll_clk
set_location_assignment PIN_Y6 -to uart_rx
set_location_assignment PIN_Y7 -to uart_tx
set_location_assignment PIN_W11 -to sda
set_location_assignment PIN_AA10 -to scl
set_location_assignment PIN_Y5 -to clk_out 
```

All pin IO Standard must be configured on `3.3-V LVTTL`.

## Testing the JTAG Interface

To test the JTAG functionality with a simulated IC memory model:

1. Prepare a second DE10-Lite board to act as a Device Under Test (DUT)
2. Load the DUT bitstream via Quartus > Tools > Programmer
3. Connect the DUT to the test board's DUT connector
4. Use the Python script (in `/sw`) to program through the UART-JTAG bridge

**Bitstream Files**:
- `.sof` (SRAM Object File): Loaded directly into FPGA RAM; erased on power-off
- `.pof` (Programmer Object File): Stored in flash memory; persists across power cycles

Use `.pof` to retain the FPGA design after power-off.