"""
create_grps_database.py
-----------------------
Creates the GRPS SQL Server database and populates the following tables
with randomly generated data:

    • Drivers    – delivery drivers
    • Vehicles   – van / truck fleet
    • Customers  – delivery recipients in Serbia
    • Routes     – optimised delivery routes (links Drivers, Vehicles, Customers)

Usage
-----
    python create_grps_database.py

The script mirrors the DatabaseManager connection pattern used in
FilteredBackendApplication.py (pyodbc, Trusted_Connection / Windows Auth,
localhost SQL Server).  Run it once before starting the GRPS Flask app.
"""

import random
import string
from datetime import datetime, timedelta

import pyodbc

# ─────────────────────────────────────────────────────────────────────────────
# CONNECTION SETTINGS  (match FilteredBackendApplication.py Config)
# ─────────────────────────────────────────────────────────────────────────────

SQL_SERVERS = ["localhost"]          # add more if needed
DATABASE    = "GRPS"                 # database that will be created / used
SEED        = 42                     # reproducible random data

# ─────────────────────────────────────────────────────────────────────────────
# SEED RANDOM
# ─────────────────────────────────────────────────────────────────────────────

random.seed(SEED)

# ─────────────────────────────────────────────────────────────────────────────
# HELPER UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def _find_driver_and_connect():
    """
    Iterate over SQL_SERVERS × available ODBC drivers and return the first
    working (server, driver, connection) triple.  Matches the logic in
    DatabaseManager.test_server_connections().
    """
    available_drivers = [d for d in pyodbc.drivers() if "SQL Server" in d]
    for server in SQL_SERVERS:
        for driver in available_drivers:
            try:
                conn_str = (
                    f"DRIVER={driver};"
                    f"SERVER={server};"
                    f"DATABASE=master;"
                    f"Trusted_Connection=yes;"
                )
                conn = pyodbc.connect(conn_str, timeout=5)
                print(f"  ✓ Connected: {server}  driver={driver}")
                return server, driver, conn
            except Exception:
                continue
    raise RuntimeError(
        "No working SQL Server connection found.  "
        "Make sure SQL Server is running and Windows Authentication is enabled."
    )


def _get_connection(server, driver, database="master"):
    conn_str = (
        f"DRIVER={driver};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"Trusted_Connection=yes;"
    )
    return pyodbc.connect(conn_str)


def _exec(cursor, sql, params=None):
    if params:
        cursor.execute(sql, params)
    else:
        cursor.execute(sql)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 – CREATE DATABASE
# ─────────────────────────────────────────────────────────────────────────────

def create_database(server, driver):
    """Create the GRPS database if it does not already exist."""
    conn = _get_connection(server, driver, "master")
    conn.autocommit = True          # CREATE DATABASE must run outside a transaction
    cursor = conn.cursor()
    cursor.execute(
        f"IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = '{DATABASE}') "
        f"CREATE DATABASE [{DATABASE}]"
    )
    print(f"  ✓ Database [{DATABASE}] ready.")
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 – CREATE TABLES
# ─────────────────────────────────────────────────────────────────────────────

