import datetime
import sys
import collections

def _parse_obs_value(chunk):
    """
    Hàm phụ trợ để phân tích một khối quan sát 16 ký tự (F14.3, I1, I1).
    Trả về (value, ssi)
    """
    value = None
    ssi = None

    # Giá trị chính (F14.3) là 14 ký tự đầu tiên
    if len(chunk) >= 14:
        value_str = chunk[0:14].strip()
        if value_str:
            try:
                value = float(value_str)
            except ValueError:
                value = None  # Lỗi hoặc giá trị trống

    # SSI (I1) là ký tự thứ 16 (index 15)
    if len(chunk) >= 16:
        ssi_str = chunk[15:16].strip()  # Lấy ký tự tại index 15
        if ssi_str:
            try:
                ssi = int(ssi_str)
            except ValueError:
                ssi = None  # Lỗi hoặc trống

    return (value, ssi)

def read_rinex_obs(file_path):
    """
    Đọc file RINEX v3.0x Observation và trích xuất các giá trị quan sát.

    Args:
        file_path (str): Đường dẫn đến file RINEX observation (.obs).

    Returns:
        list: Một danh sách (list) các dictionary, mỗi dictionary
              đại diện cho một epoch (mốc thời gian).
              Cấu trúc:
              [
                  {
                      "time": datetime_object,
                      "observations": {
                          "G05": {
                              "C1C": {"value": 20123456.789, "ssi": 7},
                              "L1C": {"value": 109269531.790, "ssi": 7},
                              ...
                          },
                          "R21": { ... },
                          ...
                      }
                  },
                  ...
              ]
    """
    all_epochs_data = []
    # obs_types sẽ lưu map: {'G': ['C1C', 'L1C', ...], 'R': ['C1C', 'L1C', ...]}
    obs_types = {}  

    try:
        with open(file_path, 'r') as f:
            # --- 1. Đọc Header ---
            while True:
                line = f.readline()
                if not line:
                    print("Lỗi: File rỗng hoặc không có END OF HEADER.", file=sys.stderr)
                    return None
                
                if "SYS / # / OBS TYPES" in line:
                    parts = line.split()
                    sys_id = parts[0]  # 'G', 'R', 'E', ... 
                    
                    # Tìm vị trí kết thúc của danh sách types
                    end_index = -1
                    for i, part in enumerate(parts):
                        if part == 'SYS':
                            end_index = i
                            break
                    
                    if end_index != -1:
                         # Lấy các loại quan sát (ví dụ: C1C, L1C, S1C, ...) 
                        obs_types[sys_id] = parts[2:end_index] 
                    
                    # (Bỏ qua xử lý các dòng tiếp theo (continuation lines) 
                    # vì file test.obs không sử dụng chúng)

                if "END OF HEADER" in line:
                    break

            if not obs_types:
                print("Lỗi: Không tìm thấy 'SYS / # / OBS TYPES' trong header.", file=sys.stderr)
                return None

            # --- 2. Đọc Dữ liệu (Data Body) ---
            while True:
                epoch_line = f.readline()
                if not epoch_line:
                    break  # Hết file
                
                if epoch_line.startswith('>'):
                    # Bắt đầu một epoch mới
                    parts = epoch_line.split()
                    try:
                        year = int(parts[1])
                        month = int(parts[2])
                        day = int(parts[3])
                        hour = int(parts[4])
                        minute = int(parts[5])
                        sec_full = float(parts[6])
                        second = int(sec_full)
                        microsecond = int((sec_full - second) * 1_000_000)
                        
                        epoch_time = datetime.datetime(year, month, day, hour, minute, second, microsecond)
                        num_sats = int(parts[8])
                        
                        epoch_data = {
                            "time": epoch_time,
                            "observations": collections.defaultdict(dict)
                        }

                        # Đọc các dòng quan sát của N vệ tinh
                        for _ in range(num_sats):
                            obs_line = f.readline()
                            if not obs_line:
                                break 
                            
                            prn = obs_line[0:3].strip() # ví dụ: 'G05', 'R21' [cite: 4390, 4392]
                            sys_id = prn[0] # 'G', 'R', ...
                            
                            # Lấy danh sách các loại obs cho hệ thống này
                            types_for_sys = obs_types.get(sys_id)
                            if not types_for_sys:
                                continue # Bỏ qua nếu không có định nghĩa (vd: 'S' cho SBAS)

                            line_data = obs_line[3:] # Dữ liệu bắt đầu từ cột 4
                            sat_obs = {}

                            # Mỗi quan sát chiếm 16 ký tự
                            for i, obs_code in enumerate(types_for_sys):
                                start_idx = i * 16
                                end_idx = start_idx + 16
                                
                                if len(line_data) < start_idx + 14: # Cần ít nhất 14 ký tự cho 1 giá trị
                                    break
                                
                                chunk = line_data[start_idx:end_idx]
                                (value, ssi) = _parse_obs_value(chunk)
                                
                                if value is not None:
                                    sat_obs[obs_code] = {"value": value, "ssi": ssi}
                            
                            if sat_obs:
                                epoch_data["observations"][prn] = sat_obs

                        all_epochs_data.append(epoch_data)

                    except (ValueError, IndexError, TypeError) as e:
                        print(f"Lỗi khi phân tích epoch: '{epoch_line.strip()}'. Lỗi: {e}", file=sys.stderr)
                        continue

    except FileNotFoundError:
        print(f"Lỗi: Không tìm thấy file tại {file_path}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Lỗi không mong muốn: {e}", file=sys.stderr)
        return None

    return all_epochs_data

# --- VÍ DỤ SỬ DỤNG ---
if __name__ == "__main__":
    # Đường dẫn đến file
    obs_file = 'test.obs' 

    print(f"Đang đọc file Observation: {obs_file}")
    all_obs_data = read_rinex_obs(obs_file)

    if all_obs_data:
        print(f"\nĐọc thành công! Tìm thấy {len(all_obs_data)} mốc thời gian (epochs).")

        # Lấy dữ liệu của epoch đầu tiên
        first_epoch = all_obs_data[0]
        print(f"\n--- Dữ liệu Epoch đầu tiên ({first_epoch['time']}) ---")
        
        # In dữ liệu pseudorange C1C cho vệ tinh G05
        example_sat = 'G05'
        if example_sat in first_epoch['observations']:
            sat_data = first_epoch['observations'][example_sat]
            
            if 'C1C' in sat_data:
                print(f"Dữ liệu cho vệ tinh {example_sat}:")
                pr_data = sat_data['C1C']
                print(f"  - Pseudorange (C1C): {pr_data['value']:>14.3f} m")
                print(f"  - SSI (0-9)       : {pr_data['ssi']}")
            else:
                print(f"Không tìm thấy quan sát 'C1C' cho {example_sat}.")

        else:
            print(f"Không tìm thấy vệ tinh {example_sat} trong epoch đầu tiên.")
    else:
        print("\nKhông thể đọc dữ liệu từ file observation.")