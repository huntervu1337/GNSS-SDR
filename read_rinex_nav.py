import datetime
import sys
import collections # Dùng defaultdict cho tiện

def _parse_float(s):
    """
    Hàm phụ trợ để phân tích chuỗi số thực RINEX (bao gồm mũ 'D').
    Loại bỏ khoảng trắng thừa và chuyển đổi D -> E.
    Trả về None nếu không thể chuyển đổi.
    """
    try:
        # Thay thế 'D' bằng 'E' và loại bỏ khoảng trắng ở đầu/cuối
        cleaned_s = s.replace('D', 'E').strip()
        if not cleaned_s: # Nếu chuỗi rỗng sau khi làm sạch
            return None
        return float(cleaned_s)
    except ValueError:
        # Thử loại bỏ tất cả khoảng trắng nếu vẫn lỗi (ít gặp hơn)
        try:
            cleaned_s = s.replace('D', 'E').replace(' ', '')
            if not cleaned_s:
                return None
            return float(cleaned_s)
        except ValueError:
            print(f"Warning: Could not parse float from '{s}'", file=sys.stderr)
            return None # Trả về None nếu không parse được

def read_rinex_nav(file_path):
    """
    Đọc file GPS Navigation RINEX v3.0x  và trích xuất
    các tham số ephemeris cần thiết để tính toán tọa độ vệ tinh
    Phiên bản này đã sửa lỗi để xử lý các file .nav có dòng trống hoặc không mong muốn.

    Args:
        file_path (str): Đường dẫn đến file RINEX navigation.

    Returns:
        dict: Một dictionary (giống map trong C++) dạng {prn: [eph1, eph2, ...]}, trong đó prn là
              mã vệ tinh (str, vd: 'G01') và value là list các dictionary
              ephemeris cho từng epoch của vệ tinh đó.
              Trả về None nếu file không đọc được hoặc không hợp lệ.
    """
    # Dùng defaultdict(list) để dễ dàng thêm ephemeris cho vệ tinh mới
    ephemeris_data = collections.defaultdict(list)
    try:
        with open(file_path, 'r') as f:
            # --- Bỏ qua Header ---
            while True:
                line = f.readline()
                if not line: # Kiểm tra cuối file sớm
                    print("Error: File appears empty or only contains header.", file=sys.stderr)
                    return None
                if "END OF HEADER" in line:
                    break

            # --- Đọc Dữ liệu Ephemeris ---
            while True:
                # Đọc dòng 1: SV Epoch / SV Clock
                line1 = f.readline()
                if not line1: # Đã đọc hết file
                    break
                if not line1.strip(): # Bỏ qua dòng trống
                    continue

                try:
                    # Phân tích dòng 1
                    sat_prn = line1[0:3].strip() 

                    # *** SỬA LỖI CHÍNH (BUG 3) ***
                    # Nếu dòng này không phải là một PRN hợp lệ, 
                    # chỉ bỏ qua dòng NÀY và tiếp tục tìm.
                    # KHÔNG bỏ qua 7 dòng tiếp theo.
                    if not sat_prn or sat_prn[0] not in 'GECJIRS': 
                        # print(f"Warning: Skipping non-record line: '{line1.strip()}'", file=sys.stderr)
                        continue # Chỉ bỏ qua dòng này, lặp lại vòng while

                    year = int(line1[4:8])
                    month = int(line1[9:11])
                    day = int(line1[12:14])
                    hour = int(line1[15:17])
                    minute = int(line1[18:20])
                    # Xử lý giây cẩn thận hơn
                    sec_str = line1[21:23]
                    second = float(sec_str) if sec_str.strip() else 0.0
                    epoch_time = datetime.datetime(year, month, day, hour, minute, int(second), int((second % 1)*1e6) )

                    sv_clock_bias = _parse_float(line1[23:42]) # a0
                    sv_clock_drift = _parse_float(line1[42:61]) # a1
                    sv_clock_drift_rate = _parse_float(line1[61:80]) # a2

                    # Đọc 7 dòng orbit parameters
                    params_list = []
                    for i_line in range(7):
                        line = f.readline()
                        if not line: # Nếu hết file giữa chừng
                            raise EOFError(f"Incomplete record for {sat_prn}. Reached EOF.")
                        
                        # Xử lý các dòng trống (nếu có) BÊN TRONG một bản ghi
                        if not line.strip():
                            params_list.extend([None, None, None, None])
                            continue

                        # Lấy 4 tham số trên mỗi dòng orbit
                        for k in range(4, 80, 19):
                            if k < len(line): # Đảm bảo dòng đủ dài
                                chunk = line[k:min(k+19, len(line))]
                            else:
                                chunk = "" # Nếu dòng quá ngắn
                            params_list.append(_parse_float(chunk))
                    
                    # --- Kiểm tra các tham số quan trọng (BUG 5) ---
                    # Kiểm tra xem các giá trị BẮT BUỘC có bị None không
                    critical_indices = [3, 5, 7, 8, 9, 10, 11, 12, 14, 15, 16] # M0, e, sqrt_a, Toe, etc.
                    

                    # --- Kiểm tra số lượng tham số đọc được ---
                    # Cần ít nhất 17 tham số orbit (đến i_dot) từ dòng 2-6
                    # Chuẩn RINEX v3 có thể có tới 28 tham số (hết dòng 8)
                    if len(params_list) < 17:
                         raise ValueError(f"Incomplete parameter list ({len(params_list)} < 17)")

                    if sv_clock_bias is None or sv_clock_drift is None or sv_clock_drift_rate is None:
                         raise ValueError(f"Clock parameter is None.")

                    for i in critical_indices:
                        if params_list[i] is None:
                            raise ValueError(f"Critical parameter {i} ('{params_list[i]}') is None.")

                    # --- Gán tham số vào dictionary theo tên chuẩn ---
                    # Thứ tự tham số trong list tương ứng với thứ tự trong file RINEX v3
                    # Ánh xạ tới tên trong Bảng 3.8 và/hoặc tên chuẩn RINEX
                    epoch_params = {
                        'epoch': epoch_time,
                        # Clock (từ line1) - Đặt tên theo Bảng 3.8
                        'a0': sv_clock_bias,
                        'a1': sv_clock_drift,
                        'a2': sv_clock_drift_rate,
                        # Orbit params (từ params_list) - Tên theo Bảng 3.8 / RINEX chuẩn
                        'IODE': params_list[0],  # Hoặc Issue of Data, Ephemeris
                        'Crs': params_list[1],
                        'Delta_n': params_list[2], # Delta n
                        'M0': params_list[3],      # Mean Anomaly at Reference Time
                        'Cuc': params_list[4],
                        'e': params_list[5],       # Eccentricity
                        'Cus': params_list[6],
                        'sqrt_a': params_list[7],  # Square Root of Semi-Major Axis
                        'Toe': params_list[8],     # Time of Ephemeris (sec of GPS week) -> t_oe
                        'Cic': params_list[9],
                        'Omega0': params_list[10], # Longitude of Ascending Node of Orbit Plane at Weekly Epoch -> Omega_r
                        'Cis': params_list[11],
                        'i0': params_list[12],     # Inclination Angle at Reference Time
                        'Crc': params_list[13],
                        'omega': params_list[14],  # Argument of Perigee
                        'Omega_dot': params_list[15], # Rate of Right Ascension -> Omega dot
                        'i_dot': params_list[16],  # Rate of Inclination Angle -> i dot
                        # Các tham số tùy chọn khác từ dòng 6, 7, 8 (nếu có)
                        'L2_codes': params_list[17] if len(params_list) > 17 else None, # Codes on L2 channel
                        'GPS_Week': params_list[18] if len(params_list) > 18 else None, # GPS Week Number (truncated)
                        'L2_Pflag': params_list[19] if len(params_list) > 19 else None, # L2 P data flag
                        'SV_acc': params_list[20] if len(params_list) > 20 else None,   # SV accuracy (m)
                        'SV_health': params_list[21] if len(params_list) > 21 else None, # SV health (bits 17-22 w 4 sf 1)
                        'TGD': params_list[22] if len(params_list) > 22 else None,      # Total Group Delay (L1/L2) (sec)
                        'IODC': params_list[23] if len(params_list) > 23 else None,     # Issue of Data, Clock
                        'TransTime': params_list[24] if len(params_list) > 24 else None, # Transmission time of message (sec of GPS week)
                        'FitInterval': params_list[25] if len(params_list) > 25 else None, # Fit interval (hours) - GPS/QZSS only
                    }

                    # Thêm vào dictionary chính
                    ephemeris_data[sat_prn].append(epoch_params)

                # *** SỬA LỖI CHÍNH (BUG 2) ***
                except (ValueError, IndexError, TypeError, AttributeError, EOFError) as e:
                    # Nếu CÓ LỖI khi đang đọc 8 dòng (vd: EOF, parse int/float lỗi,...)
                    # Báo lỗi và BỎ QUA bản ghi này.
                    # Vòng lặp while True sẽ tự động đọc dòng tiếp theo
                    # để tìm 1 header mới. KHÔNG CẦN skip 7 dòng.
                    print(f"Warning: Skipping corrupted record starting with '{line1.strip()}'. Error: {e}", file=sys.stderr)
                    continue 
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"An unexpected error occurred while processing {file_path}: {e}", file=sys.stderr)
        return None

    # Chuyển defaultdict thành dict thông thường trước khi trả về (tùy chọn)
    return dict(ephemeris_data)

