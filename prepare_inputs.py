import math
import datetime
import sys
from read_rinex_nav import read_rinex_nav
from read_rinex_obs import read_rinex_obs
from cal_sat_pos import calculate_satellite_position

# Hằng số tốc độ ánh sáng
c = 2.99792458e8
OMEGA_E_DOT = 7.2921151467e-5

def datetime_to_gps_sow(dt):
    """
    Chuyển đổi datetime UTC sang GPS Week và Second of Week (SOW).
    Lưu ý: Nếu dt input là UTC chuẩn, cần +18s giây nhuận để ra GPS Time.
    Nhưng nếu file OBS đã ghi time hệ GPS thì không cần cộng.
    (Code này giả định input đã được xử lý hoặc file OBS ghi time hệ GPS).
    """
    gps_epoch = datetime.datetime(1980,1,6,tzinfo=datetime.timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    
    diff = dt - gps_epoch
    # Tính SOW (phần lẻ của giây trong tuần)
    sow = diff.total_seconds() % 604800.0
    # Tính GPS Week
    week = int(diff.total_seconds() // 604800.0)
    return week, sow


def find_best_ephemeris(eph_list, t_s):
    """
    Tìm bản tin tinh lịch (ephemeris) phù hợp nhất cho thời điểm t_s.
    Tiêu chí: Thời gian Toe gần t_s nhất và không quá 4 giờ.
    """
    best = None
    mindt = 999999
    for eph in eph_list:
        toe = eph["Toe"]
        # Tính khoảng cách thời gian, xử lý week crossover
        dt = abs(t_s - toe)
        if dt > 302400: dt = 604800 - dt
        
        if dt < mindt:
            mindt = dt
            best = eph
            
    # Nếu bản tin quá cũ (> 4 giờ = 14400s), không sử dụng
    if mindt > 14400: 
        return None
    return best


def prepare_basic_solver_inputs(nav_file, obs_file):
    """
    Đọc và chuẩn bị dữ liệu đầu vào cho bộ giải (Solver).
    Quy trình:
    1. Đọc file NAV và OBS.
    2. Với mỗi epoch và mỗi vệ tinh:
       - Lấy Pseudorange thô (C1C).
       - Trừ TGD (Total Group Delay) khỏi Pseudorange (cho Single Frequency).
       - Tính thời gian phát tín hiệu (Transmission Time).
       - Tính tọa độ vệ tinh và sai số đồng hồ vệ tinh.
    3. Gom nhóm các vệ tinh hợp lệ theo epoch.
    """
    # Đọc dữ liệu thô
    nav = read_rinex_nav(nav_file)
    obs = read_rinex_obs(obs_file)

    epochs = []

    for epoch in obs:
        dt = epoch["time"]
        # Chuyển đổi thời gian thu (Receiver Time) sang GPS SOW
        _, t_r = datetime_to_gps_sow(dt)

        epoch_struct = {
            "time_utc": dt,
            "time_sow": t_r,
            "satellites": []
        }

        for prn, o in epoch["observations"].items():
            # Chỉ xử lý vệ tinh GPS ('G') và có dữ liệu NAV
            if not prn.startswith("G"):
                continue
            if prn not in nav:
                continue

            # Chỉ xử lý nếu có dữ liệu giả khoảng cách C1C (L1 C/A code)
            if "C1C" not in o:
                continue

            rho_raw = o["C1C"]["value"]

            # --- BƯỚC 1: Lấy TGD để hiệu chỉnh Pseudorange ---
            # Tìm ephemeris sơ bộ (dựa trên t_r) để lấy TGD
            best_eph = find_best_ephemeris(nav[prn], t_r)
            if not best_eph: 
                continue

            # TGD (Total Group Delay): Độ trễ phần cứng giữa tần số L1 và L2.
            # Người dùng đơn tần L1 CẦN trừ giá trị này khỏi pseudorange đo được.
            tgd = best_eph.get("TGD", 0.0) or 0.0

            # Pseudorange đã hiệu chỉnh TGD
            rho_corr = rho_raw - c*tgd

            # --- BƯỚC 2: Ước tính thời gian phát (Transmission Time) ---
            # Thời gian bay = Quãng đường / Tốc độ ánh sáng
            t_travel = rho_corr / c
            # Thời gian phát (t_s) = Thời gian thu (t_r) - Thời gian bay
            t_s = t_r - t_travel

            # --- BƯỚC 3: Tìm Ephemeris chính xác tại thời điểm phát ---
            eph = find_best_ephemeris(nav[prn], t_s)
            if not eph:
                continue

            # --- BƯỚC 4: Tính vị trí và đồng hồ vệ tinh ---
            # Hàm trả về: Tọa độ (đã xoay Sagnac) và Sai số đồng hồ (đã tính tương đối tính)
            X, Y, Z, dt_sat = calculate_satellite_position(eph, t_s)

            # ===========================================================
            # BƯỚC 5: HIỆU CHỈNH QUAY TRÁI ĐẤT (SAGNAC EFFECT)
            # ===========================================================
            # Trong thời gian tín hiệu bay từ vệ tinh xuống máy thu
            # Trái Đất đã tự quay một góc nhỏ. Hệ tọa độ ECEF gắn với Trái Đất cũng quay theo.
            # Cần xoay tọa độ vệ tinh (tại t_phát) sang hệ quy chiếu ECEF (tại t_thu).
            
            # Ước lượng thời gian lan truyền tín hiệu (travel time)
            # t_travel = rho_corr / c
            
            # Góc quay của Trái Đất trong thời gian đó
            theta = OMEGA_E_DOT * t_travel

            # Phép xoay trục Z
            X_rot = X*math.cos(theta) + Y*math.sin(theta)
            Y_rot = -X*math.sin(theta) + Y*math.cos(theta)
            Z_rot = Z
            
            if X is None:
                continue

            # Lưu dữ liệu sạch vào cấu trúc để Solver sử dụng
            epoch_struct["satellites"].append({
                "prn": prn,
                "pseudorange": rho_corr,       # Pseudorange đã trừ TGD
                "sat_pos_ecef": (X_rot, Y_rot, Z_rot),     # Vị trí vệ tinh tại t_s (hệ ECEF t_r)
                "sat_clock_corr_meters": c * dt_sat # Sai số đồng hồ vệ tinh (đổi ra mét)
            })

        # Chỉ giữ lại các epoch có đủ số lượng vệ tinh tối thiểu (4) để giải
        if len(epoch_struct["satellites"]) >= 4:
            epochs.append(epoch_struct)

    return epochs



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