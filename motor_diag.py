import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QComboBox, QPushButton, QTableWidget, 
                               QTableWidgetItem, QSplitter)
from PySide6.QtCore import Qt, QThread, Signal
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import serial.tools.list_ports
import serial_ctrl

# Constants
BAUDRATE = 57600  # Serial port baudrate


class DataReaderThread(QThread):
    """Thread for reading serial data without blocking the UI"""
    data_received = Signal(int, list)  # Signal(column_index, list of values)
    error_occurred = Signal(str)  # Signal(error_message)
    
    def __init__(self, serial_ctrl, column_index):
        super().__init__()
        self.serial_ctrl = serial_ctrl
        self.column_index = column_index
        
    def run(self):
        """Read data from serial port in background thread"""
        try:
            values = []
            
            # Receive 20 blocks of data
            for block_num in range(20):
                # Expected header for this block
                expected_header = f"<{block_num:02d}:"
                
                # Check for block header
                if not self.serial_ctrl.CheckResponse(expected_header):
                    self.serial_ctrl.ReceiveAvailableMessage(quiet=True)
                    self.error_occurred.emit(f"Expected header '{expected_header}' not received. Operation aborted.")
                    return
                
                # Read 10 hex values (40 characters: 10 values * 4 chars each)
                hex_data = self.serial_ctrl.ReceiveMessageBySize(40, timeout_ms=25, quiet=True)
                
                # Check if the message only contains hexadecimal characters
                if not all(c in "0123456789ABCDEFabcdef" for c in hex_data):
                    self.serial_ctrl.ReceiveAvailableMessage(quiet=True)
                    self.error_occurred.emit(f"Non-hexadecimal data received in block {block_num}. Operation aborted.")
                    return

                if len(hex_data) != 40:
                    self.serial_ctrl.ReceiveAvailableMessage(quiet=True)
                    self.error_occurred.emit(f"Incomplete data in block {block_num}. Expected 40 characters, got {len(hex_data)}. Operation aborted.")
                    return
                
                # Check for closing '>'
                closing_char = self.serial_ctrl.ReceiveMessageBySize(1, timeout_ms=25, quiet=True)
                if closing_char != '>':
                    self.serial_ctrl.ReceiveAvailableMessage(quiet=True)
                    self.error_occurred.emit(f"Expected '>' at end of block {block_num}, got '{closing_char}'. Operation aborted.")
                    return
                
                # Parse the 10 hex values
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
                    
                    values.append(signed_value)
            
            # Emit signal with all received data
            self.data_received.emit(self.column_index, values)
            
        except ValueError as e:
            self.serial_ctrl.ReceiveAvailableMessage(quiet=True)
            self.error_occurred.emit(f"Error parsing hex data: {e}. Operation aborted.")
        except Exception as e:
            self.serial_ctrl.ReceiveAvailableMessage(quiet=True)
            self.error_occurred.emit(f"Error receiving data: {e}. Operation aborted.")


