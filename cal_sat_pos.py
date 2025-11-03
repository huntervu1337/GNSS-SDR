import math
import sys

# Import functions from read_rinex_nav.py
from read_rinex_nav import *

# --- Hằng số (từ Sách ESA GNSS / WGS-84) ---
# Hằng số hấp dẫn Trái Đất (m^3/s^2) - WGS-84
MU_GPS = 3.986005e14
# Tốc độ quay Trái Đất (rad/s) - WGS-84
OMEGA_E_DOT = 7.2921151467e-5
# Tốc độ ánh sáng (m/s)
c = 2.99792458e8

def calculate_satellite_position(eph, t_gps_sow):
    """
    Tính toán tọa độ ECEF (X, Y, Z) của vệ tinh tại một thời điểm cụ thể
    dựa trên thuật toán từ Sách ESA GNSS Vol 1, Mục 3.3.1/3.3.2.

    Args:
        eph (dict): Một dictionary chứa ephemeris cho MỘT epoch của vệ tinh,
                    được trả về từ hàm read_rinex_nav_ephemeris_merged.
        t_gps_sow (float): Thời điểm cần tính toán (time of interest)
                           tính bằng Giây của Tuần GPS (GPS Seconds of Week).

    Returns:
        tuple: Một tuple (X, Y, Z) tọa độ vệ tinh trong hệ ECEF (đơn vị: mét),
               hoặc (None, None, None) nếu tính toán thất bại.
    """
    try:
        # --- 0. Lấy các tham số cần thiết từ ephemeris ---
        sqrt_a = eph['sqrt_a']
        e = eph['e']          # Độ lệch tâm
        m0 = eph['M0']        # Dị thường trung bình tại t_oe
        omega = eph['omega']  # Argument of Perigee
        i0 = eph['i0']        # Độ nghiêng quỹ đạo tại t_oe
        omega0 = eph['Omega0'] # Kinh độ điểm mọc tại t_oe
        delta_n = eph['Delta_n'] # Hiệu chỉnh chuyển động trung bình
        i_dot = eph['i_dot']     # Tốc độ thay đổi độ nghiêng
        omega_dot = eph['Omega_dot'] # Tốc độ thay đổi kinh độ điểm mọc
        cuc = eph['Cuc']
        cus = eph['Cus']
        crc = eph['Crc']
        crs = eph['Crs']
        cic = eph['Cic']
        cis = eph['Cis']
        toe = eph['Toe']      # Thời gian tham chiếu Ephemeris (SOW)

        # --- 1. Tính toán thời gian (t_k) ---
        # t_k là thời gian chênh lệch so với thời gian tham chiếu t_oe
        t_k = t_gps_sow - toe
        # Xử lý trường hợp vượt qua ranh giới tuần (week crossover)
        if t_k > 302400:
            t_k -= 604800
        elif t_k < -302400:
            t_k += 604800

        # --- 2. Bán trục lớn (A) ---
        A = sqrt_a * sqrt_a

        # --- 3. Chuyển động trung bình ban đầu (n0) ---
        n0 = math.sqrt(MU_GPS / (A**3))

        # --- 4. Chuyển động trung bình đã hiệu chỉnh (n) ---
        n = n0 + delta_n

        # --- 5. Dị thường trung bình (M_k) ---
        M_k = m0 + n * t_k

        # --- 6. Dị thường lệch tâm (E_k) - PP lặp Newton-Raphson ---
        # Giải phương trình Kepler: f(E) = E - e*sin(E) - M_k = 0
        # Đạo hàm: f'(E) = 1 - e*cos(E)
        E_k = M_k # Giá trị khởi tạo (M_k là một giá trị khởi tạo tốt)
        for _ in range(10): # Lặp tối đa 10 lần (thường chỉ cần 2-3 lần)
            # Tính f(E_k) và f'(E_k)
            f_E = E_k - e * math.sin(E_k) - M_k
            f_prime_E = 1.0 - e * math.cos(E_k)
            # Tính bước hiệu chỉnh (delta_E)
            # delta_E = f(E_k) / f'(E_k)
            # Tránh chia cho 0 (dù e < 1 nên f_prime_E luôn > 0 cho quỹ đạo elip)
            if abs(f_prime_E) < 1e-15:
                break # Thoát nếu đạo hàm quá nhỏ
            delta_E = f_E / f_prime_E
            # Cập nhật E_k
            E_k = E_k - delta_E
            # Kiểm tra hội tụ (khi bước hiệu chỉnh đã đủ nhỏ)
            if abs(delta_E) < 1e-12:
                break

        # --- 7. Dị thường thực (nu_k) ---
        # Sử dụng atan2 để đảm bảo đúng góc phần tư (Eq 3.19)
        nu_k = math.atan2(
            math.sqrt(1.0 - e**2) * math.sin(E_k),
            math.cos(E_k) - e
        )

        # --- 8. Argument of Latitude (Phi_k) ---
        Phi_k = nu_k + omega

        # --- 9. Hiệu chỉnh bậc hai (Second Harmonic Perturbations) ---
        sin_2Phik = math.sin(2 * Phi_k)
        cos_2Phik = math.cos(2 * Phi_k)

        delta_uk = cus * sin_2Phik + cuc * cos_2Phik # Hiệu chỉnh Argument of Latitude
        delta_rk = crs * sin_2Phik + crc * cos_2Phik # Hiệu chỉnh bán kính
        delta_ik = cis * sin_2Phik + cic * cos_2Phik # Hiệu chỉnh độ nghiêng

        # --- 10. Giá trị đã hiệu chỉnh ---
        u_k = Phi_k + delta_uk # Argument of Latitude đã hiệu chỉnh
        r_k = A * (1.0 - e * math.cos(E_k)) + delta_rk # Bán kính đã hiệu chỉnh
        i_k = i0 + delta_ik + i_dot * t_k # Độ nghiêng đã hiệu chỉnh

        # --- 11. Vị trí vệ tinh trong mặt phẳng quỹ đạo (x_k', y_k') ---
        x_k_prime = r_k * math.cos(u_k)
        y_k_prime = r_k * math.sin(u_k)

        # --- 12. Kinh độ điểm mọc đã hiệu chỉnh (Omega_k) ---
        # (Eq 3.25)
        Omega_k = omega0 + (omega_dot - OMEGA_E_DOT) * t_k - OMEGA_E_DOT * toe

        # --- 13. Tọa độ ECEF (X_k, Y_k, Z_k) ---
        # (Eq 3.26) - Phép quay 3D
        cos_Omegak = math.cos(Omega_k)
        sin_Omegak = math.sin(Omega_k)
        cos_ik = math.cos(i_k)
        sin_ik = math.sin(i_k)

        X_k = x_k_prime * cos_Omegak - y_k_prime * cos_ik * sin_Omegak
        Y_k = x_k_prime * sin_Omegak + y_k_prime * cos_ik * cos_Omegak
        Z_k = y_k_prime * sin_ik

        return (X_k, Y_k, Z_k)

    except (KeyError, TypeError) as e:
        print(f"Lỗi: Thiếu hoặc tham số ephemeris không hợp lệ - {e}", file=sys.stderr)
        return (None, None, None)
    except Exception as e:
        print(f"Lỗi trong quá trình tính toán vị trí vệ tinh: {e}", file=sys.stderr)
        return (None, None, None)

# --- VÍ DỤ SỬ DỤNG ---
if __name__ == "__main__":
    # !!! QUAN TRỌNG: Thay đổi đường dẫn này đến file .nav của bạn !!!
    rinex_file = 'test.nav' # Ví dụ: 'brdc2970.25n'

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
            (X, Y, Z) = calculate_satellite_position(eph_to_use, t_calc_sow)

            if X is not None:
                print("\nKết quả tọa độ ECEF (X, Y, Z) (đơn vị: mét):")
                print(f"X: {X:,.3f} m")
                print(f"Y: {Y:,.3f} m")
                print(f"Z: {Z:,.3f} m")
                
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