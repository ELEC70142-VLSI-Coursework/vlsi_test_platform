




## testing the JTAG interface
To test the jtag interface another DE10-Lite is needed to act as a DUT simulating the memory of the IC and its prgramming interface through JTAG.
From Quartus>Tools>Programmer load the file DUT_bitstream.pof. The difference between the .pof and .sof files is that the .sofis loaded directly on the FPGA while the .pof will be stored in the board flash memory and loaded ion the FPGA when booted. Loading the .qof file allow to retain the FPGA design after power off.
After the design is loaded on the fpga and this is connected to the testboard on the DUT connector you can use the python script to load the program through UART.