TABLES_DDL = {

    # ------------------------------------------------------------------
    "Drivers": """
        CREATE TABLE dbo.Drivers (
            DriverID        INT           IDENTITY(1,1) PRIMARY KEY,
            FirstName       NVARCHAR(50)  NOT NULL,
            LastName        NVARCHAR(50)  NOT NULL,
            LicenseNumber   NVARCHAR(20)  NOT NULL UNIQUE,
            LicenseClass    NVARCHAR(5)   NOT NULL,   -- B, C, C+E, etc.
            PhoneNumber     NVARCHAR(20),
            Email           NVARCHAR(100),
            HireDate        DATE          NOT NULL,
            IsActive        BIT           NOT NULL DEFAULT 1,
            WageRSD_PerHour FLOAT         NOT NULL DEFAULT 900.0,
            CreatedAt       DATETIME2     NOT NULL DEFAULT GETDATE()
        )
    """,

    # ------------------------------------------------------------------
    "Vehicles": """
        CREATE TABLE dbo.Vehicles (
            VehicleID           INT           IDENTITY(1,1) PRIMARY KEY,
            LicensePlate        NVARCHAR(15)  NOT NULL UNIQUE,
            VehicleType         NVARCHAR(30)  NOT NULL,   -- Van, Truck, etc.
            Brand               NVARCHAR(30),
            Model               NVARCHAR(30),
            Year                INT,
            VolumeCapacityM3    FLOAT         NOT NULL DEFAULT 10.0,
            WeightCapacityKG    FLOAT         NOT NULL DEFAULT 1000.0,
            FuelConsumptionL100 FLOAT         NOT NULL DEFAULT 10.0,
            FuelType            NVARCHAR(15)  NOT NULL DEFAULT 'Diesel',
            IsAvailable         BIT           NOT NULL DEFAULT 1,
            LastServiceDate     DATE,
            CreatedAt           DATETIME2     NOT NULL DEFAULT GETDATE()
        )
    """,

    # ------------------------------------------------------------------
    "Customers": """
        CREATE TABLE dbo.Customers (
            CustomerID      INT           IDENTITY(1,1) PRIMARY KEY,
            CustomerName    NVARCHAR(100) NOT NULL,
            ContactPerson   NVARCHAR(100),
            Address         NVARCHAR(200) NOT NULL,
            City            NVARCHAR(50)  NOT NULL DEFAULT 'Belgrade',
            PostalCode      NVARCHAR(10),
            Latitude        FLOAT,
            Longitude       FLOAT,
            PhoneNumber     NVARCHAR(20),
            Email           NVARCHAR(100),
            TimeWindowStart TIME          NOT NULL DEFAULT '09:00:00',
            TimeWindowEnd   TIME          NOT NULL DEFAULT '17:00:00',
            UnloadingTimeMin INT           NOT NULL DEFAULT 10,
            Packages1       INT           NOT NULL DEFAULT 0,   -- small parcels ~5 kg
            Packages2       INT           NOT NULL DEFAULT 0,   -- medium boxes ~15 kg
            Packages3       INT           NOT NULL DEFAULT 0,   -- large items ~30 kg
            IsActive        BIT           NOT NULL DEFAULT 1,
            CreatedAt       DATETIME2     NOT NULL DEFAULT GETDATE()
        )
    """,

    # ------------------------------------------------------------------
    "Routes": """
        CREATE TABLE dbo.Routes (
            RouteID             INT           IDENTITY(1,1) PRIMARY KEY,
            RouteDate           DATE          NOT NULL,
            DriverID            INT           NOT NULL
                REFERENCES dbo.Drivers(DriverID),
            VehicleID           INT           NOT NULL
                REFERENCES dbo.Vehicles(VehicleID),
            DepotName           NVARCHAR(100) NOT NULL DEFAULT 'Main Depot Belgrade',
            DepotLat            FLOAT         NOT NULL DEFAULT 44.8125,
            DepotLng            FLOAT         NOT NULL DEFAULT 20.4612,
            AlgorithmUsed       NVARCHAR(20)  NOT NULL DEFAULT 'ALNS',
            MatrixSource        NVARCHAR(20)  NOT NULL DEFAULT 'osrm',
            TotalDistanceKM     FLOAT,
            TotalFuelLitres     FLOAT,
            FuelCostRSD         FLOAT,
            WageCostRSD         FLOAT,
            TotalCostRSD        FLOAT,
            WorkingHours        FLOAT,
            DepartureTime       TIME,
            ReturnTime          TIME,
            VolumeUsedM3        FLOAT,
            WeightUsedKG        FLOAT,
            NumStops            INT,
            Status              NVARCHAR(20)  NOT NULL DEFAULT 'Planned',
            -- Status: Planned / In Progress / Completed / Cancelled
            Notes               NVARCHAR(500),
            CreatedAt           DATETIME2     NOT NULL DEFAULT GETDATE(),

            -- Many-to-many route ↔ customer is stored in RouteStops
            -- Route-level FK constraints above ensure referential integrity
        )
    """,

    # ------------------------------------------------------------------
    # Junction / detail table: one row per stop within a route
    "RouteStops": """
        CREATE TABLE dbo.RouteStops (
            StopID          INT      IDENTITY(1,1) PRIMARY KEY,
            RouteID         INT      NOT NULL
                REFERENCES dbo.Routes(RouteID),
            CustomerID      INT      NOT NULL
                REFERENCES dbo.Customers(CustomerID),
            StopSequence    INT      NOT NULL,
            ArrivalTime     TIME,
            DepartureTime   TIME,
            WaitMinutes     INT      NOT NULL DEFAULT 0,
            TWViolationMin  INT      NOT NULL DEFAULT 0,
            ServiceTimeMin  INT      NOT NULL DEFAULT 10,
            Packages1       INT      NOT NULL DEFAULT 0,
            Packages2       INT      NOT NULL DEFAULT 0,
            Packages3       INT      NOT NULL DEFAULT 0,
            VolumeM3        FLOAT,
            WeightKG        FLOAT,
            IsDelivered     BIT      NOT NULL DEFAULT 0,
            CreatedAt       DATETIME2 NOT NULL DEFAULT GETDATE()
        )
    """,
}


