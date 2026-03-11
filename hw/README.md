# Title

The testboard is an integrated solution for the IC bring-up featuring:
- A plcc socket,
- LDOs for the padring and core supply of 3.3V and 1.2V respectively
- Reset button
- Solderable jumper to select active high or active low reset
- 25MHz crystal oscillator
- DAC to provide bias voltages to the PLL
- 4-positions DIP switch for selecting the PLL frequency
- USB to UART bridge IC (CP2102N)
- Two jumpers to select source of clock and 1.2v supply (from the board ot from the connector)
- Buffer for the input clock signal from the FPGA and the output clock signal
- Connector for the DE10-Lite FPGA.



## Assembly guidelines
First solder the SMD components using the solder stencil and a reflow oven. Avoid placing the DIP switch in the reflow oven and solder it by hand afterwards.

With the SMD component soldered test the LDOs operation providing 5V and 3.3V from the connector U1 (TB). 
Check that there are no shorts on the USB-C connector 
Check that the QFN packages for U5 and U6 have no shorts and all pins are soldered.
Close the solder jumper JP4 and JP5 on low position denoted by the silk print "L" on the board.

Solder the through hole components such as the power switch S2, the connector J2 and the jumpers JP1 and JP2. Solder the 40pins FPGA connectors.
At this stage don't solder the PLCC socket J4 as it might be useful to access the pin holes for testing.

After testing is complete solder the PLCC socket with the arrow pointing down indicating pin number 1

### Testing the DAC
the I2C DAC Ic can be tested by connecting a DE10-Lite FPGA board and uploading the bitstream as described in the relevant page of this repository.
The FPGA will automatically configure the DAC through I2C after reset. The DAC requires the 1.2V as reference. Check that the core supply jumper is set on BRD for using the LDO as supply. 
The DAC output can be tested from the testpoints DAC1 and DAC2 that will show the voltag specified in the file [adc_commander.sv](../gw/src/adc_commander.sv)

### Testing the USB-UART bridge
The USB-UART bridge can be tested using the FPGA design provided as explained in the relevant page of this repository. Once the FPGA bitstream is loaded, the UART-JTAG communication can be tested through the Python script.


The TX/RX leds D2 and D3 will not work for a newly soldered CP2102N IC because its pin have to be configured first. The CP2102N can be configured following these steps:
- Install the drivers downloadable from this [page](https://www.silabs.com/software-and-tools/usb-to-uart-bridge-vcp-drivers?tab=downloads)
- Install Simplicity Studio 5 (not 6) (downloaded from this [page](https://www.silabs.com/software-and-tools/simplicity-studio/simplicity-studio-version-5))
- Turn on the board and launch Simplicity Studio. The software should recognise the IC. 
- Click on Tools>Express Configurator.
- In configuration Groupings>Port Configuraations:GPIO set GPIO0 and GPIO1 to TX Toggle and RX toggle respectively.
- Select "Program to Device"






## Improvements
Subsequent versions of the board can include the following improvements:
- Add capacitors between the PLCC socket supply pins and ground
- Add a mark indicating the pin number 1 on the PLCC socket
- Test the addition of a small value resistor between the PLCC socket input clock pin and the schmitt trigger buffer to reduce ringing.
- Add more mounting holes     