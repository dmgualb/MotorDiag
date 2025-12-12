#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serial Control Module
Handles serial port communication for the Breath Collect Application
"""

import serial
import time


def current_millis():
    """Get current time in milliseconds"""
    return int(time.time() * 1000)


class SerialCtrl:
    """Class to manage serial port communication"""
    
    def __init__(self, port: str, baudrate: int):
        self.port = port
        self.baudrate = baudrate
        self.serial_connection: serial.Serial | None = None

    def OpenConnection(self):
        """Open the serial port connection"""
        if not self.IsConnected():
            try:
                self.serial_connection = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=1
                )
                print(f"Connected to {self.port} at {self.baudrate} baud")
            except Exception as e:
                print(f"Error opening serial port: {e}")
                self.serial_connection = None
        else:
            print("Already connected!")

    def CloseConnection(self):
        """Close the serial port connection"""
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
            print("Connection closed.")
            self.serial_connection = None
        else:
            print("The connection is not opened.")

    def IsConnected(self) -> bool:
        """Check if the serial port is connected"""
        return self.serial_connection is not None and self.serial_connection.is_open

    def SendString(self, utf8_string: str, quiet: bool = False):
        """Send a UTF-8 string over the serial port"""
        self.SendBytes(utf8_string.encode('utf-8'), quiet)
            
    def SendBytes(self, data: bytes, quiet: bool = False):
        """Send raw bytes over the serial port"""
        if not self.serial_connection or not self.serial_connection.is_open:
            raise ConnectionError("Device not connected.")
        try:
            bytes_written = self.serial_connection.write(data)
            if not quiet:
                print(f"Bytes written: {bytes_written}")
                print(f"Data sent (hex): {data.hex()}")
        except Exception as e:
            if not quiet:
                print(f"Error sending data: {e}")

    def ReceiveBytesByTimeout(self, timeout_ms: int, quiet: bool = False) -> bytes:
        """Receive bytes from the serial port with timeout"""
        if not self.serial_connection or not self.serial_connection.is_open:
            raise ConnectionError("Device not connected.")
        try:
            original_timeout = self.serial_connection.timeout
            self.serial_connection.timeout = timeout_ms / 1000.0
            
            data = self.serial_connection.read_until(b'\n')  # Read until newline or timeout
            
            self.serial_connection.timeout = original_timeout
            
            if data:
                if not quiet:
                    print(f"Data received (hex): {data.hex()}")
                    print(f"Data received (ascii): {data.decode('utf-8', errors='ignore').strip()}")
                return data
            else:
                if not quiet:
                    print("Timeout reached without receiving data.")
                return b''
        except Exception as e:
            if not quiet:
                print(f"Error receiving data: {e}")
            return b''
        
    def ReceiveMessageByTimeout(self, timeout_ms: int, quiet: bool = False) -> str:
        return self.ReceiveBytesByTimeout(timeout_ms, quiet).decode('latin-1', errors='ignore') 
        
    # will return feweer bytes than requested if timeout occurs
    def ReceiveMessageBySize(self, size: int, timeout_ms: int = 100, quiet: bool = False) -> str:
        """Receive a message from the serial port with timeout"""
        if not self.serial_connection or not self.serial_connection.is_open:
            raise ConnectionError("Device not connected.")
        try:
            original_timeout = self.serial_connection.timeout
            self.serial_connection.timeout = timeout_ms / 1000.0
            
            data = self.serial_connection.read(size)  # Read fixed size or timeout
            
            self.serial_connection.timeout = original_timeout
            
            if data:
                if not quiet:
                    print(f"Data received (hex): {data.hex()}")
                    print(f"Data received (ascii): {data.decode('latin-1', errors='ignore').strip()}")
                return data.decode('latin-1', errors='ignore')
            else:
                if not quiet:
                    print("Timeout reached without receiving data.")
                return ""
        except Exception as e:
            if not quiet:
                print(f"Error receiving data: {e}")
            return ""    
        
        
    def ReceiveAvailableMessage(self, quiet: bool = False) -> str:
        """Receive all available data from the serial port"""
        if not self.serial_connection or not self.serial_connection.is_open:
            raise ConnectionError("Device not connected.")
        try:
            available_bytes = self.serial_connection.in_waiting
            if available_bytes > 0:
                data = self.serial_connection.read(available_bytes)
                if not quiet:
                    print(f"Data received (hex): {data.hex()}")
                    print(f"Data received (ascii): {data.decode('latin-1', errors='ignore').strip()}")
                return data.decode('latin-1', errors='ignore')
            else:
                if not quiet:
                    print("No data available to read.")
                return ""
        except Exception as e:
            if not quiet:
                print(f"Error receiving data: {e}")
            return ""
    
    def CheckResponse(self, expected_response: str, timeout_ms: int = 100, quiet: bool = False) -> bool:
        """Check if the expected response is received within the timeout"""
        iniTime = current_millis()

        response = self.ReceiveMessageBySize(len(expected_response), timeout_ms, quiet)
        if response == expected_response:
            if not quiet:
                print("Expected response received.")
            return True
        else:
            while current_millis() - iniTime < timeout_ms:
                adittional_response = self.ReceiveMessageBySize(1, timeout_ms, quiet)
                response += adittional_response
                if expected_response in response:
                    if not quiet:
                        print(f"Expected response {expected_response} received.")
                    return True 
            if not quiet:
                print(f"Unexpected response: '{response}' (expected: '{expected_response}')")
            return False
        
    def CheckResponses(self, expected_responses: list, timeout_ms: int = 100, quiet: bool = False) -> str:
        """Check if the expected response is received within the timeout"""
        iniTime = current_millis()

        minLen= min(len(resp) for resp in expected_responses)

        response = self.ReceiveMessageBySize(minLen, timeout_ms, quiet)

        for expected_response in expected_responses:
            if response == expected_response:
                if not quiet:
                    print(f"Expected response {expected_response} received.")
                return expected_response
            
        while current_millis() - iniTime < timeout_ms:
            adittional_response = self.ReceiveMessageBySize(1, timeout_ms, quiet)
            response += adittional_response
            for expected_response in expected_responses:
                if expected_response in response:
                    if not quiet:
                        print(f"Expected response {expected_response} received.")
                    return expected_response 
        if not quiet:
            print(f"Unexpected response: '{response}' (expected: '{expected_response}')")
        return None
        
    def SendFixedCommandRetry(self, command: str, expected_response: str, retries: int = 3, timeout : int = 100, quiet: bool = False) -> bool:
        """Send a fixed command with retries"""
        for attempt in range(retries):
            try:
                self.SendBytes(command.encode('latin-1'), quiet)
                if not quiet:
                    print(f"Command sent successfully on attempt {attempt + 1}")
                if self.CheckResponse(expected_response, timeout, quiet):
                    return True
            except Exception as e:
                if not quiet:
                    print(f"Attempt {attempt + 1} failed: {e}")
        if not quiet:
            print("All attempts to send command failed.")
        return False
        
    def SendCommandWithMultipleResponsesRetry(self, command: str, expected_responses: list, retries: int = 3, quiet: bool = False) -> str:
        """Send a command and wait for one of multiple expected responses"""
        for attempt in range(retries):
            try:
                self.SendBytes(command.encode('latin-1'), quiet)
                if not quiet:
                    print(f"Command sent successfully on attempt {attempt + 1}")

                response = self.CheckResponses(expected_responses, 100, quiet)
                if response:
                    if not quiet:
                        print("Expected response received.")
                    return response                 

            except Exception as e:
                if not quiet:
                    print(f"Attempt {attempt + 1} failed: {e}")
        if not quiet:
            print("All attempts to send command failed.")
        return None

