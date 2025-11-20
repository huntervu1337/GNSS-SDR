import math
import datetime
import sys
import collections
from typing import List, Dict, Any, Optional, Tuple

# Import các đã viết từ các file .py
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
    
    Lưu ý: Giờ GPS không có giây nhuận. Tính đến 2025 (năm trong file test.obs),
    Giờ GPS chạy trước UTC 18 giây (GPS = UTC + 18s).
    """
    """
    Theo chuẩn RINEX v3, thời gian ghi nhận trong file Observation (các dòng bắt đầu bằng >),
    thường là thời gian UTC. Còn thời gian trong file Navigation là thời gian GPS
    Do đó, code cần cộng thêm 18 giây để chuyển từ hệ UTC (của file Obs) sang hệ GPS (file Nav).
    """
    # Mốc thời gian GPS: 1980-01-06 00:00:00 UTC
    gps_epoch = datetime.datetime(1980, 1, 6, tzinfo=datetime.timezone.utc)
    
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=datetime.timezone.utc)

    # Chênh lệch thời gian so với mốc UTC
    time_diff_utc = dt_utc - gps_epoch
    
    # Cộng thêm giây nhuận (18s) để có tổng giây GPS
    # (TAI = UTC + 37s, GPS = TAI - 19s  => GPS = UTC + 18s)
    LEAP_SECONDS = 18.0
    total_gps_seconds = time_diff_utc.total_seconds() + LEAP_SECONDS
    
    SECONDS_IN_WEEK = 604800.0  # (7 * 24 * 60 * 60)
    
    gps_week = int(total_gps_seconds // SECONDS_IN_WEEK)
    gps_sow = total_gps_seconds % SECONDS_IN_WEEK
    
    return (gps_week, gps_sow)

def find_best_ephemeris(eph_list: List[Dict[str, Any]], t_s_sow: float) -> Optional[Dict[str, Any]]:
    """
    Tìm bản ghi ephemeris (eph) tốt nhất từ một danh sách cho
    thời điểm truyền tín hiệu (t_s_sow).
    "Tốt nhất" được định nghĩa là có 'Toe' (Time of Ephemeris) gần nhất 
    với 't_s_sow'
    """
    best_eph = None
    min_delta_t = float('inf') # Vô cùng

    for eph in eph_list:
        toe = eph.get('Toe')
        if toe is None:
            continue
            
        # Tính chênh lệch thời gian, xử lý week crossover
        delta_t = abs(t_s_sow - toe)
        if delta_t > 302400:  # Nửa tuần
            delta_t = 604800 - delta_t
            
        if delta_t < min_delta_t:
            min_delta_t = delta_t
            best_eph = eph
            
    # Theo chuẩn, ephemeris thường chỉ có giá trị trong ~4 giờ (14400s)
    # quanh Toe
    if min_delta_t > 14400:
        return None  # Không có ephemeris nào đủ gần

    return best_eph

# --- HÀM TỔNG HỢP DỮ LIỆU ---

def prepare_basic_solver_inputs(nav_file: str, obs_file: str) -> List[Dict[str, Any]]:
    """
    Kết hợp file NAV và OBS để chuẩn bị dữ liệu đầu vào cơ bản
    cho bộ giải 4 ẩn (chưa bao gồm clock correction).
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

    print(f"Đã đọc {len(obs_data)} epochs từ file Observation. Bắt đầu xử lý...")
    
    solver_ready_epochs = []
    
    # Lặp qua từng mốc thời gian (epoch) trong file observation
    for epoch in obs_data:
        t_receiver_utc = epoch['time']
        
        # Chuyển thời gian máy thu (UTC) sang Giây của Tuần (SOW)
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
        
        # Lặp qua từng vệ tinh quan sát được tại epoch này
        for prn, observations in epoch['observations'].items():
            
            # --- CHỌN LỌC DỮ LIỆU ---
            
            # 1. Chỉ xử lý vệ tinh GPS ('G')
            if not prn.startswith('G'):
                continue
                
            # 2. Kiểm tra có dữ liệu ephemeris cho vệ tinh này không
            if prn not in nav_data:
                continue
                
            # 3. Lấy pseudorange (C1C) 
            obs_c1c = observations.get('C1C')
            if not obs_c1c:
                continue # Bỏ qua nếu không có pseudorange C1C

            rho_i = obs_c1c['value'] # Đây là rho_i
            
            # --- TÍNH TOÁN ---
            
            # 4. Ước tính thời gian truyền tín hiệu (travel time)
            t_travel = rho_i / c  # ~0.07 giây
            
            # 5. Ước tính thời gian phát tín hiệu (transmit time) t_s
            # Đây là thời điểm chúng ta cần tính vị trí vệ tinh
            t_s_sow = t_r_sow - t_travel
            
            # 6. Tìm ephemeris tốt nhất (gần t_s_sow nhất)
            eph_to_use = find_best_ephemeris(nav_data[prn], t_s_sow)
            if not eph_to_use:
                continue # Bỏ qua nếu không có ephemeris hợp lệ

            # 7. Tính toán vị trí vệ tinh (X, Y, Z) TẠI t_s_sow
            # Đây là (xs_i, ys_i, zs_i)
            (X, Y, Z, dt_sat) = calculate_satellite_position(eph_to_use, t_s_sow)
            
            if X is None:
                continue # Bỏ qua nếu tính toán lỗi

            # 8. Lưu trữ dữ liệu đã sẵn sàng cho bộ giải
            sat_data = {
                "prn": prn,
                "pseudorange": rho_i,     # (rho_i)
                "sat_pos_ecef": (X, Y, Z), # (xs_i, ys_i, zs_i)
                "sat_clock_corr_meters": c * dt_sat 
            }
            current_epoch_inputs["satellites"].append(sat_data)

        # --- KẾT THÚC EPOCH ---
        # Chỉ lưu epoch này nếu có đủ 4 vệ tinh để giải
        if len(current_epoch_inputs["satellites"]) >= 4:
            solver_ready_epochs.append(current_epoch_inputs)
        
    print(f"Hoàn tất. Đã chuẩn bị dữ liệu cho {len(solver_ready_epochs)} epochs (có >= 4 vệ tinh GPS).")
    return solver_ready_epochs


