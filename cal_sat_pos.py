import math 
import sys
import datetime
from read_rinex_nav import *

MU_GPS = 3.986005e14
OMEGA_E_DOT = 7.2921151467e-5
c = 2.99792458e8
F = -4.442807633e-10

def _datetime_to_sow(dt):
    gps_epoch = datetime.datetime(1980, 1, 6, tzinfo=datetime.timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    delta = dt - gps_epoch
    total_sec = delta.total_seconds()
    return total_sec % 604800.0


def calculate_satellite_position(eph, t_sv):
    """
    Tính vị trí vệ tinh tại t_sv (satellite transmission time)
    + ĐÃ SỬA: clock correction dùng t_sv
    + ĐÃ THÊM: Earth rotation correction
    + ĐÃ SỬA: không trừ TGD trong dt_sat
    """
    try:
        # ======= LẤY THAM SỐ =======
        sqrt_a = eph['sqrt_a']
        e = eph['e']
        m0 = eph['M0']
        omega = eph['omega']
        i0 = eph['i0']
        omega0 = eph['Omega0']
        delta_n = eph['Delta_n']
        i_dot = eph['i_dot']
        omega_dot = eph['Omega_dot']
        cuc = eph['Cuc']; cus = eph['Cus']
        crc = eph['Crc']; crs = eph['Crs']
        cic = eph['Cic']; cis = eph['Cis']
        toe = eph['Toe']

        a0 = eph['a0']; a1 = eph['a1']; a2 = eph['a2']
        tgd = eph.get("TGD", 0.0) or 0.0

        toc = _datetime_to_sow(eph['epoch'])

        # ======= TIME DIFFERENCE (t_k) =======
        t_k = t_sv - toe
        if t_k > 302400: t_k -= 604800
        elif t_k < -302400: t_k += 604800

        # ======= ORBIT COMPUTATION =======
        A = sqrt_a * sqrt_a
        n0 = math.sqrt(MU_GPS / A**3)
        n = n0 + delta_n
        M_k = m0 + n * t_k

        # --- Solve Kepler ---
        E_k = M_k
        for _ in range(8):
            d = (E_k - e*math.sin(E_k) - M_k) / (1 - e*math.cos(E_k))
            E_k -= d
            if abs(d) < 1e-13: break

        nu_k = math.atan2(math.sqrt(1-e*e)*math.sin(E_k),
                          math.cos(E_k)-e)

        Phi_k = nu_k + omega

        sin2 = math.sin(2*Phi_k)
        cos2 = math.cos(2*Phi_k)

        delta_u = cus*sin2 + cuc*cos2
        delta_r = crs*sin2 + crc*cos2
        delta_i = cis*sin2 + cic*cos2

        u = Phi_k + delta_u
        r = A*(1 - e*math.cos(E_k)) + delta_r
        i = i0 + delta_i + i_dot*t_k

        x_orb = r * math.cos(u)
        y_orb = r * math.sin(u)

        Omega_k = omega0 + (omega_dot - OMEGA_E_DOT)*t_k - OMEGA_E_DOT*toe

        X = x_orb*math.cos(Omega_k) - y_orb*math.cos(i)*math.sin(Omega_k)
        Y = x_orb*math.sin(Omega_k) + y_orb*math.cos(i)*math.cos(Omega_k)
        Z = y_orb*math.sin(i)

        # ===========================================================
        #        CLOCK CORRECTION — ĐÃ SỬA
        # ===========================================================
        dt_clk = t_sv - toc
        if dt_clk > 302400: dt_clk -= 604800
        elif dt_clk < -302400: dt_clk += 604800

        dts_poly = a0 + a1*dt_clk + a2*(dt_clk**2)
        dts_rel  = F * e * sqrt_a * math.sin(E_k)

        dt_sat = dts_poly + dts_rel    # KHÔNG TRỪ TGD Ở ĐÂY

        # ===========================================================
        #        EARTH ROTATION CORRECTION
        # ===========================================================
        travel = math.sqrt(X*X + Y*Y + Z*Z) / c
        theta = OMEGA_E_DOT * travel

        X_rot = X*math.cos(theta) + Y*math.sin(theta)
        Y_rot = -X*math.sin(theta) + Y*math.cos(theta)
        Z_rot = Z

        return (X_rot, Y_rot, Z_rot, dt_sat)

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