def create_tables(conn):
    """Drop-and-recreate all GRPS tables (idempotent)."""
    cursor = conn.cursor()

    # Drop in reverse dependency order
    for tbl in ["RouteStops", "Routes", "Customers", "Vehicles", "Drivers"]:
        cursor.execute(
            f"IF OBJECT_ID('dbo.{tbl}', 'U') IS NOT NULL DROP TABLE dbo.{tbl}"
        )
    conn.commit()

    for tbl, ddl in TABLES_DDL.items():
        cursor.execute(ddl)
        print(f"  ✓ Table dbo.{tbl} created.")
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 – RANDOM DATA GENERATORS
# ─────────────────────────────────────────────────────────────────────────────

# ── Serbian first/last names ─────────────────────────────────────────────────
FIRST_NAMES = [
    "Aleksandar", "Nikola", "Stefan", "Marko", "Dragan", "Zoran", "Miloš",
    "Nemanja", "Luka", "Ivan", "Ana", "Milica", "Jelena", "Marija", "Ivana",
    "Tamara", "Maja", "Nataša", "Jovana", "Katarina",
]
LAST_NAMES = [
    "Jovanović", "Petrović", "Nikolić", "Đorđević", "Popović", "Todorović",
    "Stojanović", "Ilić", "Marković", "Simić", "Lukić", "Stanković",
    "Radovanović", "Milosavljević", "Vasiljević",
]

# ── Belgrade streets (real-sounding) ─────────────────────────────────────────
BELGRADE_STREETS = [
    "Knez Mihailova", "Terazije", "Bulevar kralja Aleksandra",
    "Bulevar oslobođenja", "Nemanjina", "Kralja Milana",
    "Vojvode Stepe", "Cara Dušana", "Zmaj Jovina",
    "Ustaničke", "Požeška", "Vojislava Ilića",
    "Deligradska", "Resavska", "Birčaninova",
    "Patrijarha Dimitrija", "Jurija Gagarina",
]

# ── Belgrade neighbourhoods (bounding box ±0.05°) ────────────────────────────
BELGRADE_ZONES = [
    ("Stari Grad",    44.8200, 20.4620),
    ("Savski Venac",  44.8050, 20.4530),
    ("Vračar",        44.7960, 20.4780),
    ("Zvezdara",      44.7920, 20.5050),
    ("Palilula",      44.8330, 20.5010),
    ("Novi Beograd",  44.8120, 20.3920),
    ("Zemun",         44.8430, 20.4050),
    ("Rakovica",      44.7660, 20.4340),
    ("Čukarica",      44.7760, 20.3940),
    ("Voždovac",      44.7790, 20.4900),
]

VEHICLE_TYPES = ["Van", "Truck", "Mini Van", "Cargo Van"]
VEHICLE_BRANDS = [
    ("Mercedes-Benz", "Sprinter"),
    ("Volkswagen",    "Crafter"),
    ("Ford",          "Transit"),
    ("Fiat",          "Ducato"),
    ("Iveco",         "Daily"),
    ("Renault",       "Master"),
]
LICENSE_CLASSES = ["B", "C", "C+E", "B+E"]

ROUTE_STATUSES = ["Planned", "Completed", "In Progress", "Cancelled"]
MATRIX_SOURCES = ["osrm", "here", "haversine"]
ALGORITHMS     = ["ALNS", "Nearest Neighbor", "Model 2"]

COMPANY_SUFFIXES = ["d.o.o.", "a.d.", "Trade", "Express", "Commerce", "Solutions"]
COMPANY_WORDS   = [
    "Sigma", "Delta", "Prima", "Global", "Rapid", "Balkan",
    "Euro", "Novo", "Top", "Smart", "Fast", "City",
]


def _rnd_name():
    return random.choice(FIRST_NAMES), random.choice(LAST_NAMES)