# --- VÍ DỤ SỬ DỤNG ---
if __name__ == "__main__":
    
    NAV_FILE = '2908-nav-base.nav' # File .nav 
    OBS_FILE = 'test.obs' # File .obs

    # Chạy hàm chuẩn bị dữ liệu
    solver_data = prepare_basic_solver_inputs(NAV_FILE, OBS_FILE)

    if solver_data:
        # In ra dữ liệu đã chuẩn bị cho epoch đầu tiên
        first_epoch_data = solver_data[0]
        print(f"\n--- DỮ LIỆU ĐÃ SẴN SÀNG CHO BỘ GIẢI (EPOCH ĐẦU TIÊN) ---")
        print(f"Thời gian (UTC): {first_epoch_data['time_utc']}")
        print(f"Thời gian (SOW): {first_epoch_data['time_sow']:.3f} s")
        print(f"Tìm thấy {len(first_epoch_data['satellites'])} vệ tinh GPS hợp lệ:")

        # In thông tin của 4 vệ tinh đầu tiên
        for sat in first_epoch_data['satellites'][:4]:
            print(f"  --- Vệ tinh: {sat['prn']} ---")
            print(f"    Pseudorange (rho_i):  {sat['pseudorange']:12.3f} m")
            print(f"    Sat. Pos (X_s):       {sat['sat_pos_ecef'][0]:12.3f} m")
            print(f"    Sat. Pos (Y_s):       {sat['sat_pos_ecef'][1]:12.3f} m")
            print(f"    Sat. Pos (Z_s):       {sat['sat_pos_ecef'][2]:12.3f} m")
            print(f"    Sat. Clock correction:{sat['sat_clock_corr_meters'] * 1e9 / c:12.3f} ns")