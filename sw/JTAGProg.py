"""
JTAGProg.py — Host-side JTAG/UART programmer.

Drives the JTAG Engine firmware module via a USB-to-UART bridge (e.g. FTDI or
CP210x). Each byte sent over UART carries four JTAG clock cycles: the high
nibble encodes four TMS bits and the low nibble encodes four TDI bits.

Classes:
    JTAGDriver  — Builds TMS/TDI bitstreams, packs them into the nibble format
                  described above, and provides helpers for navigating the JTAG
                  FSM and shifting instruction/data registers.
    JTAGProg    — Opens a serial port and exchanges the packed byte stream with
                  the UART bridge. Read data is recovered by clocking dummy
                  bytes into the TAP and capturing the TDO bits returned by the
                  target.

Helper functions:
    load_32bit_hex_file        — Loads 32-bit hex words from a plain-text file.
    reconstruct_data_from_response — Parses a raw read response into a
                                     (data, address) tuple.
"""

import sys
import time
import serial
import argparse
import threading
import queue
from typing import List, Optional
import random


# JTAG constants matching the C++ defines
IR_NOP = 0x0
IR_MEM_CTRL = 0x1
IR_WRITE = 0x2
IR_READ = 0x3
IR_DONE = 0x4

ADDR_W = 10
DATA_W = 32
DR_W = ADDR_W + DATA_W


class JTAGDriver:
    def __init__(self):
        self.tms_bits: List[bool] = []
        self.tdi_bits: List[bool] = []

    def clear_stream(self):
        self.tms_bits.clear()
        self.tdi_bits.clear()

    @staticmethod
    def _pack_jtag_nibble(tms: int, tdi: int) -> int:
        return ((tms & 0x0F) << 4) | (tdi & 0x0F)

    def get_stream(self) -> List[int]:
        if len(self.tms_bits) != len(self.tdi_bits):
            raise RuntimeError("TMS/TDI size mismatch")

        out = []
        n = len(self.tms_bits)
        for i in range(0, n, 4):
            tms = 0
            tdi = 0
            for b in range(4):
                if i + b < n:
                    if self.tms_bits[i + b]:
                        tms |= (1 << b)
                    if self.tdi_bits[i + b]:
                        tdi |= (1 << b)
            out.append(self._pack_jtag_nibble(tms, tdi))

        return out

    def append_bits(self, tms_bits: List[bool], tdi_bits: List[bool]):
        if len(tms_bits) != len(tdi_bits):
            raise RuntimeError("TMS/TDI size mismatch")
        self.tms_bits.extend(tms_bits)
        self.tdi_bits.extend(tdi_bits)

    def append_repeat(self, tms: bool, tdi: bool, count: int):
        for _ in range(count):
            self.tms_bits.append(bool(tms))
            self.tdi_bits.append(bool(tdi))

    def shift_value(self, value: int, bitlen: int, exit_after: bool = True):
        for i in range(bitlen):
            bit = bool((value >> i) & 1)
            is_last_bit = (i == bitlen - 1)
            self.tms_bits.append(bool(exit_after and is_last_bit))
            self.tdi_bits.append(bit)

    def shift_instruction(self, ir: int, ir_len: int):
        # Move to Shift-IR
        self.append_repeat(1, 0, 2)  # Select-DR -> Select-IR
        self.append_repeat(0, 0, 1)  # Capture-IR
        self.append_repeat(0, 0, 1)  # Shift-IR

        # Shift IR LSB first
        self.shift_value(ir, ir_len, False)

        self.append_repeat(1, 0, 1)  # Exit IR
        self.append_repeat(1, 0, 1)  # Update-IR
        self.append_repeat(0, 0, 1)  # Run-Test/Idle

    def build_write_mem(self, ir: int, ir_len: int, dr_addr: int, dr_addr_len: int, dr_data: int, dr_data_len: int):
        self.shift_instruction(ir, ir_len)
        self.append_repeat(1, 0, 1)  # Select-DR
        self.append_repeat(0, 0, 1)  # Capture-DR
        self.append_repeat(0, 0, 1)  # Shift-DR

        # Shift DR data then address (LSB first as in the C++ driver)
        self.shift_value(dr_data, dr_data_len, False)
        self.shift_value(dr_addr, dr_addr_len, False)

        # Return to Run-Test/Idle
        self.append_repeat(1, 0, 1)  # Exit DR
        self.append_repeat(1, 0, 1)  # Update-DR
        self.append_repeat(0, 0, 1)  # Run-Test/Idle

    def build_read_mem(self, ir: int, ir_len: int, dr_addr: int, dr_addr_len: int):
        self.shift_instruction(ir, ir_len)
        self.append_repeat(1, 0, 1)  # Select-DR
        self.append_repeat(0, 0, 1)  # Capture-DR
        self.append_repeat(0, 0, 1)  # Shift-DR

        # Shift DR address
        self.shift_value(dr_addr, dr_addr_len, False)

        # Return to Run-Test/Idle
        self.append_repeat(1, 0, 1)  # Exit DR
        self.append_repeat(1, 0, 1)  # Update-DR
        self.append_repeat(0, 0, 1)  # Run-Test/Idle

    def shift_out_data(self, bitlen: int):
        # Wait for memory to process read (arbitrary cycles)
        self.append_repeat(0, 0, 5)

        # Move to Shift-DR to read data
        self.append_repeat(1, 0, 1)  # Select-DR
        self.append_repeat(0, 0, 1)  # Capture-DR
        self.append_repeat(0, 0, 1)  # Shift-DR

        # It's up to the testbench/host to clock out dummy bits if needed.

    def shift_out_data_exit(self):
        # Return to Run-Test/Idle after reading data
        self.append_repeat(1, 0, 1)  # Exit DR
        self.append_repeat(1, 0, 1)  # Update-DR
        self.append_repeat(0, 0, 2)  # Run-Test/Idle


