def read_rinex_nav_v3(filename):
    sats = []
    with open(filename, "r") as f:
        # Bỏ phần header
        for line in f:
            if "END OF HEADER" in line:
                break

        while True:
            header = f.readline()
            if not header:
                break
            if not header.strip():
                continue

            sv = header[0:3].strip()           # e.g. G01
            year = int(header[4:8])
            month = int(header[9:11])
            day = int(header[12:14])
            hour = int(header[15:17])
            minute = int(header[18:20])
            second = float(header[21:23])
            af0 = float(header[23:42].replace('D','E'))
            af1 = float(header[42:61].replace('D','E'))
            af2 = float(header[61:80].replace('D','E'))

            params = []
            for _ in range(7):
                line = f.readline()
                if not line:
                    break
                for k in range(4, 80, 19):
                    chunk = line[k:k+19].replace('D','E').strip()
                    if chunk:
                        try:
                            params.append(float(chunk))
                        except ValueError:
                            chunk = chunk.replace(' ', '')
                            params.append(float(chunk))

            if len(params) < 24:
                continue  # thiếu dữ liệu

            eph = {
                "PRN": sv,
                "epoch": (year, month, day, hour, minute, second),
                "af0": af0, "af1": af1, "af2": af2,
                "IODE": params[0], "Crs": params[1], "Delta_n": params[2], "M0": params[3],
                "Cuc": params[4], "e": params[5], "Cus": params[6], "sqrtA": params[7],
                "Toe": params[8], "Cic": params[9], "Omega0": params[10], "Cis": params[11],
                "i0": params[12], "Crc": params[13], "omega": params[14], "Omega_dot": params[15],
                "i_dot": params[16],
                "Week": params[18] if len(params) > 18 else None,
                "sv_acc": params[20] if len(params) > 20 else None,
                "sv_health": params[21] if len(params) > 21 else None,
                "TGD": params[22] if len(params) > 22 else None,
                "IODC": params[23] if len(params) > 23 else None,
            }
            sats.append(eph)

    return sats

nav = read_rinex_nav_v3("nav.nav")
print(f"Found ephemeris for {len(nav)} satellites")
for k, v in nav[0].items():
    print(f"{k:10s}: {v}")