class MotorDiagWindow(QMainWindow):
    """Main window for Motor Diagnostics application"""
    
    def __init__(self):
        super().__init__()
        self.serial_ctrl = None
        self.ax2 = None  # Secondary axis for Y2
        self.ax3 = None  # Secondary axis for Y3
        self.ax4 = None  # Secondary axis for Y4
        self.reader_thread = None  # Thread for reading serial data
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
        main_layout.addLayout(top_layout)
        
        # Middle section: Table and Plot side by side
        middle_splitter = QSplitter(Qt.Horizontal)
        
        # Create table (1/3 width)
        self.table = QTableWidget(200, 6)
        self.table.setHorizontalHeaderLabels(['X', 'Y0', 'Y1', 'Y2', 'Y3', 'Y4'])
        
        # Hide the row index column
        self.table.verticalHeader().setVisible(False)
        
        # Set column widths to ensure all columns are visible
        self.table.setColumnWidth(0, 40)   # X column
        self.table.setColumnWidth(1, 60)   # Y0 column
        self.table.setColumnWidth(2, 60)   # Y1 column
        self.table.setColumnWidth(3, 60)   # Y2 column
        self.table.setColumnWidth(4, 60)   # Y3 column
        self.table.setColumnWidth(5, 60)   # Y4 column
        
        # Set minimum width to show all columns (40+60+60+60+60+60 + scrollbar ~20 + margins)
        self.table.setMinimumWidth(40+60*5 + 20 + 20)
        
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
        
        self.read_y3_btn = QPushButton("Read Y3")
        self.read_y3_btn.clicked.connect(self.read_y3)
        bottom_layout.addWidget(self.read_y3_btn)
        
        self.read_y4_btn = QPushButton("Read Y4")
        self.read_y4_btn.clicked.connect(self.read_y4)
        bottom_layout.addWidget(self.read_y4_btn)
        
        self.ac_toggle_btn = QPushButton("Disable AC")
        self.ac_toggle_btn.clicked.connect(self.toggle_ac)
        bottom_layout.addWidget(self.ac_toggle_btn)
        
        self.fill_speed_btn = QPushButton("Fill Speed")
        self.fill_speed_btn.clicked.connect(self.fill_speed)
        bottom_layout.addWidget(self.fill_speed_btn)
        
        self.copy_btn = QPushButton("Copy Table")
        self.copy_btn.clicked.connect(self.copy_table_to_clipboard)
        bottom_layout.addWidget(self.copy_btn)
        
        bottom_layout.addStretch()
        main_layout.addLayout(bottom_layout)
        
        # Track AC state (True = enabled, False = disabled)
        self.ac_enabled = True
        
        # Set initial button style (after all buttons are created)
        self.update_connection_ui(False)
        
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
            self.read_y0_btn.setEnabled(True)
            self.read_y1_btn.setEnabled(True)
            self.read_y2_btn.setEnabled(True)
            self.read_y3_btn.setEnabled(True)
            self.read_y4_btn.setEnabled(True)
            self.ac_toggle_btn.setEnabled(True)
            self.fill_speed_btn.setEnabled(True)
        else:
            self.connect_btn.setText("Connect")
            self.connect_btn.setStyleSheet("background-color: #CCCCCC;")
            self.port_combo.setEnabled(True)
            self.refresh_btn.setEnabled(True)
            self.read_y0_btn.setEnabled(False)
            self.read_y1_btn.setEnabled(False)
            self.read_y2_btn.setEnabled(False)
            self.read_y3_btn.setEnabled(False)
            self.read_y4_btn.setEnabled(False)
            self.ac_toggle_btn.setEnabled(False)
            self.fill_speed_btn.setEnabled(False)
    
    def read_y0(self):
        """Read Y0 data from serial port"""
        if not self.serial_ctrl or not self.serial_ctrl.IsConnected():
            print("Not connected to serial port")
            return
        
        # Don't start a new read if one is already in progress
        if self.reader_thread and self.reader_thread.isRunning():
            print("Data read already in progress")
            return
        
        try:
            # Clean buffer before sending command
            self.serial_ctrl.ReceiveAvailableMessage(quiet=True)
            self.serial_ctrl.SendString("<GV:0>")
            
            # Start background thread to read data
            self.reader_thread = DataReaderThread(self.serial_ctrl, 0)
            self.reader_thread.data_received.connect(self.on_data_received)
            self.reader_thread.error_occurred.connect(self.on_error_occurred)
            self.reader_thread.start()
            print("Reading Y0 data...")
        except Exception as e:
            print(f"Error reading Y0: {e}")
        
    def read_y1(self):
        """Read Y1 data from serial port"""
        if not self.serial_ctrl or not self.serial_ctrl.IsConnected():
            print("Not connected to serial port")
            return
        
        # Don't start a new read if one is already in progress
        if self.reader_thread and self.reader_thread.isRunning():
            print("Data read already in progress")
            return
        
        try:
            # Clean buffer before sending command
            self.serial_ctrl.ReceiveAvailableMessage(quiet=True)
            self.serial_ctrl.SendString("<GV:1>")
            
            # Start background thread to read data
            self.reader_thread = DataReaderThread(self.serial_ctrl, 1)
            self.reader_thread.data_received.connect(self.on_data_received)
            self.reader_thread.error_occurred.connect(self.on_error_occurred)
            self.reader_thread.start()
            print("Reading Y1 data...")
        except Exception as e:
            print(f"Error reading Y1: {e}")
        
    def read_y2(self):
        """Read Y2 data from serial port"""
        if not self.serial_ctrl or not self.serial_ctrl.IsConnected():
            print("Not connected to serial port")
            return
        
        # Don't start a new read if one is already in progress
        if self.reader_thread and self.reader_thread.isRunning():
            print("Data read already in progress")
            return
        
        try:
            # Clean buffer before sending command
            self.serial_ctrl.ReceiveAvailableMessage(quiet=True)
            self.serial_ctrl.SendString("<GV:2>")
            
            # Start background thread to read data
            self.reader_thread = DataReaderThread(self.serial_ctrl, 2)
            self.reader_thread.data_received.connect(self.on_data_received)
            self.reader_thread.error_occurred.connect(self.on_error_occurred)
            self.reader_thread.start()
            print("Reading Y2 data...")
        except Exception as e:
            print(f"Error reading Y2: {e}")
    
    def read_y3(self):
        """Read Y3 data from serial port"""
        if not self.serial_ctrl or not self.serial_ctrl.IsConnected():
            print("Not connected to serial port")
            return
        
        # Don't start a new read if one is already in progress
        if self.reader_thread and self.reader_thread.isRunning():
            print("Data read already in progress")
            return
        
        try:
            # Clean buffer before sending command
            self.serial_ctrl.ReceiveAvailableMessage(quiet=True)
            self.serial_ctrl.SendString("<GV:3>")
            
            # Start background thread to read data
            self.reader_thread = DataReaderThread(self.serial_ctrl, 3)
            self.reader_thread.data_received.connect(self.on_data_received)
            self.reader_thread.error_occurred.connect(self.on_error_occurred)
            self.reader_thread.start()
            print("Reading Y3 data...")
        except Exception as e:
            print(f"Error reading Y3: {e}")
    
    def read_y4(self):
        """Read Y4 data from serial port"""
        if not self.serial_ctrl or not self.serial_ctrl.IsConnected():
            print("Not connected to serial port")
            return
        
        # Don't start a new read if one is already in progress
        if self.reader_thread and self.reader_thread.isRunning():
            print("Data read already in progress")
            return
        
        try:
            # Clean buffer before sending command
            self.serial_ctrl.ReceiveAvailableMessage(quiet=True)
            self.serial_ctrl.SendString("<GV:4>")
            
            # Start background thread to read data
            self.reader_thread = DataReaderThread(self.serial_ctrl, 4)
            self.reader_thread.data_received.connect(self.on_data_received)
            self.reader_thread.error_occurred.connect(self.on_error_occurred)
            self.reader_thread.start()
            print("Reading Y4 data...")
        except Exception as e:
            print(f"Error reading Y4: {e}")
    
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
    
    def fill_speed(self):
        """Send Fill Speed command"""
        if not self.serial_ctrl or not self.serial_ctrl.IsConnected():
            print("Not connected to serial port")
            return
        
        try:
            # Clean buffer before sending command
            self.serial_ctrl.ReceiveAvailableMessage(quiet=True)
            success = self.serial_ctrl.SendFixedCommandRetry("<FS>", "<FS>", 2)
            if success:
                print("Fill Speed command sent successfully")
            else:
                print("Failed to send Fill Speed command")
        except Exception as e:
            print(f"Error sending Fill Speed: {e}")
    
    def copy_table_to_clipboard(self):
        """Copy table data to clipboard in tab-separated format"""
        try:
            # Build tab-separated text
            rows = []
            # Add header
            headers = []
            for col in range(self.table.columnCount()):
                headers.append(self.table.horizontalHeaderItem(col).text())
            rows.append("\t".join(headers))
            
            # Add data rows
            for row in range(self.table.rowCount()):
                row_data = []
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col)
                    row_data.append(item.text() if item and item.text() else "")
                rows.append("\t".join(row_data))
            
            # Copy to clipboard
            clipboard_text = "\n".join(rows)
            QApplication.clipboard().setText(clipboard_text)
            print("Table copied to clipboard")
        except Exception as e:
            print(f"Error copying table: {e}")
    
    def on_data_received(self, column_index, values):
        """
        Callback when data is received from background thread
        
        Args:
            column_index: The column to populate (0=Y0, 1=Y1, 2=Y2)
            values: List of 200 integer values
        """
        try:
            # Populate table cells
            for row, value in enumerate(values):
                self.table.setItem(row, column_index + 1, QTableWidgetItem(str(value)))
            
            print(f"Successfully received all data for Y{column_index}")
            # Update the plot with new data
            self.update_plot()
            
        except Exception as e:
            print(f"Error populating table: {e}")
    
    def on_error_occurred(self, error_message):
        """
        Callback when error occurs in background thread
        
        Args:
            error_message: The error message
        """
        print(f"Error: {error_message}")
    
    def update_plot(self):
        """Update the matplotlib plot with current data"""
        self.ax.clear()
        
        # Clear all secondary axes if they exist
        if self.ax2 is not None:
            self.ax2.clear()
            self.ax2.remove()
            self.ax2 = None
        if self.ax3 is not None:
            self.ax3.clear()
            self.ax3.remove()
            self.ax3 = None
        if self.ax4 is not None:
            self.ax4.clear()
            self.ax4.remove()
            self.ax4 = None
        
        self.ax.set_xlabel('X')
        self.ax.set_ylabel('Y0 / Y1', color='black')
        self.ax.set_title('Motor Data')
        self.ax.grid(True)
        
        # Extract data from table
        x_data = []
        y0_data = []
        y1_data = []
        y2_data = []
        y3_data = []
        y4_data = []
        
        for row in range(self.table.rowCount()):
            x_item = self.table.item(row, 0)
            y0_item = self.table.item(row, 1)
            y1_item = self.table.item(row, 2)
            y2_item = self.table.item(row, 3)
            y3_item = self.table.item(row, 4)
            y4_item = self.table.item(row, 5)
            
            if x_item and x_item.text():
                x_data.append(float(x_item.text()))
                
                if y0_item and y0_item.text():
                    y0_data.append(float(y0_item.text()))
                if y1_item and y1_item.text():
                    y1_data.append(float(y1_item.text()))
                if y2_item and y2_item.text():
                    y2_data.append(float(y2_item.text()))
                if y3_item and y3_item.text():
                    y3_data.append(float(y3_item.text()))
                if y4_item and y4_item.text():
                    y4_data.append(float(y4_item.text()))
        
        # Plot Y0 and Y1 on the primary axis (left)
        lines = []
        labels = []
        if y0_data:
            line, = self.ax.plot(x_data[:len(y0_data)], y0_data, 'b-', label='Y0')
            lines.append(line)
            labels.append('Y0')
        if y1_data:
            line, = self.ax.plot(x_data[:len(y1_data)], y1_data, 'r-', label='Y1')
            lines.append(line)
            labels.append('Y1')
        
        # Create secondary axes for Y2, Y3, Y4 if they have data
        # Y2 uses standard twinx (right side)
        if y2_data:
            self.ax2 = self.ax.twinx()
            line, = self.ax2.plot(x_data[:len(y2_data)], y2_data, 'g-', label='Y2')
            self.ax2.set_ylabel('Y2', color='g')
            self.ax2.tick_params(axis='y', labelcolor='g')
            lines.append(line)
            labels.append('Y2')
        
        # Y3 uses twinx with spine offset to the right
        if y3_data:
            self.ax3 = self.ax.twinx()
            self.ax3.spines['right'].set_position(('outward', 60))
            line, = self.ax3.plot(x_data[:len(y3_data)], y3_data, 'm-', label='Y3')
            self.ax3.set_ylabel('Y3', color='m')
            self.ax3.tick_params(axis='y', labelcolor='m')
            lines.append(line)
            labels.append('Y3')
        
        # Y4 uses twinx with spine offset further to the right
        if y4_data:
            self.ax4 = self.ax.twinx()
            self.ax4.spines['right'].set_position(('outward', 120))
            line, = self.ax4.plot(x_data[:len(y4_data)], y4_data, 'c-', label='Y4')
            self.ax4.set_ylabel('Y4', color='c')
            self.ax4.tick_params(axis='y', labelcolor='c')
            lines.append(line)
            labels.append('Y4')
        
        # Adjust layout to make room for multiple y-axes
        if y4_data:
            self.figure.subplots_adjust(right=0.67)  # Make room for Y4
        elif y3_data:
            self.figure.subplots_adjust(right=0.82)  # Make room for Y3
        else:
            self.figure.subplots_adjust(right=0.90)
        
        # Create combined legend
        if lines:
            self.ax.legend(lines, labels, loc='upper left')
        
        # Calculate and display statistics for Y0 and Y1
        stats_text = ""
        if y0_data:
            y0_min = min(y0_data)
            y0_max = max(y0_data)
            y0_amp = y0_max - y0_min
            stats_text += f"Y0: Min={y0_min:.2f}  Max={y0_max:.2f}  Amp={y0_amp:.2f}\n"
        
        if y1_data:
            y1_min = min(y1_data)
            y1_max = max(y1_data)
            y1_amp = y1_max - y1_min
            stats_text += f"Y1: Min={y1_min:.2f}  Max={y1_max:.2f}  Amp={y1_amp:.2f}"
        
        # Display statistics text below the plot
        if stats_text:
            self.figure.text(0.05, 0.02, stats_text, fontsize=9, 
                           verticalalignment='bottom', family='monospace',
                           bbox=dict(boxstyle='round', facecolor='wheat', alpha=1.0))
        
        self.canvas.draw()


def main():
    """Main entry point for the application"""
    app = QApplication(sys.argv)
    window = MotorDiagWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
