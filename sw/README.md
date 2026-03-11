# JTAGProg — Host-Side JTAG/UART Programmer

`JTAGProg.py` is a Python tool for driving the JTAG Engine firmware module located in [gw/src/](../gw/src/) via a UART interface. A USB-to-UART bridge (e.g. FTDI or CP2102N) exposes the JTAG engine to the host as a standard serial port.

## How it works

The script contains two main classes:

- **`JTAGDriver`** — builds TMS/TDI bitstreams and packs them into bytes. Each byte encodes four JTAG clock cycles: the high nibble carries four TMS bits and the low nibble carries four TDI bits. The class provides helpers for navigating the JTAG FSM and shifting instructions and data registers.
- **`JTAGProg`** — opens a serial port and sends/receives the packed byte stream to/from the UART bridge. Read data is recovered by clocking dummy bytes into the TAP and capturing the TDO bits returned by the target device.

## Dependencies

Install the required package with:

```
pip install pyserial
```

## Usage

Run the script with `-h` to see all options:

```
python JTAGProg.py -h
```

In both modes the COM port must be specified. To list available ports:

```
python -m serial.tools.list_ports -v
```

### Test mode

Generates random 32-bit words, writes them to memory, then reads them back and verifies the contents.

```
python JTAGProg.py COM4 --test-mode --word-count 256
```

`--word-count` is optional (default: 128).

### Load mode

Writes the contents of a plain-text file containing one 32-bit hex word per line.

```
python JTAGProg.py COM4 data.hex
```

### Output

Both modes print a summary after verification:

```
Summary:
  Total words: 256
  Total bytes: 1024 (1.00 KB)
  Total write time: 1.604s
  Write throughput: 0.62 KB/s
  Total read time: 6.994s
  Read throughput: 0.14 KB/s
  Total errors: 0
```

The script exits with code `2` if any verification errors are detected, or `0` on success.