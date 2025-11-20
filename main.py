from prepare_inputs import *
from solve_navigation_equations import *

if __name__ == "__main__":
    
    NAV_FILE = '2908-nav-base.nav' # File .nav 
    OBS_FILE = 'test.obs' # File .obs

    # Vị trí dự đoán ban đầu, lấy từ header file .obs thì hội tụ nhanh hơn
    # File test.obs có dòng: -1626584.7059 5730519.4572 2271864.3916 APPROX POSITION XYZ
    # APPROX_POS_XYZ = [-1626584.7059, 5730519.4572, 2271864.3916] # Từ header

    APPROX_POS_XYZ = [0, 0, 0] # Từ tâm trái đất
    
    # 1. Chuẩn bị dữ liệu
    solver_data = prepare_basic_solver_inputs(NAV_FILE, OBS_FILE)

    if solver_data:
        # 2. Lấy dữ liệu của epoch đầu tiên
        first_epoch_data = solver_data[0]
        print(f"\n--- BẮT ĐẦU GIẢI HỆ PHƯƠNG TRÌNH CHO EPOCH ĐẦU TIÊN ---")
        print(f"Thời gian: {first_epoch_data['time_utc']}")
        print(f"Dự đoán ban đầu (X, Y, Z): {APPROX_POS_XYZ}")
        print(f"Số vệ tinh sử dụng: {len(first_epoch_data['satellites'])}")

        # 3. Gọi hàm giải
        final_solution = solve_navigation_equations(first_epoch_data, APPROX_POS_XYZ)

        if final_solution is not None:
            x_receiver = final_solution[0]
            y_receiver = final_solution[1]
            z_receiver = final_solution[2]
            clock_bias_meters = final_solution[3]
            
            print("\n--- KẾT QUẢ TÍNH TOÁN (VỊ TRÍ MÁY THU) ---")
            print(f"  Vị trí X: {x_receiver:.3f} m")
            print(f"  Vị trí Y: {y_receiver:.3f} m")
            print(f"  Vị trí Z: {z_receiver:.3f} m")
            print(f"  Sai lệch đồng hồ (c*dt_r): {clock_bias_meters:.3f} m")
            print(f"  (Nghĩa là đồng hồ máy thu chạy lệch ~ {clock_bias_meters / c * 1e9:.1f} nano-second)")
        else:
            print("\nGiải hệ phương trình thất bại.")

    else:
        print("\nKhông có dữ liệu nào được chuẩn bị để giải.")