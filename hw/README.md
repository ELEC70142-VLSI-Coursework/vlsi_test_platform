# Testboard Hardware

The testboard is an integrated solution for the **VLSI SoC Project** IC bring-up. It includes:

- PLCC socket
- LDOs for the padring and core supplies (3.3 V and 1.2 V respectively)
- Reset button
- Solderable jumper to select active-high or active-low reset
- 25 MHz crystal oscillator
- DAC to supply bias voltages to the PLL
- 4-position DIP switch for selecting the PLL frequency
- USB-to-UART bridge IC (CP2102N)
- Jumpers to select the source of the clock and 1.2 V supply (board or connector)
- Buffers for the FPGA input clock and the board output clock
- Connector for the DE10-Lite FPGA



## Assembly Guidelines

First, solder the SMD components using the stencil and a reflow oven. Do not place the DIP switch in the reflow oven — solder it by hand afterwards.

Once the SMD components are soldered, test the LDOs by applying 5 V and 3.3 V to connector U1 (TB). Check for shorts on the USB-C connector and verify that QFN packages U5 and U6 have no solder bridges and all pins are properly soldered. 

Set solder jumpers JP4 and JP5 to the low position, marked "L" on the silkscreen.

Next, solder the through-hole components: power switch S2, connector J2, jumpers JP1 and JP2, and the 40-pin FPGA connectors. Do not solder the PLCC socket (J4) at this stage — leaving it unsoldered allows easier access to the pin holes for testing.

Once testing is complete, solder the PLCC socket with the orientation arrow pointing down, indicating pin 1.

### Testing the DAC

The I2C DAC IC can be tested by connecting a DE10-Lite FPGA board and loading the bitstream described elsewhere in this repository. The FPGA automatically configures the DAC over I2C after reset. The DAC requires the 1.2 V supply as its reference — ensure the core-supply jumper is set to "BRD" to use the onboard LDO. Measure the DAC outputs at testpoints DAC1 and DAC2; the expected voltages are defined in [gw/src/adc_commander.sv](../gw/src/adc_commander.sv).

### Testing the USB-UART Bridge

Test the USB-UART bridge using the provided FPGA design (see elsewhere in this repository). After loading the bitstream, verify UART–JTAG communication using the Python script.

The TX/RX LEDs (D2 and D3) will not function on a newly soldered CP2102N until the IC has been configured. To configure it:

1. Install the USB-to-UART VCP drivers from [Silicon Labs](https://www.silabs.com/software-and-tools/usb-to-uart-bridge-vcp-drivers?tab=downloads).
2. Install [Simplicity Studio 5](https://www.silabs.com/software-and-tools/simplicity-studio/simplicity-studio-version-5) (not version 6).
3. Power the board and launch Simplicity Studio — it should detect the CP2102N automatically.
4. Open **Tools > Express Configurator**.
5. Under **Configuration Groupings > Port Configurations > GPIO**, set GPIO0 to "TX Toggle" and GPIO1 to "RX Toggle".
6. Click **Program to Device**.






## Suggested Improvements

Future board revisions could include:

- Decoupling capacitors between the PLCC socket supply pins and ground.
- A silkscreen mark indicating PLCC socket pin 1.
- A small series resistor between the PLCC socket clock input and the Schmitt-trigger buffer to reduce ringing.
- Additional mounting holes.     