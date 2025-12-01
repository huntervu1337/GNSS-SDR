import serial
from pyubx2 import UBXReader
import sys

# Import các module của bạn
from read_rinex_nav import read_rinex_nav
from solve_navigation_equations import solve_navigation_equations
from coord_transform import ecef_to_lla
from realtime_adapter import process_realtime_epoch # Hàm mới viết ở trên

# CẤU HÌNH
COM_PORT = 'COM5'
BAUDRATE = 115200 # Nhớ set ZED-F9P lên mức này hoặc cao hơn
NAV_FILE_PATH = '2908-nav-base.nav' # Hoặc file brdc tải mới nhất trong ngày

def main():
    # 1. Load dữ liệu Navigation (Ephemeris) trước
    print(f"Đang tải dữ liệu Ephemeris từ {NAV_FILE_PATH}...")
    nav_data = read_rinex_nav(NAV_FILE_PATH)
    if not nav_data:
        print("Lỗi: Không đọc được file NAV. Dừng chương trình.")
        return
    print(f"Đã tải ephemeris của {len(nav_data)} vệ tinh.")

    # 2. Kết nối tới ZED-F9P
    try:
        stream = serial.Serial(COM_PORT, BAUDRATE, timeout=1)
        ubr = UBXReader(stream)
        print(f"Đang lắng nghe dữ liệu thời gian thực trên {COM_PORT}...")
        
        # Vị trí dự đoán ban đầu (Tâm Trái Đất)
        current_pos = [0, 0, 0] 

        for (raw_data, parsed_data) in ubr:
            # Chỉ xử lý bản tin RAWX
            if parsed_data.identity == 'RXM-RAWX':
                
                # --- A. Trích xuất dữ liệu thô từ UBX ---
                rcv_tow = parsed_data.rcvTow
                week = parsed_data.week
                num_meas = parsed_data.numMeas
                
                raw_satellites = []
                for i in range(1, num_meas + 1):
                    idx = f"{i:02d}"
                    try:
                        gnss_id = getattr(parsed_data, f"gnssId_{idx}")
                        # Chỉ xử lý GPS (gnssId=0)
                        if gnss_id == 0:
                            sv_id = getattr(parsed_data, f"svId_{idx}")
                            pr_mes = getattr(parsed_data, f"prMes_{idx}")
                            cno = getattr(parsed_data, f"cno_{idx}")
                            
                            prn = f"G{sv_id:02d}"
                            raw_satellites.append({
                                'prn': prn,
                                'pseudorange': pr_mes,
                                'cno': cno
                            })
                    except AttributeError:
                        continue
                
                # --- B. Tính toán Vị trí Vệ tinh (Dùng realtime_adapter) ---
                ubx_epoch_struct = {
                    'rcvTow': rcv_tow, 
                    'week': week, 
                    'satellites': raw_satellites
                }
                
                # Hàm này sẽ tính t_tx, gọi cal_sat_pos, và đóng gói dữ liệu
                solver_input = process_realtime_epoch(ubx_epoch_struct, nav_data)
                
                # --- C. Giải phương trình vị trí (Solver) ---
                if solver_input:
                    # Gọi hàm giải (sử dụng vị trí cũ làm dự đoán cho vị trí mới để hội tụ nhanh)
                    solution = solve_navigation_equations(solver_input, current_pos)
                    
                    if solution is not None:
                        x, y, z, clk = solution
                        
                        # Cập nhật vị trí hiện tại để làm đầu vào cho vòng lặp sau
                        current_pos = [x, y, z]
                        
                        # Chuyển đổi sang LLA để dễ đọc
                        lat, lon, hgt = ecef_to_lla(x, y, z)
                        
                        print(f"TOW: {rcv_tow:.2f} | Sats: {len(solver_input['satellites'])} | "
                              f"Lat: {lat:.6f}, Lon: {lon:.6f}, Hgt: {hgt:.3f} m")
                    else:
                        print(f"TOW: {rcv_tow:.2f} | Không hội tụ.")
                else:
                    # print(f"TOW: {rcv_tow:.2f} | Không đủ dữ liệu GPS (hoặc thiếu Ephemeris).")
                    pass

    except serial.SerialException as e:
        print(f"Lỗi cổng COM: {e}")
    except KeyboardInterrupt:
        print("Đã dừng.")

if __name__ == "__main__":
    main()