import serial
from pyubx2 import UBXReader, UBXMessage

def read_ubx_from_serial():
    # Configure serial port settings
    PORT = 'COM5'
    BAUDRATE = 9600  # Check your specific device manual (often 9600, 38400, or 115200)
    TIMEOUT = 3

    try:
        # Open serial connection
        with serial.Serial(PORT, BAUDRATE, timeout=TIMEOUT) as stream:
            print(f"Connected to {PORT} at {BAUDRATE} baud.")
            print("Waiting for UBX data...")

            # Instantiate UBXReader class
            # protfilter=2 allows UBX messages; you can also allow NMEA (1) or RTCM (4)
            ubr = UBXReader(stream)

            for (raw_data, parsed_data) in ubr:
                # parsed_data is a UBXMessage object
                
                # Example: Filter for specific message identity (e.g., NAV-PVT for navigation solution)
                if parsed_data.identity == 'NAV-PVT':
                    print(f"Timestamp: {parsed_data.year}-{parsed_data.month}-{parsed_data.day} "
                          f"{parsed_data.hour}:{parsed_data.min}:{parsed_data.second}")
                    print(f"Lat: {parsed_data.lat}, Lon: {parsed_data.lon}")
                    print(f"Accuracy (hAcc): {parsed_data.hAcc} mm")
                    print("-" * 20)
                
                # To see ALL messages, uncomment the line below:
                # print(parsed_data)

    except serial.SerialException as e:
        print(f"Error connecting to {PORT}: {e}")
    except KeyboardInterrupt:
        print("\nStream stopped by user.")

if __name__ == "__main__":
    read_ubx_from_serial()