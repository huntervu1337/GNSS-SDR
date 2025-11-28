import math

def ecef_to_lla(x, y, z):
    """
    Chuyển đổi tọa độ ECEF (X, Y, Z) sang Latitude, Longitude, Height (WGS84).
    
    Args:
        x, y, z (float): Tọa độ ECEF đơn vị mét.
        
    Returns:
        tuple: (lat, lon, height)
            - lat: Vĩ độ (độ, -90 đến 90)
            - lon: Kinh độ (độ, -180 đến 180)
            - height: Độ cao so với bề mặt elipxoid (mét)
    """
    # --- Hằng số WGS-84 ---
    a = 6378137.0              # Bán trục lớn (Semi-major axis)
    f = 1 / 298.257223563      # Độ dẹt (Flattening)
    b = a * (1 - f)            # Bán trục nhỏ (Semi-minor axis)
    e2 = 2*f - f**2            # Bình phương tâm sai thứ nhất (First eccentricity squared)
    ep2 = (a**2 - b**2) / b**2 # Bình phương tâm sai thứ hai (Second eccentricity squared)
    
    # --- Tính toán ---
    # 1. Tính Kinh độ (Longitude)
    lon = math.atan2(y, x)
    
    # 2. Tính Vĩ độ (Latitude) và Độ cao (Height)
    # Sử dụng thuật toán lặp (Iterative method) hoặc thuật toán Bowring (độ chính xác cao, không lặp)
    # Dưới đây là thuật toán Bowring (thông dụng và chính xác cho GNSS)
    
    p = math.sqrt(x**2 + y**2)
    theta = math.atan2(z * a, p * b)
    
    lat = math.atan2(
        z + ep2 * b * math.sin(theta)**3,
        p - e2 * a * math.cos(theta)**3
    )
    
    # Tính bán kính cong tại vĩ độ (Radius of curvature in the prime vertical)
    N = a / math.sqrt(1 - e2 * math.sin(lat)**2)
    
    height = p / math.cos(lat) - N
    
    # Chuyển đổi sang độ (Degrees)
    lat_deg = math.degrees(lat)
    lon_deg = math.degrees(lon)
    
    return lat_deg, lon_deg, height

# --- Ví dụ sử dụng ---
if __name__ == "__main__":
    # Tọa độ XYZ ví dụ (từ kết quả chạy trước của bạn hoặc file header OBS)
    # x = -1626584.706
    # y = 5730519.457
    # z = 2271864.392
    
    # Tọa độ máy thu tính được từ bài trước (giả sử):
    x_rec = -1626587.9382125922
    y_rec = 5730550.070124399
    z_rec = 2271878.444405352
    
    lat, lon, h = ecef_to_lla(x_rec, y_rec, z_rec)
    
    print(f"--- ECEF Coordinates ---")
    print(f"X: {x_rec} m")
    print(f"Y: {y_rec} m")
    print(f"Z: {z_rec} m")
    
    print(f"\n--- WGS84 Geodetic Coordinates ---")
    print(f"Latitude  : {lat} degrees")
    print(f"Longitude : {lon} degrees")
    print(f"Height    : {h} meters")