def _rnd_phone():
    return f"+381 {random.randint(60,69)} {random.randint(100,999)}-{random.randint(1000,9999)}"


def _rnd_email(first, last):
    domain = random.choice(["gmail.com", "yahoo.com", "grps.rs", "ptt.rs"])
    return f"{first.lower().replace(' ','.')}.{last.lower()[:6]}@{domain}"


def _rnd_license_plate():
    city = random.choice(["BG", "NS", "NI", "KG", "KR", "SM", "SB", "ZA"])
    letters = "".join(random.choices(string.ascii_uppercase, k=2))
    digits  = "".join(random.choices(string.digits, k=3))
    return f"{city}-{digits}-{letters}"


def _rnd_location():
    zone, lat0, lng0 = random.choice(BELGRADE_ZONES)
    lat = lat0 + random.uniform(-0.03, 0.03)
    lng = lng0 + random.uniform(-0.03, 0.03)
    street = random.choice(BELGRADE_STREETS)
    num    = random.randint(1, 120)
    return f"{street} {num}", zone, round(lat, 6), round(lng, 6)


def _rnd_company():
    return (f"{random.choice(COMPANY_WORDS)} "
            f"{random.choice(COMPANY_WORDS)} "
            f"{random.choice(COMPANY_SUFFIXES)}")


def _rnd_time_window():
    starts = ["07:00", "08:00", "09:00", "10:00", "11:00"]
    ends   = ["15:00", "16:00", "17:00", "18:00", "19:00"]
    return random.choice(starts), random.choice(ends)


def _rnd_date(start_year=2023, end_year=2025):
    start = datetime(start_year, 1, 1)
    end   = datetime(end_year, 12, 31)
    return (start + timedelta(days=random.randint(0, (end - start).days))).date()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 – POPULATE TABLES
# ─────────────────────────────────────────────────────────────────────────────

N_DRIVERS   = 20
N_VEHICLES  = 15
N_CUSTOMERS = 80
N_ROUTES    = 40      # Routes (each will get 3-8 stops from Customers)


def populate_drivers(cursor):
    rows = []
    used_licenses = set()
    for _ in range(N_DRIVERS):
        first, last = _rnd_name()
        # Unique 8-char license number
        while True:
            lic = "LIC" + "".join(random.choices(string.digits, k=6))
            if lic not in used_licenses:
                used_licenses.add(lic)
                break
        rows.append((
            first,
            last,
            lic,
            random.choice(LICENSE_CLASSES),
            _rnd_phone(),
            _rnd_email(first, last),
            str(_rnd_date(2018, 2024)),
            1 if random.random() > 0.1 else 0,        # 90 % active
            round(random.uniform(800, 1200), 0),       # wage RSD/h
        ))
    sql = """
        INSERT INTO dbo.Drivers
            (FirstName, LastName, LicenseNumber, LicenseClass,
             PhoneNumber, Email, HireDate, IsActive, WageRSD_PerHour)
        VALUES (?,?,?,?,?,?,?,?,?)
    """
    cursor.executemany(sql, rows)
    print(f"  ✓ Inserted {len(rows)} Drivers.")
    return len(rows)


def populate_vehicles(cursor):
    rows = []
    used_plates = set()
    for _ in range(N_VEHICLES):
        while True:
            plate = _rnd_license_plate()
            if plate not in used_plates:
                used_plates.add(plate)
                break
        vtype = random.choice(VEHICLE_TYPES)
        brand, model = random.choice(VEHICLE_BRANDS)
        vol_cap  = round(random.uniform(5, 20), 1)
        wt_cap   = round(random.uniform(500, 3500), 0)
        fuel_con = round(random.uniform(8, 18), 1)
        year     = random.randint(2015, 2024)
        last_svc = str(_rnd_date(2023, 2025))
        rows.append((
            plate, vtype, brand, model, year,
            vol_cap, wt_cap, fuel_con, "Diesel",
            1 if random.random() > 0.15 else 0,
            last_svc,
        ))
    sql = """
        INSERT INTO dbo.Vehicles
            (LicensePlate, VehicleType, Brand, Model, Year,
             VolumeCapacityM3, WeightCapacityKG, FuelConsumptionL100,
             FuelType, IsAvailable, LastServiceDate)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """
    cursor.executemany(sql, rows)
    print(f"  ✓ Inserted {len(rows)} Vehicles.")
    return len(rows)


