import math
import sys
from datetime import datetime, timezone
# Import các module của bạn
from read_rinex_nav import read_rinex_nav
from solve_navigation_equations import solve_navigation_equations
from coord_transform import ecef_to_lla
import serial
from pyubx2 import UBXReader

# CẤU HÌNH
COM_PORT = 'COM5'
BAUDRATE = 115200 # Nhớ set ZED-F9P lên mức này hoặc cao hơn
NAV_FILE_PATH = '2908-nav-base.nav' # Hoặc file brdc tải mới nhất trong ngày

# --- Import các hàm cũ của bạn ---
from cal_sat_pos import calculate_satellite_position
# Tận dụng hàm tìm ephemeris tốt nhất từ code cũ (hoặc viết lại bản đơn giản hơn ở dưới)
from prepare_inputs import find_best_ephemeris 

# Hằng số tốc độ ánh sáng
c = 2.99792458e8

def process_realtime_epoch(ubx_epoch_data, nav_data):
    """
    Xử lý dữ liệu thô của 1 epoch từ ZED-F9P và chuẩn bị đầu vào cho bộ giải.
    
    Args:
        ubx_epoch_data (dict): Dữ liệu từ UBX-RXM-RAWX (đã parse).
                               Cấu trúc: {'rcvTow': float, 'week': int, 'satellites': list}
                               Trong đó 'satellites' là list các dict {'prn': 'G01', 'pseudorange': ...}
        nav_data (dict): Dữ liệu ephemeris đã load từ file .nav (dùng read_rinex_nav).
        
    Returns:
        dict: Dữ liệu đã sẵn sàng cho hàm solve_navigation_equations
              (trả về None nếu không đủ vệ tinh)
    """
    
    rcv_tow = ubx_epoch_data['rcvTow'] # Thời gian thu tại máy thu (Time of Reception)
    week = ubx_epoch_data['week']
    raw_sats = ubx_epoch_data['satellites']
    
    solver_satellites = []
    
    # Lặp qua từng vệ tinh quan sát được trong epoch này
    for sat in raw_sats:
        prn = sat['prn']
        pseudorange = sat['pseudorange']
        
        # 1. Kiểm tra xem có Ephemeris cho vệ tinh này không
        if prn not in nav_data:
            # print(f"Warning: Không có lịch vệ tinh cho {prn}. Bỏ qua.")
            continue
            
        ephemeris_list = nav_data[prn]
        
        # 2. Tính thời gian phát tín hiệu (Signal Transmission Time)
        # t_tx = t_rx - thời_gian_bay
        # thời_gian_bay = pseudorange / c
        # Đây là bước quan trọng: Vị trí vệ tinh phải tính ở t_tx, không phải t_rx!
        travel_time = pseudorange / c
        t_tx_sow = rcv_tow - travel_time
        
        # 3. Tìm ephemeris phù hợp nhất cho thời điểm phát (t_tx)
        best_eph = find_best_ephemeris(ephemeris_list, t_tx_sow)
        
        if best_eph is None:
            continue
            
        # 4. Tính tọa độ vệ tinh tại t_tx
        # Gọi hàm cal_sat_pos cũ của bạn
        (x_sat, y_sat, z_sat, dt_sat) = calculate_satellite_position(best_eph, t_tx_sow)
        
        # 5. Tính lượng hiệu chỉnh đồng hồ vệ tinh (đổi ra mét)
        sat_clock_corr_meters = c * dt_sat

        if x_sat is None:
            continue
        
        # 6. Đóng gói dữ liệu (theo format mà solve_navigation_equations cần)
        solver_satellites.append({
            'prn': prn,
            'pseudorange': pseudorange, # Pseudorange đã bù sai số đồng hồ vệ tinh
            'sat_pos_ecef': (x_sat, y_sat, z_sat),
            'sat_clock_corr_meters': sat_clock_corr_meters,
            # Có thể thêm trọng số (weight) ở đây nếu muốn (dựa trên sat['cno'])
            'weight': 1.0 
        })
        
    # Kiểm tra số lượng vệ tinh tối thiểu
    if len(solver_satellites) < 4:
        return None
        
    # Tạo cấu trúc dữ liệu cuối cùng cho Epoch
    epoch_solver_data = {
        'time_sow': rcv_tow,
        'week': week,
        'satellites': solver_satellites
    }
    
    return epoch_solver_data

if __name__ == "__main__":
    # 1. Load dữ liệu Navigation (Ephemeris) trước
    print(f"Đang tải dữ liệu Ephemeris từ {NAV_FILE_PATH}...")
    nav_data = read_rinex_nav(NAV_FILE_PATH)
    if not nav_data:
        print("Lỗi: Không đọc được file NAV. Dừng chương trình.")
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
    except serial.SerialException as e:
        print(f"Lỗi cổng COM: {e}")
    except KeyboardInterrupt:
        print("Đã dừng.")