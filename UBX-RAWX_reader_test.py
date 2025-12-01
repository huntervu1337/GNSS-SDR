import serial
from pyubx2 import UBXReader

# CẤU HÌNH CỔNG COM
PORT = 'COM5'        # Thay đổi cổng COM của bạn
BAUDRATE = 115200    # Khuyên dùng baudrate cao cho RAWX (115200, 230400, 460800...)
TIMEOUT = 1

def gnss_id_to_char(gnss_id):
    """Chuyển đổi ID số sang ký tự hệ thống (G, E, C, R...)"""
    mapping = {
        0: 'G', # GPS
        1: 'S', # SBAS
        2: 'E', # Galileo
        3: 'C', # BeiDou
        4: 'I', # IMES
        5: 'Q', # QZSS
        6: 'R', # GLONASS
    }
    return mapping.get(gnss_id, 'U') # U = Unknown

def read_realtime_rawx():
    print(f"Đang kết nối tới {PORT} tốc độ {BAUDRATE}...")
    
    try:
        with serial.Serial(PORT, BAUDRATE, timeout=TIMEOUT) as stream:
            # Khởi tạo UBXReader để đọc luồng dữ liệu
            ubr = UBXReader(stream)
            
            print("Đang chờ bản tin UBX-RXM-RAWX...")
            
            # Vòng lặp đọc liên tục
            for (raw_data, parsed_data) in ubr:
                # parsed_data chứa đối tượng bản tin đã giải mã
                
                # Chúng ta chỉ quan tâm đến bản tin có identity là 'RXM-RAWX'
                if parsed_data.identity == 'RXM-RAWX':
                    
                    # 1. Lấy thông tin chung của Epoch
                    rcv_tow = parsed_data.rcvTow
                    week = parsed_data.week
                    num_meas = parsed_data.numMeas
                    
                    print(f"\n--- Epoch: Week {week} | TOW {rcv_tow:.3f} | Sats: {num_meas} ---")
                    
                    satellites_data = []

                    # 2. Lặp qua từng vệ tinh trong bản tin
                    # pyubx2 đánh chỉ số các nhóm lặp lại bằng _01, _02, ...
                    for i in range(1, num_meas + 1):
                        # Tạo tên thuộc tính động, ví dụ: gnssId_01, prMes_01
                        idx = f"{i:02d}" 
                        
                        try:
                            gnss_id = getattr(parsed_data, f"gnssId_{idx}")
                            sv_id = getattr(parsed_data, f"svId_{idx}")
                            pr_mes = getattr(parsed_data, f"prMes_{idx}") # Pseudorange
                            cp_mes = getattr(parsed_data, f"cpMes_{idx}") # Carrier Phase
                            cno = getattr(parsed_data, f"cno_{idx}")     # Signal Strength
                            
                            # Chỉ lấy GPS (gnssId = 0) để đơn giản hóa bài toán lúc đầu
                            if gnss_id == 0:
                                prn = f"{gnss_id_to_char(gnss_id)}{sv_id:02d}" # Ví dụ: G05
                                
                                # Lưu vào danh sách
                                satellites_data.append({
                                    'prn': prn,
                                    'pseudorange': pr_mes,
                                    'ssi': cno,
                                    'carrier_phase': cp_mes
                                })
                                
                                print(f"  {prn} | Pseudorange: {pr_mes:14.3f} m | SSI: {cno} dBHz")
                                
                        except AttributeError:
                            # Phòng trường hợp bản tin bị lỗi cấu trúc
                            continue
                    
                    # --- TẠI ĐÂY: BẠN CÓ THỂ GỌI HÀM GIẢI PHƯƠNG TRÌNH ---
                    # solver_input = prepare_realtime_input(satellites_data, rcv_tow, week)
                    # position = solve_navigation_equations(solver_input)
                    
    except serial.SerialException as e:
        print(f"Lỗi kết nối cổng COM: {e}")
    except KeyboardInterrupt:
        print("\nĐã dừng chương trình.")

if __name__ == "__main__":
    read_realtime_rawx()