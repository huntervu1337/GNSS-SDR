# Global Navigation Satellite Systems software-defined receiver
## Currently for personal use only
# GNSS Single Point Positioning (SPP) Python Implementation

Dự án này là một bộ công cụ phần mềm viết bằng Python để thực hiện kỹ thuật **Định vị Điểm đơn (Single Point Positioning - SPP)**. Chương trình đọc dữ liệu từ các tệp chuẩn RINEX v3 (Navigation & Observation), tính toán vị trí vệ tinh và giải hệ phương trình định vị để tìm tọa độ máy thu.

Dự án được thực hiện dựa trên các thuật toán nền tảng từ tài liệu: *ESA GNSS Data Processing, Vol. 1: Fundamentals and Algorithms*.

## Tính Năng Chính

* **Đọc dữ liệu RINEX v3.xx:**
    * Hỗ trợ đọc file Navigation (`.nav`, `.n`) để lấy lịch vệ tinh (Ephemeris).
    * Hỗ trợ đọc file Observation (`.obs`, `.o`) để lấy giả cự (Pseudorange) và chỉ số cường độ tín hiệu (SSI).
* **Xử lý dữ liệu vệ tinh:**
    * Tính toán tọa độ vệ tinh (X, Y, Z trong hệ ECEF) tại thời điểm phát tín hiệu.
    * Tính toán sai số đồng hồ vệ tinh (Clock Correction), bao gồm cả hiệu ứng tương đối tính (Relativistic effects).
* **Thuật toán định vị:**
    * Đồng bộ hóa dữ liệu quan sát và lịch vệ tinh.
    * Sử dụng phương pháp **Bình phương Tối thiểu Lặp (Iterative Least Squares - ILS)** để giải hệ phương trình phi tuyến tính.
    * Tính toán vị trí máy thu $(x, y, z)$ và độ lệch đồng hồ máy thu $(c \cdot dt_r)$.

## Cấu Trúc Dự Án

| Tên File | Chức Năng |
| :--- | :--- |
| **`main.py`** | Điểm bắt đầu của chương trình. Điều phối luồng xử lý từ đọc dữ liệu đến giải phương trình. |
| `read_rinex_nav.py` | Module đọc và trích xuất tham số quỹ đạo (Ephemeris) từ file RINEX Navigation. |
| `read_rinex_obs.py` | Module đọc và trích xuất dữ liệu quan sát (Pseudorange `C1C`, `L1C`, SSI...) từ file RINEX Observation. |
| `cal_sat_pos.py` | Chứa hàm `calculate_satellite_position`. Thực hiện tính toán vị trí vệ tinh và hiệu chỉnh đồng hồ dựa trên tham số Ephemeris. |
| `prepare_inputs.py` | Module trung gian: Khớp nối thời gian giữa file OBS và NAV, chọn lọc vệ tinh khả dụng, chuẩn bị dữ liệu đầu vào cho bộ giải. |
| `solve_navigation_equations.py` | Chứa thuật toán toán học (Least Squares) để giải hệ phương trình định vị 4 ẩn. |

## 🛠️ Yêu Cầu Cài Đặt

Chương trình yêu cầu Python 3.x và thư viện `numpy` để xử lý ma trận.

```bash
pip install numpy
```
hoặc
```bash
pip install -r requirements.txt
```