# --- Ví dụ Sử dụng ---
if __name__ == "__main__":
    # Đường dẫn đến file navigation
    rinex_file = "2908-nav-base.nav"

    print(f"Attempting to read RINEX file: {rinex_file}")
    nav_data = read_rinex_nav(rinex_file)

    if nav_data:
        print("\nSuccessfully parsed RINEX data.")
        print(f"Found ephemeris for {len(nav_data)} satellites: {sorted(nav_data.keys())}")

        # In ephemeris cho một vệ tinh ví dụ, vd: 'G05'
        example_sat = 'G05' # Thay đổi nếu muốn xem vệ tinh khác
        if example_sat in nav_data:
            print(f"\nExample Ephemeris for {example_sat} (first epoch found):")
            first_epoch = nav_data[example_sat][0]
            # Chỉ in các tham số cần cho tính toán vị trí theo Bảng 3.8
            keys_to_print = ['epoch', 'Toe', 'sqrt_a', 'e', 'M0', 'omega', 'i0', 'Omega0',
                             'Delta_n', 'i_dot', 'Omega_dot', 'Cuc', 'Cus', 'Crc', 'Crs',
                             'Cic', 'Cis', 'a0', 'a1', 'a2']
            for key in keys_to_print:
                value = first_epoch.get(key) # Dùng get để tránh lỗi nếu key thiếu
                if value is not None:
                    if isinstance(value, float):
                        print(f"  {key:<12}: {value:.11E}")
                    else:
                        print(f"  {key:<12}: {value}")
                else:
                     print(f"  {key:<12}: Not found")
    #     else:
    #         if nav_data: # Chỉ thực hiện nếu có dữ liệu
    #              first_sat = list(nav_data.keys())[0]
    #              print(f"\nSatellite {example_sat} not found. Showing first epoch for {first_sat}:")
    #              first_epoch = nav_data[first_sat][0]
    #              keys_to_print = ['epoch', 'Toe', 'sqrt_a', 'e', 'M0', 'omega', 'i0', 'Omega0',
    #                               'Delta_n', 'i_dot', 'Omega_dot', 'Cuc', 'Cus', 'Crc', 'Crs',
    #                               'Cic', 'Cis', 'a0', 'a1', 'a2']
    #              for key in keys_to_print:
    #                  value = first_epoch.get(key)
    #                  if value is not None:
    #                      if isinstance(value, float):
    #                          print(f"  {key:<12}: {value:.14E}")
    #                      else:
    #                          print(f"  {key:<12}: {value}")
    #                  else:
    #                       print(f"  {key:<12}: Not found")
    #         else:
    #              print(f"\nSatellite {example_sat} not found, and no other satellite data parsed.")

    # else:
    #     print("\nFailed to parse RINEX data. Please check the file path and format.")