def populate_customers(cursor):
    rows = []
    for _ in range(N_CUSTOMERS):
        company = _rnd_company()
        first, last = _rnd_name()
        address, city, lat, lng = _rnd_location()
        postal   = str(random.randint(11000, 11300))
        phone    = _rnd_phone()
        email    = _rnd_email(first, last)
        tw_s, tw_e = _rnd_time_window()
        unload  = random.randint(5, 30)
        pkg1    = random.randint(0, 10)
        pkg2    = random.randint(0, 5)
        pkg3    = random.randint(0, 3)
        rows.append((
            company, f"{first} {last}", address, city, postal,
            lat, lng, phone, email,
            tw_s, tw_e, unload,
            pkg1, pkg2, pkg3,
            1,
        ))
    sql = """
        INSERT INTO dbo.Customers
            (CustomerName, ContactPerson, Address, City, PostalCode,
             Latitude, Longitude, PhoneNumber, Email,
             TimeWindowStart, TimeWindowEnd, UnloadingTimeMin,
             Packages1, Packages2, Packages3, IsActive)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    cursor.executemany(sql, rows)
    print(f"  ✓ Inserted {len(rows)} Customers.")
    return len(rows)


def populate_routes_and_stops(cursor, n_drivers, n_vehicles, n_customers):
    route_rows = []
    stop_rows  = []

    used_driver_vehicle = set()  # avoid duplicate (driver, vehicle, date) combos

    depots = [
        ("Main Depot Belgrade",   44.8125, 20.4612),
        ("Novi Beograd Depot",    44.8120, 20.3920),
        ("Zemun Depot",           44.8430, 20.4050),
    ]

    for r in range(N_ROUTES):
        # Pick random date, driver, vehicle (avoid exact duplicates)
        for _ in range(50):                        # max 50 attempts
            route_date = str(_rnd_date(2024, 2025))
            driver_id  = random.randint(1, n_drivers)
            vehicle_id = random.randint(1, n_vehicles)
            key = (route_date, driver_id, vehicle_id)
            if key not in used_driver_vehicle:
                used_driver_vehicle.add(key)
                break

        depot_name, depot_lat, depot_lng = random.choice(depots)
        algorithm  = random.choice(ALGORITHMS)
        matrix_src = random.choice(MATRIX_SOURCES)
        status     = random.choice(ROUTE_STATUSES)

        # Random route metrics
        n_stops   = random.randint(3, 8)
        dist_km   = round(random.uniform(20, 120), 2)
        fuel_l    = round(dist_km * random.uniform(0.08, 0.18), 2)
        fuel_cost = round(fuel_l * random.uniform(185, 215), 0)
        hours     = round(random.uniform(3, 9), 2)
        wage_cost = round(hours * random.uniform(800, 1200), 0)
        vol_used  = round(random.uniform(2, 15), 2)
        wt_used   = round(random.uniform(200, 2500), 1)

        dep_h   = random.randint(6, 10)
        dep_m   = random.choice([0, 15, 30, 45])
        ret_h   = min(dep_h + int(hours) + 1, 22)
        ret_m   = random.choice([0, 15, 30, 45])
        dep_t   = f"{dep_h:02d}:{dep_m:02d}:00"
        ret_t   = f"{ret_h:02d}:{ret_m:02d}:00"

        route_rows.append((
            route_date, driver_id, vehicle_id,
            depot_name, depot_lat, depot_lng,
            algorithm, matrix_src,
            dist_km, fuel_l, fuel_cost, wage_cost, fuel_cost + wage_cost,
            hours, dep_t, ret_t, vol_used, wt_used, n_stops, status,
            f"Auto-generated route {r+1}",
        ))

        # Build stop list for this route (sequential customer IDs, no repeats in route)
        stop_customers = random.sample(range(1, n_customers + 1), min(n_stops, n_customers))
        cur_h, cur_m = dep_h, dep_m
        for seq, cust_id in enumerate(stop_customers, start=1):
            cur_m += random.randint(10, 35)
            if cur_m >= 60:
                cur_h += cur_m // 60
                cur_m  = cur_m % 60
            cur_h = min(cur_h, 22)
            arr_t = f"{cur_h:02d}:{cur_m:02d}:00"
            svc   = random.randint(5, 30)
            cur_m += svc
            if cur_m >= 60:
                cur_h += cur_m // 60
                cur_m  = cur_m % 60
            cur_h = min(cur_h, 22)
            dep_stop_t = f"{cur_h:02d}:{cur_m:02d}:00"

            pkg1 = random.randint(0, 5)
            pkg2 = random.randint(0, 3)
            pkg3 = random.randint(0, 2)
            vol  = round((pkg1 * 0.10 + pkg2 * 0.30 + pkg3 * 0.60), 3)
            wt   = round((pkg1 * 5 + pkg2 * 15 + pkg3 * 30), 1)
            tw_viol = random.randint(0, 5) if random.random() < 0.1 else 0

            # route_id will be filled after bulk insert; store as placeholder
            stop_rows.append((
                seq, arr_t, dep_stop_t,
                random.randint(0, 10), tw_viol, svc,
                pkg1, pkg2, pkg3, vol, wt,
                1 if status == "Completed" else 0,
                cust_id,    # CustomerID
                r,          # 0-based route index (replaced below)
            ))

    # Insert Routes
    route_sql = """
        INSERT INTO dbo.Routes
            (RouteDate, DriverID, VehicleID,
             DepotName, DepotLat, DepotLng,
             AlgorithmUsed, MatrixSource,
             TotalDistanceKM, TotalFuelLitres, FuelCostRSD, WageCostRSD, TotalCostRSD,
             WorkingHours, DepartureTime, ReturnTime,
             VolumeUsedM3, WeightUsedKG, NumStops, Status, Notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    cursor.executemany(route_sql, route_rows)
    print(f"  ✓ Inserted {len(route_rows)} Routes.")

    # Retrieve generated RouteIDs in insertion order
    cursor.execute("SELECT RouteID FROM dbo.Routes ORDER BY RouteID")
    route_ids = [row[0] for row in cursor.fetchall()]

    # Build a route_index → RouteID map
    # stop_rows stores the 0-based route index in position [-1]
    stop_sql = """
        INSERT INTO dbo.RouteStops
            (RouteID, CustomerID, StopSequence,
             ArrivalTime, DepartureTime,
             WaitMinutes, TWViolationMin, ServiceTimeMin,
             Packages1, Packages2, Packages3,
             VolumeM3, WeightKG, IsDelivered)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    final_stops = []
    for s in stop_rows:
        route_idx = s[-1]
        route_id  = route_ids[route_idx] if route_idx < len(route_ids) else route_ids[-1]
        cust_id   = s[-2]
        seq       = s[0]
        arr_t, dep_t, wait, viol, svc = s[1], s[2], s[3], s[4], s[5]
        p1, p2, p3, vol, wt, delivered = s[6], s[7], s[8], s[9], s[10], s[11]
        final_stops.append((route_id, cust_id, seq,
                            arr_t, dep_t, wait, viol, svc,
                            p1, p2, p3, vol, wt, delivered))

    cursor.executemany(stop_sql, final_stops)
    print(f"  ✓ Inserted {len(final_stops)} RouteStops.")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("GRPS Database Setup")
    print("=" * 60)

    # 1. Find a working SQL Server connection
    print("\n[1/4] Connecting to SQL Server …")
    server, driver, master_conn = _find_driver_and_connect()
    master_conn.close()

    # 2. Create database
    print(f"\n[2/4] Creating database [{DATABASE}] …")
    create_database(server, driver)

    # 3. Create tables
    print(f"\n[3/4] Creating tables …")
    conn = _get_connection(server, driver, DATABASE)
    create_tables(conn)

    # 4. Populate with random data
    print(f"\n[4/4] Populating tables with random data (seed={SEED}) …")
    cursor = conn.cursor()
    cursor.fast_executemany = True

    n_drivers   = populate_drivers(cursor)
    n_vehicles  = populate_vehicles(cursor)
    n_customers = populate_customers(cursor)
    populate_routes_and_stops(cursor, n_drivers, n_vehicles, n_customers)

    conn.commit()

    # Summary
    print("\n" + "=" * 60)
    print("GRPS database setup complete.")
    print(f"  Database : {DATABASE}")
    print(f"  Server   : {server}")
    print(f"  Tables   : Drivers ({n_drivers}), Vehicles ({n_vehicles}),")
    print(f"             Customers ({n_customers}), Routes ({N_ROUTES}),")
    print(f"             RouteStops (see above)")
    print("=" * 60)

    conn.close()


if __name__ == "__main__":
    main()