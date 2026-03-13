`timescale 1ns / 1ps


module DE10Top (
    input logic pll_clk,
    input logic rst_n,

    input logic uart_rx,
    output logic uart_tx,

    output logic tck,
    output logic tms,
    output logic tdi,
    input logic tdo,


	output logic l_tck,
	output logic l_tms,
	output logic l_tdi,
	output logic l_tdo,

	 // I2C bus
    inout  wire  scl,
    inout  wire  sda,

    output logic led

);

    assign {l_tck, l_tms, l_tdi} = {tck, tms, tdi};
    assign l_tdo = tdo;

    localparam CLK_FREQ = 10_000_000; // 10 MHz

    logic clk;

	pll_clk clkgen_i(
		.inclk0(pll_clk),
		.c0(clk)
	);

    // CDC logic for UART RX signal
    logic [1:0] uart_rx_sync;
    always_ff @(posedge clk) begin
        if(!rst_n) begin
            uart_rx_sync <= 2'b11; // idle state (line is high)
        end else begin
            uart_rx_sync <= {uart_rx_sync[0], uart_rx};
        end
    end

	 adc_commander #(
        .CLK_FREQ(CLK_FREQ)
     ) adc_commander_inst (
        .i_clk(clk),
        .i_rst_n(rst_n),
        .o_done(),  // Not used. It can be connected to an LED or left unconnected.
        .o_ack_error(),  // Not used. It can be connected to an LED or left unconnected.
        .scl(scl),
        .sda(sda)
    );

    // Instantiate the JTAG-UART bridge
    jtag_uart_bridge #(
        .CLK_FREQ(CLK_FREQ)
    ) jtag_uart_inst (
        .clk      (clk),
        .rst_n    (rst_n),
        .uart_rx  (uart_rx_sync[1]),
        .uart_tx  (uart_tx),
        .TCK      (tck),
        .TMS      (tms),
        .TDI      (tdi),
        .TDO      (tdo)
    );

    /////////////////////////////////// LED signals (for debugging)
    logic [$clog2(CLK_FREQ/2)-1:0] counter;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            counter <= 0;
            led <= 0;
        end else begin
            counter <= counter + 1;
            if(counter == CLK_FREQ/2 - 1) begin
                counter <= 0;
                led <= ~led; // Toggle LED every 0.5 seconds
            end
        end
    end

endmodule
