import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QComboBox, QPushButton, QTableWidget, 
                               QTableWidgetItem, QSplitter)
from PySide6.QtCore import Qt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import serial.tools.list_ports
import serial_ctrl

# Constants
BAUDRATE = 57600  # Serial port baudrate


class MotorDiagWindow(QMainWindow):
    """Main window for Motor Diagnostics application"""
    
    def __init__(self):
        super().__init__()
        self.serial_ctrl = None
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Motor Diagnostics")
        self.setGeometry(100, 100, 1200, 800)
        
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Top section: Serial port controls
        top_layout = QHBoxLayout()
        
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(200)
        self.port_combo.setMaximumHeight(30)
        top_layout.addWidget(self.port_combo)
        
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setMaximumHeight(30)
        self.refresh_btn.clicked.connect(self.refresh_ports)
        top_layout.addWidget(self.refresh_btn)
        
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        self.connect_btn.setMaximumHeight(30)
        top_layout.addWidget(self.connect_btn)
        
        top_layout.addStretch()
        
        # Set initial button style
        self.update_connection_ui(False)
        main_layout.addLayout(top_layout)
        
        # Middle section: Table and Plot side by side
        middle_splitter = QSplitter(Qt.Horizontal)
        
        # Create table (1/3 width)
        self.table = QTableWidget(200, 4)
        self.table.setHorizontalHeaderLabels(['X', 'Y0', 'Y1', 'Y2'])
        
        # Hide the row index column
        self.table.verticalHeader().setVisible(False)
        
        # Set column widths to ensure all columns are visible
        self.table.setColumnWidth(0, 40)   # X column
        self.table.setColumnWidth(1, 80)   # Y0 column
        self.table.setColumnWidth(2, 80)   # Y1 column
        self.table.setColumnWidth(3, 80)   # Y2 column
        
        # Set minimum width to show all columns (40+80+80+80 + scrollbar ~20 + margins)
        self.table.setMinimumWidth(320)
        
        # Pre-fill X column with values 0-199
        for row in range(200):
            self.table.setItem(row, 0, QTableWidgetItem(str(row)))
        
        middle_splitter.addWidget(self.table)
        
        # Create matplotlib plot (2/3 width)
        self.figure = Figure(figsize=(8, 6))
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_xlabel('X')
        self.ax.set_ylabel('Y')
        self.ax.set_title('Motor Data')
        self.ax.grid(True)
        
        middle_splitter.addWidget(self.canvas)
        
        # Set stretch factors for 1/3 and 2/3 width
        middle_splitter.setStretchFactor(0, 1)  # Table
        middle_splitter.setStretchFactor(1, 2)  # Plot
        
        main_layout.addWidget(middle_splitter)
        
        # Bottom section: Read buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        
        self.read_y0_btn = QPushButton("Read Y0")
        self.read_y0_btn.clicked.connect(self.read_y0)
        bottom_layout.addWidget(self.read_y0_btn)
        
        self.read_y1_btn = QPushButton("Read Y1")
        self.read_y1_btn.clicked.connect(self.read_y1)
        bottom_layout.addWidget(self.read_y1_btn)
        
        self.read_y2_btn = QPushButton("Read Y2")
        self.read_y2_btn.clicked.connect(self.read_y2)
        bottom_layout.addWidget(self.read_y2_btn)
        
        self.ac_toggle_btn = QPushButton("Disable AC")
        self.ac_toggle_btn.clicked.connect(self.toggle_ac)
        bottom_layout.addWidget(self.ac_toggle_btn)
        
        bottom_layout.addStretch()
        main_layout.addLayout(bottom_layout)
        
        # Track AC state (True = enabled, False = disabled)
        self.ac_enabled = True
        
        # Initial port refresh
        self.refresh_ports()
        
    def refresh_ports(self):
        """Refresh the list of available serial ports"""
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.port_combo.addItem(f"{port.device} - {port.description}", port.device)
    
    def toggle_connection(self):
        """Connect or disconnect from the serial port"""
        if self.serial_ctrl is None or not self.serial_ctrl.IsConnected():
            # Connect
            if self.port_combo.count() == 0:
                print("No serial ports available")
                return
            
            port = self.port_combo.currentData()
            if port:
                self.serial_ctrl = serial_ctrl.SerialCtrl(port, BAUDRATE)
                self.serial_ctrl.OpenConnection()
                
                if self.serial_ctrl.IsConnected():
                    self.update_connection_ui(True)
        else:
            # Disconnect
            self.serial_ctrl.CloseConnection()
            self.update_connection_ui(False)
    
    def update_connection_ui(self, connected):
        """Update UI elements based on connection state"""
        if connected:
            self.connect_btn.setText("Disconnect")
            self.connect_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
            self.port_combo.setEnabled(False)
            self.refresh_btn.setEnabled(False)
        else:
            self.connect_btn.setText("Connect")
            self.connect_btn.setStyleSheet("background-color: #CCCCCC;")
            self.port_combo.setEnabled(True)
            self.refresh_btn.setEnabled(True)
    
    def read_y0(self):
        """Read Y0 data from serial port"""
        if not self.serial_ctrl or not self.serial_ctrl.IsConnected():
            print("Not connected to serial port")
            return
        
        try:
            # Clean buffer before sending command
            self.serial_ctrl.ReceiveAvailableMessage(quiet=True)
            self.serial_ctrl.SendString("<GV:0>")
            self.receive_data_response(0)  # Column 1 for Y0
        except Exception as e:
            print(f"Error reading Y0: {e}")
        
    def read_y1(self):
        """Read Y1 data from serial port"""
        if not self.serial_ctrl or not self.serial_ctrl.IsConnected():
            print("Not connected to serial port")
            return
        
        try:
            # Clean buffer before sending command
            self.serial_ctrl.ReceiveAvailableMessage(quiet=True)
            self.serial_ctrl.SendString("<GV:1>")
            self.receive_data_response(1)  # Column 2 for Y1
        except Exception as e:
            print(f"Error reading Y1: {e}")
        
    def read_y2(self):
        """Read Y2 data from serial port"""
        if not self.serial_ctrl or not self.serial_ctrl.IsConnected():
            print("Not connected to serial port")
            return
        
        try:
            # Clean buffer before sending command
            self.serial_ctrl.ReceiveAvailableMessage(quiet=True)
            self.serial_ctrl.SendString("<GV:2>")
            self.receive_data_response(2)  # Column 3 for Y2
        except Exception as e:
            print(f"Error reading Y2: {e}")
    
    def toggle_ac(self):
        """Toggle AC enable/disable"""
        if not self.serial_ctrl or not self.serial_ctrl.IsConnected():
            print("Not connected to serial port")
            return
        
        try:
            # Clean buffer before sending command
            self.serial_ctrl.ReceiveAvailableMessage(quiet=True)
            
            if self.ac_enabled:
                # Disable AC
                success = self.serial_ctrl.SendFixedCommandRetry("<CA:0>", "<CA:0>", 2)
                if success:
                    self.ac_enabled = False
                    self.ac_toggle_btn.setText("Enable AC")
                    print("AC disabled successfully")
                else:
                    print("Failed to disable AC")
            else:
                # Enable AC
                success = self.serial_ctrl.SendFixedCommandRetry("<CA:1>", "<CA:1>", 2)
                if success:
                    self.ac_enabled = True
                    self.ac_toggle_btn.setText("Disable AC")
                    print("AC enabled successfully")
                else:
                    print("Failed to enable AC")
        except Exception as e:
            print(f"Error toggling AC: {e}")
    
    def receive_data_response(self, column_index):
        """
        Receive data response from serial port and populate the table column
        
        Args:
            column_index: The column to populate (0=Y0, 1=Y1, 2=Y2)
        """
        print(f"Waiting for response for column Y{column_index}...")
        
        try:
            # Receive 20 blocks of data
            for block_num in range(20):
                # Expected header for this block
                expected_header = f"<{block_num:02d}:"
                
                # Check for block header
                if not self.serial_ctrl.CheckResponse(expected_header):
                    self.serial_ctrl.ReceiveAvailableMessage(quiet=True)  # Clean buffer
                    print(f"Error: Expected header '{expected_header}' not received. Operation aborted.")
                    return
                
                # Read 10 hex values (40 characters: 10 values * 4 chars each)
                hex_data = self.serial_ctrl.ReceiveMessageBySize(40, timeout_ms=25, quiet=True)
                
                # Check if the message only contanins hexadecimal characters
                if not all(c in "0123456789ABCDEFabcdef" for c in hex_data):
                    self.serial_ctrl.ReceiveAvailableMessage(quiet=True)  # Clean buffer
                    print(f"Error: Non-hexadecimal data received in block {block_num}. Operation aborted.")
                    return

                if len(hex_data) != 40:
                    self.serial_ctrl.ReceiveAvailableMessage(quiet=True)  # Clean buffer
                    print(f"Error: Incomplete data in block {block_num}. Expected 40 characters, got {len(hex_data)}. Operation aborted.")
                    return
                
                # Check for closing '>'
                closing_char = self.serial_ctrl.ReceiveMessageBySize(1, timeout_ms=25, quiet=True)
                if closing_char != '>':
                    self.serial_ctrl.ReceiveAvailableMessage(quiet=True)  # Clean buffer
                    print(f"Error: Expected '>' at end of block {block_num}, got '{closing_char}'. Operation aborted.")
                    return
                
                # Parse the 10 hex values and populate table
                try:
                    for value_idx in range(10):
                        # Extract 4-character hex value
                        hex_value = hex_data[value_idx * 4:(value_idx * 4) + 4]
                        
                        # Convert to signed 16-bit integer
                        unsigned_value = int(hex_value, 16)
                        # Convert to signed (two's complement)
                        if unsigned_value >= 0x8000:
                            signed_value = unsigned_value - 0x10000
                        else:
                            signed_value = unsigned_value
                        
                        # Calculate row in table (block_num * 10 + value_idx)
                        row = block_num * 10 + value_idx
                        
                        # Populate table cell (column_index + 1 because column 0 is X)
                        self.table.setItem(row, column_index + 1, QTableWidgetItem(str(signed_value)))
                        
                except ValueError as e:
                    self.serial_ctrl.ReceiveAvailableMessage(quiet=True)  # Clean buffer
                    print(f"Error parsing hex data in block {block_num}: {e}. Operation aborted.")
                    return
            
            print(f"Successfully received all data for Y{column_index}")
            # Update the plot with new data
            self.update_plot()
            
        except Exception as e:
            self.serial_ctrl.ReceiveAvailableMessage(quiet=True)  # Clean buffer
            print(f"Error receiving data: {e}. Operation aborted.")
            return
    
    def update_plot(self):
        """Update the matplotlib plot with current data"""
        self.ax.clear()
        self.ax.set_xlabel('X')
        self.ax.set_ylabel('Y')
        self.ax.set_title('Motor Data')
        self.ax.grid(True)
        
        # Extract data from table
        x_data = []
        y0_data = []
        y1_data = []
        y2_data = []
        
        for row in range(self.table.rowCount()):
            x_item = self.table.item(row, 0)
            y0_item = self.table.item(row, 1)
            y1_item = self.table.item(row, 2)
            y2_item = self.table.item(row, 3)
            
            if x_item and x_item.text():
                x_data.append(float(x_item.text()))
                
                if y0_item and y0_item.text():
                    y0_data.append(float(y0_item.text()))
                if y1_item and y1_item.text():
                    y1_data.append(float(y1_item.text()))
                if y2_item and y2_item.text():
                    y2_data.append(float(y2_item.text()))
        
        # Plot data
        if y0_data:
            self.ax.plot(x_data[:len(y0_data)], y0_data, 'b-', label='Y0')
        if y1_data:
            self.ax.plot(x_data[:len(y1_data)], y1_data, 'r-', label='Y1')
        if y2_data:
            self.ax.plot(x_data[:len(y2_data)], y2_data, 'g-', label='Y2')
        
        if y0_data or y1_data or y2_data:
            self.ax.legend()
        
        self.canvas.draw()


def main():
    """Main entry point for the application"""
    app = QApplication(sys.argv)
    window = MotorDiagWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