class JTAGProg:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 1.0, verbose: bool = False):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.verbose = bool(verbose)
        self.ser = serial.Serial(port, baudrate=baud, timeout=0.01)
        # threaded reader to avoid missing RX bytes while writing
        self._rx_q: "queue.Queue[bytes]" = queue.Queue()
        self._stop_event = threading.Event()
        self._reader = threading.Thread(target=self._reader_thread, daemon=True)
        self._reader.start()

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        # stop reader thread
        try:
            self._stop_event.set()
            if hasattr(self, "_reader"):
                self._reader.join(timeout=0.1)
        except Exception:
            pass

    def _reader_thread(self):
        # continuously read single bytes and push them to the queue
        while not self._stop_event.is_set():
            try:
                b = self.ser.read(1)
                if b:
                    try:
                        self._rx_q.put(b, block=False)
                    except Exception:
                        pass
            except Exception:
                break

    def _clear_rx_queue(self):
        try:
            with self._rx_q.mutex:
                self._rx_q.queue.clear()
        except Exception:
            while not self._rx_q.empty():
                try:
                    self._rx_q.get_nowait()
                except Exception:
                    break

    def send_bytes(self, data: bytes):
        # Write and flush
        self.ser.write(data)
        self.ser.flush()

    def send_jtag_driver(self, driver: JTAGDriver):
        stream = driver.get_stream()
        data = bytes(stream)
        if getattr(self, "verbose", True):
            print(f"Sending {len(data)} bytes to {self.port}")
        self.send_bytes(data)

    def read_bytes(self, count: int, timeout_s: float = 1.0) -> bytes:
        deadline = time.time() + timeout_s
        buf = bytearray()
        while len(buf) < count and time.time() < deadline:
            chunk = self.ser.read(count - len(buf))
            if chunk:
                buf.extend(chunk)
        return bytes(buf)

    # High level helpers mirroring the C++ testbench actions
    def reset_jtag(self):
        drv = JTAGDriver()
        drv.append_repeat(1, 0, 5)
        drv.append_repeat(0, 0, 1)
        self.send_jtag_driver(drv)

    def prog_mode_on(self):
        drv = JTAGDriver()
        drv.shift_instruction(IR_MEM_CTRL, 4)
        self.send_jtag_driver(drv)

    def prog_mode_off(self):
        drv = JTAGDriver()
        drv.shift_instruction(IR_DONE, 4)
        self.send_jtag_driver(drv)

    def write_mem(self, addr: int, data: int):
        drv = JTAGDriver()
        drv.build_write_mem(IR_WRITE, 4, addr, ADDR_W, data, DATA_W)
        self.send_jtag_driver(drv)

    def read_mem(self, addr: int, expect_response_bytes: int = 6, resp_timeout: float = 1.0) -> bytes:
        # Build read command and send
        if getattr(self, "verbose", True):
            print(f"Requesting read from addr=0x{addr:02X}")
        drv = JTAGDriver()
        drv.build_read_mem(IR_READ, 4, addr, ADDR_W)
        self.send_jtag_driver(drv)
        # Prepare to shift out read data: send pre-shift control bytes, then
        # send dummy bytes (0x00) while reading one response byte per dummy
        # byte, then send the post-shift (exit) control bytes.

        # time.sleep(0.015)


        # pre-shift (enter Shift-DR and any wait cycles)
        drv_pre = JTAGDriver()
        drv_pre.shift_out_data(DR_W)
        pre_stream = drv_pre.get_stream()
        if pre_stream:
            self.send_bytes(bytes(pre_stream))

        # clear any stale data and the reader queue before starting to read response bytes
        time.sleep(0.01)
        self.ser.reset_input_buffer()
        self._clear_rx_queue()

        # send dummy bytes one at a time and read one response byte per dummy
        # time.sleep(0.005)
        # self.ser.reset_input_buffer()


        resp_buf = bytearray()

        # Send two dummy bites for each expected response byte
        self.send_bytes(b"\x00" * (expect_response_bytes * 2))

        # post-shift (exit DR back to Run-Test/Idle)
        drv_post = JTAGDriver()
        drv_post.shift_out_data_exit()
        post_stream = drv_post.get_stream()
        if post_stream:
            self.send_bytes(bytes(post_stream))
        else:
            if getattr(self, "verbose", True):
                print("Warning: no post-shift stream generated")

        # Drain any bytes in the reader queue into resp_buf
        # (capture all bytes received since last clear)
        try:
            # brief pause to allow any in-flight bytes to arrive
            time.sleep(0.01)
        except Exception:
            pass

        # Drain queue without blocking
        while True:
            try:
                b = self._rx_q.get_nowait()
            except queue.Empty:
                break
            resp_buf.extend(b)

        # Print debug info: bytes and count
        # print(f"Received {len(resp_buf)} bytes: {resp_buf.hex()}")

        return bytes(resp_buf)


