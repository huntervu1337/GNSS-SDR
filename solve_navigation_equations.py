import numpy as np
import math
import sys
from typing import List, Dict, Any, Optional, Tuple

def solve_navigation_equations(epoch_data: Dict[str, Any], initial_pos: List[float]) -> Optional[np.ndarray]:
    """
    Giải hệ phương trình 4 ẩn bằng Bình phương Tối thiểu Lặp (ILS)
    để tìm vị trí máy thu (x_r, y_r, z_r) và sai lệch đồng hồ (c*dt_r).

    Args:
        epoch_data: Một dictionary chứa dữ liệu đã chuẩn bị cho 1 epoch
                    (từ hàm prepare_basic_solver_inputs_demo).
        initial_pos: Vị trí dự đoán ban đầu [x, y, z] (ví dụ: từ header file obs).

    Returns:
        Một mảng numpy 4 phần tử [x_r, y_r, z_r, c_dt_r] nếu hội tụ,
        hoặc None nếu lỗi.
    """
    
    # --- 1. Dự đoán ban đầu ---
    # Bắt đầu với vị trí APPROX POS và sai lệch đồng hồ bằng 0 
    current_solution = np.array([initial_pos[0], initial_pos[1], initial_pos[2], 0.0])
    
    MAX_ITERATIONS = 10
    CONVERGENCE_LIMIT_METERS = 1e-4  # Hội tụ khi độ hiệu chỉnh < 0.1 mm

    # print(f"\n--- Bắt đầu giải cho Epoch: {epoch_data['time_utc']} ---")
    
    for i in range(MAX_ITERATIONS):
        satellites = epoch_data['satellites']
        num_sats = len(satellites)
        
        # Khởi tạo ma trận H và véc-tơ y (delta_rho) 
        H = np.zeros((num_sats, 4))
        y = np.zeros(num_sats)
        
        x_r, y_r, z_r, c_dt_r = current_solution
        
        # --- 2. Xây dựng ma trận H và véc-tơ y ---
        for j, sat in enumerate(satellites):
            rho_i = sat['pseudorange']        # Pseudorange đo được (đã biết)
            xs_i, ys_i, zs_i = sat['sat_pos_ecef'] # Vị trí vệ tinh (đã biết)
            
            # Tính khoảng cách hình học dự đoán (r_i)
            r_i_predicted = math.sqrt(
                (xs_i - x_r)**2 +
                (ys_i - y_r)**2 +
                (zs_i - z_r)**2
            )
            
            # Tính pseudorange dự đoán (rho_predicted) 
            rho_predicted = r_i_predicted + c_dt_r
            
            # Xây dựng véc-tơ y (chênh lệch đo đạc) 
            # y = rho_thực_tế - rho_dự_đoán
            y[j] = rho_i - rho_predicted
            
            # Xây dựng hàng thứ j của ma trận H
            H[j, 0] = (x_r - xs_i) / r_i_predicted
            H[j, 1] = (y_r - ys_i) / r_i_predicted
            H[j, 2] = (z_r - zs_i) / r_i_predicted
            H[j, 3] = 1.0  # Đạo hàm riêng theo c*dt_r

        # --- 3. Giải hệ phương trình tuyến tính ---
        # Tìm véc-tơ hiệu chỉnh x = (H^T H)^-1 * H^T * y
        try:
            H_T = H.T
            H_T_H = H_T @ H
            H_T_H_inv = np.linalg.inv(H_T_H)
            
            # Véc-tơ hiệu chỉnh [dx, dy, dz, d(c*dt_r)]
            x_correction = H_T_H_inv @ H_T @ y
        
        except np.linalg.LinAlgError:
            # Lỗi nếu các vệ tinh thẳng hàng (DOP vô cùng)
            print(f"Lỗi: Ma trận H^T H không thể nghịch đảo (singular matrix) tại epoch {epoch_data['time_utc']}.", file=sys.stderr)
            return None

        # --- 4. Cập nhật dự đoán --- 
        current_solution += x_correction
        
        # --- 5. Kiểm tra hội tụ ---
        # Chỉ kiểm tra độ lớn của hiệu chỉnh vị trí (3 thành phần đầu)
        correction_magnitude = np.linalg.norm(x_correction[:3])
        
        if correction_magnitude < CONVERGENCE_LIMIT_METERS:
            # print(f"Hội tụ sau {i+1} vòng lặp.")
            return current_solution

    # print(f"Cảnh báo: Không hội tụ sau {MAX_ITERATIONS} vòng lặp cho epoch {epoch_data['time_utc']}.")
    return current_solution