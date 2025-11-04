import math
import datetime
import sys
import collections
from typing import List, Dict, Any, Optional, Tuple

# Import các hàm đã viết từ các file .py
try:
    from read_rinex_nav import read_rinex_nav
    from read_rinex_obs import read_rinex_obs
    from cal_sat_pos import calculate_satellite_position
except ImportError as e:
    print(f"Lỗi: Không tìm thấy file thư viện. {e}", file=sys.stderr)
    print("Vui lòng đảm bảo các file read_rinex_nav.py, read_rinex_obs.py, và cal_sat_pos.py ở cùng thư mục.")
    sys.exit(1)


# --- Hằng số (từ cal_sat_pos.py và lý thuyết) ---
c = 2.99792458e8            # Tốc độ ánh sáng (m/s)

# --- CÁC HÀM PHỤ TRỢ ---

def datetime_to_gps_sow(dt_utc: datetime.datetime) -> Tuple[int, float]:
    """
    Chuyển đổi datetime UTC sang Tuần GPS và Giây của Tuần (SOW).
    
    Lưu ý: Giờ GPS không có giây nhuận. Tính đến 2025,
    Giờ GPS chạy trước UTC 18 giây (GPS = UTC + 18s).
    """
    gps_epoch = datetime.datetime(1980, 1, 6, tzinfo=datetime.timezone.utc)
    
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=datetime.timezone.utc)

    time_diff_utc = dt_utc - gps_epoch
    
    LEAP_SECONDS = 18.0 # Giả định 18 giây nhuận cho năm 2025
    total_gps_seconds = time_diff_utc.total_seconds() + LEAP_SECONDS
    
    SECONDS_IN_WEEK = 604800.0
    
    gps_week = int(total_gps_seconds // SECONDS_IN_WEEK)
    gps_sow = total_gps_seconds % SECONDS_IN_WEEK
    
    return (gps_week, gps_sow)

def find_best_ephemeris_demo(eph_list: List[Dict[str, Any]], t_s_sow: float) -> Optional[Dict[str, Any]]:
    """
    Tìm bản ghi ephemeris (eph) tốt nhất từ một danh sách cho
    thời điểm truyền tín hiệu (t_s_sow).
    "Tốt nhất" được định nghĩa là có 'Toe' (Time of Ephemeris) gần nhất
    với 't_s_sow'
    (PHIÊN BẢN DEMO)
    Hàm này BỎ QUA kiểm tra chênh lệch thời gian 14400s để
    cho phép chạy demo với file .nav và .obs không khớp ngày.
    """
    best_eph = None
    min_delta_t = float('inf') 

    for eph in eph_list:
        toe = eph.get('Toe')
        if toe is None:
            continue
            
        delta_t = abs(t_s_sow - toe)
        if delta_t > 302400:
            delta_t = 604800 - delta_t
            
        if delta_t < min_delta_t:
            min_delta_t = delta_t
            best_eph = eph

    # Theo chuẩn, ephemeris thường chỉ có giá trị trong ~4 giờ (14400s) quanh Toe.        
    # --- LÀ DEMO NÊN ĐÃ XÓA BỎ KIỂM TRA 14400 GIÂY TẠI ĐÂY ---
    # if min_delta_t > 14400:
    #     return None 

    # Sẽ luôn trả về ephemeris có 'Toe' gần nhất, 
    # ngay cả khi nó cách xa hàng triệu giây (sai ngày).
    return best_eph

# --- HÀM TỔNG HỢP DỮ LIỆU ---

def prepare_basic_solver_inputs_demo(nav_file: str, obs_file: str) -> List[Dict[str, Any]]:
    """
    (PHIÊN BẢN DEMO)
    Kết hợp file NAV và OBS để chuẩn bị dữ liệu đầu vào cơ bản (pseudorange, x_j, y_j, z_j)
    cho giải hệ phương trình 4 ẩn.
    """
    print("Đang đọc file Navigation (.nav)...")
    nav_data = read_rinex_nav(nav_file)
    if not nav_data:
        print("Không thể đọc file Navigation.")
        return []

    print("Đang đọc file Observation (.obs)...")
    obs_data = read_rinex_obs(obs_file)
    if not obs_data:
        print("Không thể đọc file Observation.")
        return []

    print(f"Đã đọc {len(obs_data)} epochs từ file Observation. Bắt đầu xử lý (chế độ demo)...")
    
    solver_ready_epochs = []
    
    for epoch in obs_data:
        t_receiver_utc = epoch['time']
        
        try:
            (gps_week, t_r_sow) = datetime_to_gps_sow(t_receiver_utc)
        except Exception as e:
            print(f"Lỗi chuyển đổi thời gian cho epoch {t_receiver_utc}: {e}", file=sys.stderr)
            continue
            
        current_epoch_inputs = {
            "time_utc": t_receiver_utc,
            "time_sow": t_r_sow,
            "satellites": []
        }
        
        for prn, observations in epoch['observations'].items():
            
            if not prn.startswith('G'):
                continue
            if prn not in nav_data:
                continue
                
            obs_c1c = observations.get('C1C')
            if not obs_c1c:
                continue 

            rho_i = obs_c1c['value']
            
            t_travel = rho_i / c
            t_s_sow = t_r_sow - t_travel
            
            # Gọi hàm DEMO đã chỉnh sửa
            eph_to_use = find_best_ephemeris_demo(nav_data[prn], t_s_sow)
            
            if not eph_to_use:
                # Điều này gần như không xảy ra, trừ khi file .nav trống
                continue 

            (X, Y, Z) = calculate_satellite_position(eph_to_use, t_s_sow)
            
            if X is None:
                continue 

            sat_data = {
                "prn": prn,
                "pseudorange": rho_i,
                "sat_pos_ecef": (X, Y, Z)
            }
            current_epoch_inputs["satellites"].append(sat_data)

        if len(current_epoch_inputs["satellites"]) >= 4:
            solver_ready_epochs.append(current_epoch_inputs)
        
    print(f"Hoàn tất. Đã chuẩn bị dữ liệu cho {len(solver_ready_epochs)} epochs (có >= 4 vệ tinh GPS).")
    return solver_ready_epochs

# --- VÍ DỤ SỬ DỤNG ---
if __name__ == "__main__":
    
    NAV_FILE = 'nav.nav' 
    OBS_FILE = 'test.obs'

    print("--- CHẠY CHẾ ĐỘ DEMO (BỎ QUA KIỂM TRA THỜI GIAN) ---")

    # Gọi hàm DEMO
    solver_data = prepare_basic_solver_inputs_demo(NAV_FILE, OBS_FILE)

    if solver_data:
        # In ra dữ liệu đã chuẩn bị cho epoch đầu tiên
        first_epoch_data = solver_data[0]
        print(f"\n--- DỮ LIỆU ĐÃ SẴN SÀNG CHO BỘ GIẢI (EPOCH ĐẦU TIÊN) ---")
        print(f"Thời gian (UTC): {first_epoch_data['time_utc']}")
        print(f"Thời gian (SOW): {first_epoch_data['time_sow']:.3f} s")
        print(f"Tìm thấy {len(first_epoch_data['satellites'])} vệ tinh GPS hợp lệ:")

        for sat in first_epoch_data['satellites'][:4]: # In 4 vệ tinh đầu tiên
            print(f"  --- Vệ tinh: {sat['prn']} ---")
            print(f"    Pseudorange (rho_i):  {sat['pseudorange']:12.3f} m")
            print(f"    Sat. Pos (X_s):       {sat['sat_pos_ecef'][0]:12.3f} m")
            print(f"    Sat. Pos (Y_s):       {sat['sat_pos_ecef'][1]:12.3f} m")
            print(f"    Sat. Pos (Z_s):       {sat['sat_pos_ecef'][2]:12.3f} m")
