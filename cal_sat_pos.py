import math 
import sys
import datetime
from read_rinex_nav import *

# --- CÁC HẰNG SỐ VẬT LÝ & GPS (Theo ICD-GPS-200 / WGS-84) ---
MU_GPS = 3.986005e14            # Hằng số hấp dẫn của Trái Đất (m^3/s^2)
OMEGA_E_DOT = 7.2921151467e-5   # Tốc độ quay của Trái Đất (rad/s)
c = 2.99792458e8                # Tốc độ ánh sáng trong chân không (m/s)
F = -4.442807633e-10            # Hằng số cho hiệu chỉnh tương đối tính (sec/meter^(1/2))

def _datetime_to_sow(dt):
    """
    Hàm phụ trợ: Chuyển đổi datetime thành Giây trong tuần GPS (SOW - Second of Week).
    Lưu ý: Hàm này giả định đầu vào đã là giờ GPS (hoặc không quan tâm giây nhuận
    nếu tính khoảng cách tương đối trong cùng hệ quy chiếu).
    """
    gps_epoch = datetime.datetime(1980, 1, 6, tzinfo=datetime.timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    
    # Tính tổng số giây từ mốc GPS Epoch
    delta = dt - gps_epoch
    total_sec = delta.total_seconds()
    
    # Chia lấy dư cho số giây trong 1 tuần (604800s) để ra SOW
    return total_sec % 604800.0


def calculate_satellite_position(eph, t_sv):
    """
    Tính toán vị trí vệ tinh (ECEF) và hiệu chỉnh đồng hồ tại thời điểm phát tín hiệu.
    
    Args:
        eph (dict): Dữ liệu tinh lịch (ephemeris) của vệ tinh.
        t_sv (float): Thời điểm PHÁT tín hiệu (Transmission Time) theo giờ GPS (SOW).
                      Giá trị này thường được tính: t_rx (thu) - pseudo_range/c.

    Returns:
        tuple: (X, Y, Z, dt_sat)
            - X, Y, Z: Tọa độ vệ tinh trong hệ ECEF tại thời điểm phát, 
                       đã được xoay để khớp với hệ quy chiếu tại thời điểm thu (Sagnac effect).
            - dt_sat:  Sai số đồng hồ vệ tinh (Clock Bias) tính bằng giây.
                       Đã bao gồm: Đa thức đồng hồ + Hiệu chỉnh tương đối.
                       (Lưu ý: TGD được xử lý ở bên ngoài hoặc tùy chọn).
    """
    try:
        # ===========================================================
        # BƯỚC 0: TRÍCH XUẤT CÁC THAM SỐ TỪ TINH LỊCH (EPHEMERIS)
        # ===========================================================
        # Tham số quỹ đạo Kepler
        sqrt_a = eph['sqrt_a']      # Căn bậc 2 bán trục lớn
        e = eph['e']                # Độ lệch tâm (Eccentricity)
        m0 = eph['M0']              # Dị thường trung bình (Mean Anomaly) tại Toe
        omega = eph['omega']        # Argument of Perigee
        i0 = eph['i0']              # Độ nghiêng quỹ đạo tại Toe
        omega0 = eph['Omega0']      # Longitude of Ascending Node tại tuần GPS
        
        # Tham số nhiễu loạn và tốc độ thay đổi
        delta_n = eph['Delta_n']    # Hiệu chỉnh chuyển động trung bình
        i_dot = eph['i_dot']        # Tốc độ thay đổi độ nghiêng
        omega_dot = eph['Omega_dot']# Tốc độ thay đổi Longitude of Ascending Node
        
        # Tham số hiệu chỉnh điều hòa (Harmonic Corrections)
        cuc = eph['Cuc']; cus = eph['Cus'] # Cho Argument of Latitude
        crc = eph['Crc']; crs = eph['Crs'] # Cho Bán kính quỹ đạo
        cic = eph['Cic']; cis = eph['Cis'] # Cho Độ nghiêng
        
        # Thời gian tham chiếu quỹ đạo (Toe)
        toe = eph['Toe']

        # Tham số đồng hồ (Clock)
        a0 = eph['a0']; a1 = eph['a1']; a2 = eph['a2']
        
        # Total Group Delay (TGD): Quan trọng cho người dùng đơn tần
        tgd = eph.get("TGD", 0.0) or 0.0

        # Thời gian tham chiếu đồng hồ (Toc) - lấy từ epoch của bản tin
        toc = _datetime_to_sow(eph['epoch'])

        # ===========================================================
        # BƯỚC 1: TÍNH TOÁN THỜI GIAN TRUYỀN DẪN (Time difference)
        # ===========================================================
        # t_k là thời gian từ thời điểm tham chiếu Toe đến thời điểm phát t_sv
        t_k = t_sv - toe
        
        # Xử lý trường hợp chuyển giao giữa các tuần (Week Crossover)
        # Nếu chênh lệch quá lớn (> nửa tuần), điều chỉnh lại cho đúng
        if t_k > 302400: t_k -= 604800
        elif t_k < -302400: t_k += 604800

        # ===========================================================
        # BƯỚC 2: TÍNH TOÁN QUỸ ĐẠO (Keplerian Orbit)
        # ===========================================================
        # Bán trục lớn (Semi-major axis)
        A = sqrt_a * sqrt_a
        
        # Chuyển động trung bình tính toán (Computed Mean Motion)
        n0 = math.sqrt(MU_GPS / A**3)
        
        # Chuyển động trung bình đã hiệu chỉnh
        n = n0 + delta_n
        
        # Dị thường trung bình (Mean Anomaly) tại t_sv
        M_k = m0 + n * t_k

        # --- Giải phương trình Kepler: M_k = E_k - e*sin(E_k) ---
        # Sử dụng phương pháp lặp Newton-Raphson để tìm Dị thường tâm sai (Eccentric Anomaly) E_k
        E_k = M_k
        for _ in range(8): # Thường chỉ cần 3-4 vòng lặp là hội tụ
            d = (E_k - e*math.sin(E_k) - M_k) / (1 - e*math.cos(E_k))
            E_k -= d
            if abs(d) < 1e-13: break

        # Dị thường thực (True Anomaly) v_k
        nu_k = math.atan2(math.sqrt(1-e*e)*math.sin(E_k),
                          math.cos(E_k)-e)

        # Argument of Latitude (Phi_k) chưa hiệu chỉnh
        Phi_k = nu_k + omega

        # --- Tính các hiệu chỉnh nhiễu loạn bậc 2 ---
        sin2 = math.sin(2*Phi_k)
        cos2 = math.cos(2*Phi_k)

        delta_u = cus*sin2 + cuc*cos2 # Hiệu chỉnh Argument of Latitude
        delta_r = crs*sin2 + crc*cos2 # Hiệu chỉnh Bán kính
        delta_i = cis*sin2 + cic*cos2 # Hiệu chỉnh Độ nghiêng

        # Áp dụng hiệu chỉnh
        u = Phi_k + delta_u
        r = A*(1 - e*math.cos(E_k)) + delta_r # Bán kính đã hiệu chỉnh
        i = i0 + delta_i + i_dot*t_k          # Độ nghiêng đã hiệu chỉnh

        # Tọa độ trong mặt phẳng quỹ đạo (Orbital Plane)
        x_orb = r * math.cos(u)
        y_orb = r * math.sin(u)

        # Longitude of Ascending Node đã hiệu chỉnh (Omega_k)
        # Tính đến chuyển động quay của Trái Đất trong thời gian t_k
        Omega_k = omega0 + (omega_dot - OMEGA_E_DOT)*t_k - OMEGA_E_DOT*toe

        # Tọa độ ECEF TẠI THỜI ĐIỂM PHÁT (chưa tính Sagnac effect)
        X = x_orb*math.cos(Omega_k) - y_orb*math.cos(i)*math.sin(Omega_k)
        Y = x_orb*math.sin(Omega_k) + y_orb*math.cos(i)*math.cos(Omega_k)
        Z = y_orb*math.sin(i)

        # ===========================================================
        # BƯỚC 3: TÍNH HIỆU CHỈNH ĐỒNG HỒ (CLOCK CORRECTION)
        # ===========================================================
        # Tính khoảng thời gian từ mốc Toc đến t_sv
        dt_clk = t_sv - toc
        if dt_clk > 302400: dt_clk -= 604800
        elif dt_clk < -302400: dt_clk += 604800

        # 1. Sai số đa thức (Polynomial Offset + Drift + Aging)
        dts_poly = a0 + a1*dt_clk + a2*(dt_clk**2)
        
        # 2. Hiệu chỉnh thuyết tương đối (Relativistic Correction)
        # Do quỹ đạo elip, vận tốc và thế năng hấp dẫn thay đổi gây ra giãn nở thời gian
        dts_rel  = F * e * sqrt_a * math.sin(E_k)

        # Tổng hợp sai số đồng hồ vệ tinh
        # Lưu ý: Không trừ TGD ở đây, đã xử lý tường minh ở prepare_inputs
        dt_sat = dts_poly + dts_rel

        return (X, Y, Z, dt_sat)

    except Exception as e:
        print(f"Lỗi tính vị trí vệ tinh: {e}", file=sys.stderr)
        return (None, None, None, None)
    



# --- VÍ DỤ SỬ DỤNG ---
if __name__ == "__main__":
    
    rinex_file = '2908-nav-base.nav' # Đường dẫn đến file nav

    print(f"Đang đọc file RINEX: {rinex_file}")
    nav_data = read_rinex_nav(rinex_file)

    if nav_data:
        print(f"Đã đọc thành công dữ liệu cho {len(nav_data)} vệ tinh: {sorted(nav_data.keys())}")

        # --- Chọn một vệ tinh và thời điểm để tính toán ---
        example_sat = 'G05' # Thử với vệ tinh G05
        if example_sat in nav_data:
            # Lấy bản ghi ephemeris đầu tiên tìm thấy cho G05
            # Một ứng dụng thực tế sẽ tìm bản ghi có 'Toe' gần nhất với thời gian cần tính
            eph_to_use = nav_data[example_sat][0]

            # Xác định thời điểm cần tính (Time of Interest)
            # Ví dụ: Tính vị trí ngay tại thời điểm tham chiếu (Toe)
            t_calc_sow = eph_to_use['Toe']
            
            # Hoặc tính tại thời điểm sau Toe 1 phút (60 giây)
            # t_calc_sow = eph_to_use['Toe'] + 60.0

            print(f"\n--- Tính toán vị trí cho {example_sat} ---")
            print(f"Sử dụng ephemeris epoch: {eph_to_use['epoch']}")
            print(f"Thời gian tham chiếu (Toe): {eph_to_use['Toe']} SOW")
            print(f"Thời gian tính toán (t): {t_calc_sow} SOW")

            # Gọi hàm tính toán
            (X, Y, Z, dt_sat) = calculate_satellite_position(eph_to_use, t_calc_sow)

            if X is not None:
                print("\nKết quả tọa độ ECEF (X, Y, Z) (đơn vị: mét):")
                print(f"X: {X:,.3f} m")
                print(f"Y: {Y:,.3f} m")
                print(f"Z: {Z:,.3f} m")
                print(f"Satellite clock correction: {dt_sat * 1e9} ns")
                
                # Tính toán khoảng cách từ tâm Trái Đất để kiểm tra
                distance = math.sqrt(X**2 + Y**2 + Z**2) / 1000.0 # đổi sang km
                print(f"-> Khoảng cách tới tâm TĐ: {distance:,.3f} km")
                # (Kết quả này nên ~ 26,600 km đối với GPS)
            else:
                print("\nTính toán vị trí thất bại.")
        else:
            print(f"\nKhông tìm thấy dữ liệu cho vệ tinh {example_sat} trong file.")

    else:
        print("\nKhông thể đọc dữ liệu từ file RINEX.")