def load_32bit_hex_file(path: str) -> List[int]:
    out: List[int] = []
    with open(path, "r") as f:
        for ln in f:
            s = ln.strip()
            if not s:
                continue
            # allow 0x prefix or plain hex
            if s.startswith("0x") or s.startswith("0X"):
                s = s[2:]
            # remove comments after a space
            if " " in s:
                s = s.split(" ", 1)[0]
            try:
                val = int(s, 16) & 0xFFFFFFFF
            except ValueError:
                raise ValueError(f"Invalid hex in data file: {ln.strip()}")
            out.append(val)
    return out

## Genearate some dummy data for testing instead of loading from file
def generate_dummy_data(count: int, seed: int) -> List[int]:
    r = random.Random(seed)
    return [r.getrandbits(32) for _ in range(count)]

def human_bytes(num_bytes: int) -> str:
    """Convert bytes to human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if num_bytes < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} TB"

def reconstruct_data_from_response(resp: bytes) -> int:
    # Reconstruct data (bytes 0..3 are data LSB..MSB)
    # return value and address separately
    data_val = 0
    for j in range(3, -1, -1):
        data_val <<= 8
        data_val |= resp[j]
    addr_val = (resp[5] << 8) | resp[4]
    return data_val, addr_val


def main():
    parser = argparse.ArgumentParser(description="Host JTAG UART programmer")
    parser.add_argument("port", help="Serial port to open (e.g. /dev/ttyUSB0)")
    parser.add_argument("datafile", nargs='?', help="Text file containing 32-bit hex words, one per line (required unless --test-mode is used)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate for the serial port")
    parser.add_argument("--start-addr", type=int, default=0)
    parser.add_argument("--verbose", action="store_true", help="Enable verbose JTAG driver prints")
    parser.add_argument("--test-mode", action="store_true", help="Run in test mode with generated dummy data instead of loading from file")
    parser.add_argument("--word-count", type=int, default=128, help="Number of words to generate in test mode (default 128)")
    args = parser.parse_args()

    # Validate that datafile is provided if not in test mode
    if not args.test_mode and not args.datafile:
        parser.error("datafile is required unless --test-mode is used")

    # For testing, generate some dummy data instead of loading from file
    if args.test_mode:
        words = generate_dummy_data(args.word_count, seed=42)
    else:
        words = load_32bit_hex_file(args.datafile)


    p = JTAGProg(args.port, baud=args.baud, verbose=args.verbose)
    try:
        print("Resetting JTAG TAP...")
        p.reset_jtag()
        time.sleep(0.05)
        print("Entering programming mode...")
        p.prog_mode_on()


        # progress counters
        written_so_far = 0
        verified_so_far = 0
        # throttle updates to a reasonable number (approx 200 updates)
        write_update_interval = max(1, len(words) // 200)
        read_update_interval = max(1, len(words) // 200)

        def _print_progress(stage: str, current: int, total: int):
            pct = (current * 100.0 / total) if total else 100.0
            # carriage-return update
            sys.stdout.write(f"\r{stage}: {pct:6.2f}% ({current}/{total})")
            sys.stdout.flush()

        # write words sequentially starting at start-addr
        t0 = time.time()
        for i, w in enumerate(words):
            addr = args.start_addr + i
            if getattr(p, "verbose", True):
                print(f"Writing addr=0x{addr:02X} data=0x{w:08X}")
            p.write_mem(addr, w)
            written_so_far += 1
            # throttled progress update
            if written_so_far % write_update_interval == 0 or (i + 1) == len(words):
                _print_progress("Writing", written_so_far, len(words))
            time.sleep(0.005)

        t1 = time.time()
        write_time = t1 - t0

        sys.stdout.write("\n\n")
        # Read and verify all the written words
        print("Verifying all entries...")
        errors = 0
        for i in range(len(words)):
            addr = args.start_addr + i
            resp = p.read_mem(addr, expect_response_bytes=6, resp_timeout=0.5)
            verified_so_far += 1
            # throttled progress update
            if (verified_so_far % read_update_interval) == 0 or verified_so_far == len(words):
                _print_progress("Verifying", verified_so_far, len(words))
            if len(resp) < 6:
                print(f"Addr 0x{addr:02X}: no response (len={len(resp)})")
                continue
            data_val, addr_resp = reconstruct_data_from_response(resp)
            expected_val = words[i]
            if addr_resp != addr or data_val != expected_val:
                print(f"Addr 0x{addr:02X}: MISMATCH! Expected 0x{expected_val:08X}, got 0x{data_val:08X}")
                errors += 1
            else:
                if getattr(p, "verbose", True):
                    print(f"Addr 0x{addr:02X}: OK Data: 0x{data_val:08X}")

        read_time = time.time() - t1

        sys.stdout.write("\n\n")

        print(f"Verification complete. Errors found: {errors}")
        print("Exiting programming mode...")
        p.prog_mode_off()


        print("\nSummary:")
        print(f"  Total words: {len(words)}")
        print(f"  Total bytes: {len(words)*4} ({human_bytes(len(words)*4)})")
        print(f"  Total write time: {write_time:.3f}s")
        if write_time > 0:
            print(f"  Write throughput: {(len(words)*4)/1024/write_time:.2f} KB/s")
        print(f"  Total read time: {read_time:.3f}s")
        if read_time > 0:
            print(f"  Read throughput: {(len(words)*4)/1024/read_time:.2f} KB/s")
        print(f"  Total errors: {errors}")

        if errors:
            print("One or more verification errors detected.")
            sys.exit(2)
        else:
            print("All data verified successfully.")

    finally:
        p.close()


if __name__ == "__main__":
    main()
