import math
import datetime
import sys
from read_rinex_nav import read_rinex_nav
from read_rinex_obs import read_rinex_obs
from cal_sat_pos import calculate_satellite_position

c = 2.99792458e8

def datetime_to_gps_sow(dt):
    gps_epoch = datetime.datetime(1980,1,6,tzinfo=datetime.timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    diff = dt - gps_epoch
    sow = diff.total_seconds() % 604800.0
    week = int(diff.total_seconds() // 604800.0)
    return week, sow


def find_best_ephemeris(eph_list, t_s):
    best = None
    mindt = 999999
    for eph in eph_list:
        toe = eph["Toe"]
        dt = abs(t_s - toe)
        if dt > 302400: dt = 604800 - dt
        if dt < mindt:
            mindt = dt
            best = eph
    if mindt > 14400: 
        return None
    return best


def prepare_basic_solver_inputs(nav_file, obs_file):
    nav = read_rinex_nav(nav_file)
    obs = read_rinex_obs(obs_file)

    epochs = []

    for epoch in obs:
        dt = epoch["time"]
        _, t_r = datetime_to_gps_sow(dt)

        epoch_struct = {
            "time_utc": dt,
            "time_sow": t_r,
            "satellites": []
        }

        for prn, o in epoch["observations"].items():

            if not prn.startswith("G"):
                continue
            if prn not in nav:
                continue

            if "C1C" not in o:
                continue

            rho_raw = o["C1C"]["value"]

            # TGD-trừ trong pseudorange (single frequency)
            best_eph = find_best_ephemeris(nav[prn], t_r)
            if not best_eph: 
                continue

            tgd = best_eph.get("TGD", 0.0) or 0.0

            rho_corr = rho_raw - c*tgd   # ĐÃ SỬA

            t_travel = rho_corr / c
            t_s = t_r - t_travel

            eph = find_best_ephemeris(nav[prn], t_s)
            if not eph:
                continue

            X,Y,Z, dt_sat = calculate_satellite_position(eph, t_s)
            if X is None:
                continue

            epoch_struct["satellites"].append({
                "prn": prn,
                "pseudorange": rho_corr,
                "sat_pos_ecef": (X,Y,Z),
                "sat_clock_corr_meters": c * dt_sat
            })

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