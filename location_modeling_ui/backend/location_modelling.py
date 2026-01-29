import os, json, time, argparse
from pathlib import Path
from typing import Dict, Tuple, List, Optional

import numpy as np
import pandas as pd
from sqlalchemy import create_engine

# distances
import osmnx as ox
import networkx as nx
from math import radians, sin, cos, asin, sqrt

# optimization
from pulp import (
    LpProblem, LpMinimize, LpMaximize, LpVariable, LpBinary,
    lpSum, value, LpStatus
)

# mapping
import geopandas as gpd
import matplotlib
matplotlib.use('Agg')  
import matplotlib.pyplot as plt
import contextily as cx
from shapely.geometry import LineString

# CONSTANTS (miles)
MI_TO_M = 1609.344
EARTH_R_MI = 3958.7613

# DB
PG_DBNAME = "cosea_db"
PG_USER = "cosea_user"
PG_PASSWORD = "CoSeaIndex"
PG_HOST = "pgsql.dataconn.net"
PG_PORT = "5432"

def mk_engine():
    conn_url = (
        f'postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}'
        f'@{PG_HOST}:{PG_PORT}/{PG_DBNAME}'
    )
    return create_engine(conn_url, pool_pre_ping=True)

# CLI
def parse_args():
    ap = argparse.ArgumentParser(description="Facility Location Models (P-Median, LSCP, MCLP) — miles, multi-metric")
    # distances/graph
    ap.add_argument("--metric", choices=["haversine","network"], default="haversine",
                    help="distance metric (haversine=fast; network=OSM road distances)")
    ap.add_argument("--radius_cap_miles", type=float, default=40.0,
                    help="max radius (miles) for graph_from_point in network mode")
    ap.add_argument("--knearest", type=int, default=15,
                    help="keep k nearest facilities per demand (speed). Use -1 to disable pruning.")

    # modeling
    ap.add_argument("--p", type=int, default=8, help="number of facilities to open (p-median & MCLP)")
    ap.add_argument("--teacher_seats", type=int, default=200, help="capacity per certified teacher")
    ap.add_argument("--coverage_miles", type=float, default=10.0,
                    help="coverage distance (miles) for LSCP/MCLP")

    # demand metrics
    ap.add_argument("--demand_metrics", type=str, default="sfr",
                    help="comma-separated demand metrics to run independently "
                         "(e.g., 'sfr,ri_female,ri_black').")

    # block group option
    ap.add_argument("--aggregate_block_groups", action="store_true",
                    help="aggregate demand/capacity by block group if a bg_geoid column exists in schools")

    # plotting
    ap.add_argument("--plot_assignments", action="store_true",
                    help="draw p-median spider lines (can be visually cluttered).")
    ap.add_argument("--sample_assignments", type=int, default=500,
                    help="max number of assignment lines to draw if --plot_assignments is on (random sample).")
    return ap.parse_args()

# EXPORTS
BASE_EXPORT_DIR = Path("outputs_location_models_miles")
BASE_EXPORT_DIR.mkdir(parents=True, exist_ok=True)

def metric_export_dir(metric_slug: str) -> Path:
    p = BASE_EXPORT_DIR / metric_slug.lower()
    p.mkdir(parents=True, exist_ok=True)
    return p

# SQL
def build_school_sql() -> str:
    sql = """
    SELECT
      s."UNIQUESCHOOLID"::text                      AS id,
      s.lat::float                                  AS latitude,
      s.lon::float                                  AS longitude,
      COALESCE(g."CS_Enrollment", 0)::float         AS cs_enrollment,
      COALESCE(g."Certified_Teachers", 0)::float    AS certified_teachers,
      COALESCE(g."RI_Asian", NULL)::float           AS ri_asian,
      COALESCE(g."RI_Black", NULL)::float           AS ri_black,
      COALESCE(g."RI_Hispanic", NULL)::float        AS ri_hispanic,
      COALESCE(g."RI_White", NULL)::float           AS ri_white,
      COALESCE(g."RI_Female", NULL)::float          AS ri_female
      -- If schools already has block group, expose it:
      -- , s."bg_geoid"::text AS bg_geoid
    FROM "2024"."tbl_approvedschools" s
    LEFT JOIN census.gadoe2024 g
      ON g."UNIQUESCHOOLID" = s."UNIQUESCHOOLID"
    WHERE s.lat IS NOT NULL AND s.lon IS NOT NULL;
    """
    return sql

def to_numeric(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

def fetch_data(engine) -> pd.DataFrame:
    sql = build_school_sql()
    df = pd.read_sql(sql, engine)
    df = to_numeric(df, [
        "latitude","longitude","cs_enrollment","certified_teachers",
        "ri_asian","ri_black","ri_hispanic","ri_white","ri_female"
    ])
    df = df.dropna(subset=["latitude","longitude"])
    df = df[df["latitude"].between(-90, 90) & df["longitude"].between(-180, 180)]
    df = df[~((df["latitude"].abs() < 1e-6) & (df["longitude"].abs() < 1e-6))]
    df["cs_enrollment"] = df["cs_enrollment"].fillna(0).clip(lower=0)
    df["certified_teachers"] = df["certified_teachers"].fillna(0).clip(lower=0)
    df["id"] = df["id"].astype(str)
    return df


def maybe_aggregate_block_groups(df: pd.DataFrame, teacher_seats: int,
                                 demand_col: str) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    if "bg_geoid" not in df.columns:
        print("[Aggregate] No 'bg_geoid' found on schools — skipping block-group aggregation.")
        return None, None

    dtmp = df.copy()

    agg = dtmp.groupby("bg_geoid").apply(lambda g: pd.Series({
        "latitude": np.average(g["latitude"], weights=g["cs_enrollment"].clip(lower=1)),
        "longitude": np.average(g["longitude"], weights=g["cs_enrollment"].clip(lower=1)),
        "demand_val": np.average(g[demand_col].fillna(0), weights=g["cs_enrollment"].clip(lower=1)),
        "cs_enrollment": g["cs_enrollment"].sum(),
        "certified_teachers": g["certified_teachers"].sum()
    })).reset_index()

    demand_bg = agg.rename(columns={"bg_geoid":"id", "demand_val":"demand"}).copy()
    facilities_bg = demand_bg[["id","latitude","longitude"]].copy()
    facilities_bg["capacity"] = np.maximum(50, agg["certified_teachers"].fillna(0) * float(teacher_seats)).astype(float)
    return demand_bg[["id","latitude","longitude","demand"]], facilities_bg[["id","latitude","longitude","capacity"]]

ox.settings.use_cache = True
ox.settings.log_console = False

def bbox_from_points(demand: pd.DataFrame, facilities: pd.DataFrame) -> Tuple[float,float,float,float]:
    pts = pd.concat([demand[["latitude","longitude"]], facilities[["latitude","longitude"]]], ignore_index=True).dropna()
    north, south = float(pts["latitude"].max()), float(pts["latitude"].min())
    east, west  = float(pts["longitude"].max()), float(pts["longitude"].min())
    if west > east: west, east = east, west
    if south > north: south, north = north, south
    eps = 1e-4
    if abs(north - south) < eps: north += eps; south -= eps
    if abs(east - west)   < eps: east  += eps; west  -= eps
    return (north, south, east, west)

def download_osm_graph_radius(bbox_nsew, radius_cap_miles=40.0):
    n, s, e, w = bbox_nsew
    cy = (n + s) / 2.0; cx = (e + w) / 2.0
    lat_span = max(1e-3, n - s)
    lon_span = max(1e-3, e - w)
    span_km_y = lat_span * 111.0
    span_km_x = lon_span * 111.0 * max(0.3, np.cos(np.deg2rad(cy)))
    span_miles = max(span_km_x, span_km_y) * 0.621371
    dist_miles = min(radius_cap_miles, span_miles * 0.75)
    dist_m = int(max(10 * MI_TO_M, dist_miles * MI_TO_M))  # >= 10 miles
    print(f"[OSMnx] graph_from_point @ ({cy:.5f},{cx:.5f}) radius≈{dist_miles:.1f} miles")
    return ox.graph_from_point(center_point=(cy, cx), dist=dist_m, network_type="drive")

def build_network_distances(demand: pd.DataFrame, facilities: pd.DataFrame, G: nx.MultiDiGraph):
    d_nodes = ox.nearest_nodes(G, demand["longitude"].values, demand["latitude"].values)
    f_nodes = ox.nearest_nodes(G, facilities["longitude"].values, facilities["latitude"].values)
    D: Dict[Tuple[int,int], float] = {}
    N: Dict[int, List[int]] = {i: [] for i in range(len(demand))}
    t0 = time.time()
    for i, dn in enumerate(d_nodes):
        lengths = nx.single_source_dijkstra_path_length(G, dn, weight="length")  # meters
        for j, fn in enumerate(f_nodes):
            if fn in lengths:
                miles = lengths[fn] / MI_TO_M
                D[(i,j)] = miles
                N[i].append(j)
    print(f"[Distances] NETWORK pairs kept: {len(D)}  built in {time.time()-t0:.1f}s")
    return D, N

def haversine_miles(lat1, lon1, lat2, lon2):
    dlat = radians(lat2 - lat1); dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return 2 * EARTH_R_MI * asin(sqrt(a))

def build_haversine_distances(demand: pd.DataFrame, facilities: pd.DataFrame):
    D: Dict[Tuple[int,int], float] = {}
    N: Dict[int, List[int]] = {i: [] for i in range(len(demand))}
    t0 = time.time()
    d = demand.reset_index(drop=True); f = facilities.reset_index(drop=True)
    for i in range(len(d)):
        lat1, lon1 = d.loc[i, "latitude"], d.loc[i, "longitude"]
        for j in range(len(f)):
            lat2, lon2 = f.loc[j, "latitude"], f.loc[j, "longitude"]
            D[(i,j)] = haversine_miles(lat1, lon1, lat2, lon2)
            N[i].append(j)
    print(f"[Distances] HAVERSINE pairs kept: {len(D)}  built in {time.time()-t0:.1f}s")
    return D, N

def prune_knn(D: Dict[Tuple[int,int], float], N: Dict[int, List[int]], k: int):
    if k is None or k < 1: return
    for i, js in list(N.items()):
        js_sorted = sorted(js, key=lambda j: D[(i,j)])[:k]
        N[i] = js_sorted
        to_keep = set((i,j) for j in js_sorted)
        for j in js:
            if (i,j) not in to_keep and (i,j) in D:
                del D[(i,j)]

# MODELS
def solve_pmedian_capacitated(demand_df, fac_df, D, N, p, export_dir: Path):
    """
    Constraints:
      (1) Assignment: sum_j x_ij == 1
      (2) Open exactly p facilities: sum_j y_j == p
      (3) Consistency: x_ij <= y_j
      (4) Capacity: sum_i demand_i * x_ij <= capacity_j * y_j
    Objective:
      Minimize sum_{i,j} demand_i * distance_ij(miles) * x_ij
    """
    print(f"\n=== Solving capacitated p-median (p={p}) ===")
    I = list(demand_df.index)
    J = list(fac_df.index)

    zero = [i for i in I if len(N.get(i, [])) == 0]
    if zero:
        print(f"[Error] {len(zero)} demand points have no reachable facilities. Increase radius or use --metric haversine.")
        return

    model = LpProblem("Capacitated_PMedian", LpMinimize)
    x = {(i,j): LpVariable(f"x_{i}_{j}", cat=LpBinary) for (i,j) in D.keys()}
    y = {j: LpVariable(f"y_{j}", cat=LpBinary) for j in J}

    model += lpSum(demand_df.loc[i, "demand"] * D[(i,j)] * x[(i,j)] for (i,j) in D.keys())

    for i in I:
        model += lpSum(x[(i,j)] for j in N[i]) == 1

    model += lpSum(y[j] for j in J) == p

    for (i,j) in D.keys():
        model += x[(i,j)] <= y[j]

    for j in J:
        model += lpSum(demand_df.loc[i, "demand"] * x[(i,j)]
                       for i in I if (i,j) in D) <= fac_df.loc[j, "capacity"] * y[j]

    model.solve()
    status = LpStatus[model.status]
    print("Status:", status)
    if status != "Optimal":
        return

    obj = value(model.objective)
    print(f"Total demand-weighted distance (miles): {obj:,.3f}")

    y_open = [j for j in J if y[j].value() > 0.5]
    fac_out = fac_df.loc[y_open, ["id","latitude","longitude","capacity"]].copy()
    fac_out.to_csv(export_dir / "pmedian_facilities.csv", index=False)

    rows = []
    for (i,j), var in x.items():
        if var.value() and var.value() > 0.5:
            rows.append({
                "demand_idx": i,
                "demand_id": demand_df.loc[i, "id"],
                "facility_idx": j,
                "facility_id": fac_df.loc[j, "id"]
            })
    pd.DataFrame(rows).to_csv(export_dir / "pmedian_assignments.csv", index=False)

    with open(export_dir / "pmedian_kpis.json", "w") as f:
        json.dump({"status": status, "objective_miles": obj, "p": p}, f, indent=2)

    print("\nOptimal facilities:")
    for _, r in fac_out.iterrows():
        print(f"- {r['id']} @ ({r['latitude']:.5f}, {r['longitude']:.5f})  cap={int(r['capacity'])}")

def solve_lscp(demand_df, fac_df, D, coverage_miles, export_dir: Path):
    """Minimize number of facilities such that every demand is covered within coverage_miles."""
    print(f"\n=== Solving LSCP (coverage ≤ {coverage_miles} miles) ===")
    I, J = demand_df.index, fac_df.index
    Ncov = {i: [j for j in J if (i,j) in D and D[(i,j)] <= coverage_miles] for i in I}

    zero = [i for i in I if len(Ncov[i]) == 0]
    if zero:
        print(f"[Error] {len(zero)} demand points cannot be covered within {coverage_miles} miles.")
        return

    model = LpProblem("LSCP", LpMinimize)
    y = {j: LpVariable(f"y_{j}", cat=LpBinary) for j in J}

    model += lpSum(y[j] for j in J)
    for i in I:
        model += lpSum(y[j] for j in Ncov[i]) >= 1

    model.solve()
    status = LpStatus[model.status]
    print("Status:", status)
    if status != "Optimal":
        return

    min_fac = int(value(model.objective))
    print("Minimum facilities to cover all demand:", min_fac)
    sel = [j for j in J if y[j].value() > 0.5]
    fac_df.loc[sel, ["id","latitude","longitude"]].to_csv(export_dir / "lscp_facilities.csv", index=False)
    with open(export_dir / "lscp_kpis.json","w") as f:
        json.dump({"status": status, "coverage_miles": coverage_miles, "min_facilities": min_fac}, f, indent=2)

def solve_mclp(demand_df, fac_df, D, p, coverage_miles, export_dir: Path):
    """Open exactly p facilities, maximize demand covered within coverage_miles."""
    print(f"\n=== Solving MCLP (p={p}, coverage ≤ {coverage_miles} miles) ===")
    I, J = demand_df.index, fac_df.index
    Ncov = {i: [j for j in J if (i,j) in D and D[(i,j)] <= coverage_miles] for i in I}

    model = LpProblem("MCLP", LpMaximize)
    y = {j: LpVariable(f"y_{j}", cat=LpBinary) for j in J}
    z = {i: LpVariable(f"z_{i}", cat=LpBinary) for i in I}

    model += lpSum(demand_df.loc[i, "demand"] * z[i] for i in I)
    model += lpSum(y[j] for j in J) == p

    for i in I:
        if Ncov[i]:
            model += z[i] <= lpSum(y[j] for j in Ncov[i])
        else:
            model += z[i] == 0

    model.solve()
    status = LpStatus[model.status]
    print("Status:", status)
    if status != "Optimal":
        return

    covered = value(model.objective)
    total = float(demand_df["demand"].sum())
    pct = 100.0 * covered / total if total > 0 else 0.0
    print(f"Total demand covered: {covered:,.0f} / {total:,.0f} ({pct:.1f}%)")

    sel = [j for j in J if y[j].value() > 0.5]
    fac_df.loc[sel, ["id","latitude","longitude"]].to_csv(export_dir / "mclp_facilities.csv", index=False)
    with open(export_dir / "mclp_kpis.json","w") as f:
        json.dump({"status": status, "coverage_miles": coverage_miles, "p": p,
                   "covered": float(covered), "total": total, "pct": pct}, f, indent=2)

# MAPPING HELPERS (EPSG:3857 for basemap)
def _to_gdf(df, xcol="longitude", ycol="latitude", crs="EPSG:4326"):
    return gpd.GeoDataFrame(df.copy(), geometry=gpd.points_from_xy(df[xcol], df[ycol]), crs=crs)

def _project_3857(gdf):
    return gdf.to_crs(epsg=3857)

def _save_fig(fig, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)

def plot_pmedian_static(demand_df, facilities_df, export_dir: Path,
                        plot_assignments=False, sample_assignments=500):
    fac_path = export_dir / "pmedian_facilities.csv"
    asg_path = export_dir / "pmedian_assignments.csv"
    if not (fac_path.exists() and asg_path.exists()):
        print("[Map] p-median results not found; skipping plot.")
        return

    sel_fac = pd.read_csv(fac_path, dtype={"id": str})
    asg = pd.read_csv(asg_path, dtype={"demand_id": str, "facility_id": str})

    ddf = demand_df.copy(); ddf["id"] = ddf["id"].astype(str)
    fdf = facilities_df.copy(); fdf["id"] = fdf["id"].astype(str)

    g_d = _to_gdf(ddf[["id","latitude","longitude","demand"]])
    g_f = _to_gdf(fdf[["id","latitude","longitude","capacity"]])
    g_sel = g_f.merge(sel_fac[["id"]], on="id", how="inner")

    join_d = g_d.rename(columns={"id":"demand_id"}).set_index("demand_id")
    join_f = g_f.rename(columns={"id":"facility_id"}).set_index("facility_id")

    if plot_assignments and len(asg) > sample_assignments:
        asg = asg.sample(n=sample_assignments, random_state=42)

    lines = []
    if plot_assignments:
        for _, r in asg.iterrows():
            di = r["demand_id"]; fj = r["facility_id"]
            if di in join_d.index and fj in join_f.index:
                p1 = join_d.loc[di, "geometry"]; p2 = join_f.loc[fj, "geometry"]
                lines.append({"demand_id": di, "facility_id": fj, "geometry": LineString([p1, p2])})
    g_lines = gpd.GeoDataFrame(lines, crs="EPSG:4326") if lines else gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    g_d_3857 = _project_3857(g_d)
    g_sel_3857 = _project_3857(g_sel)
    g_lines_3857 = _project_3857(g_lines) if not g_lines.empty else g_lines

    fig, ax = plt.subplots(figsize=(10, 10))
    if not g_lines_3857.empty:
        g_lines_3857.plot(ax=ax, linewidth=0.3, alpha=0.15, color="gray")
    ms = np.clip(g_d_3857["demand"] / max(g_d_3857["demand"].max(), 1) * 60, 8, 60)
    g_d_3857.plot(ax=ax, markersize=ms, alpha=0.5, color="#1f77b4", label="Demand")
    g_sel_3857.plot(ax=ax, markersize=60, marker="^", color="#d62728", edgecolor="black", label="Selected facilities")
    cx.add_basemap(ax, source=cx.providers.CartoDB.Positron)
    ax.set_axis_off(); ax.legend(loc="lower left")
    _save_fig(fig, export_dir / "map_pmedian.png")
    print(f"[Map] Saved -> {export_dir/'map_pmedian.png'}")

def plot_lscp_static(demand_df, facilities_df, coverage_miles, export_dir: Path):
    fac_path = export_dir / "lscp_facilities.csv"
    if not fac_path.exists():
        print("[Map] LSCP results not found; skipping plot.")
        return

    sel_fac = pd.read_csv(fac_path, dtype={"id": str})
    fdf = facilities_df.copy(); fdf["id"] = fdf["id"].astype(str)
    ddf = demand_df.copy()

    g_d = _to_gdf(ddf[["id","latitude","longitude","demand"]])
    g_f = _to_gdf(fdf[["id","latitude","longitude"]])
    g_sel = g_f.merge(sel_fac[["id"]], on="id", how="inner")

    g_d_3857 = _project_3857(g_d)
    g_sel_3857 = _project_3857(g_sel)
    buffers = g_sel_3857.copy()
    buffers["geometry"] = g_sel_3857.buffer(coverage_miles * MI_TO_M)  # miles→meters

    fig, ax = plt.subplots(figsize=(10, 10))
    buffers.plot(ax=ax, facecolor="#ffeda0", edgecolor="#fdae6b", alpha=0.25, label=f"{coverage_miles} mi coverage")
    g_d_3857.plot(ax=ax, markersize=10, alpha=0.6, color="#3182bd", label="Demand")
    g_sel_3857.plot(ax=ax, markersize=40, marker="^", color="#e6550d", edgecolor="black", label="Open facilities")
    cx.add_basemap(ax, source=cx.providers.CartoDB.Positron)
    ax.set_axis_off(); ax.legend(loc="lower left")
    _save_fig(fig, export_dir / "map_lscp.png")
    print(f"[Map] Saved -> {export_dir/'map_lscp.png'}")

def plot_mclp_static(demand_df, facilities_df, coverage_miles, export_dir: Path):
    fac_path = export_dir / "mclp_facilities.csv"
    if not fac_path.exists():
        print("[Map] MCLP results not found; skipping plot.")
        return

    sel_fac = pd.read_csv(fac_path, dtype={"id": str})
    ddf = demand_df.copy(); ddf["id"] = ddf["id"].astype(str)
    fdf = facilities_df.copy(); fdf["id"] = fdf["id"].astype(str)

    g_d = _to_gdf(ddf[["id","latitude","longitude","demand"]])
    g_f = _to_gdf(fdf[["id","latitude","longitude"]])
    g_sel = g_f.merge(sel_fac[["id"]], on="id", how="inner")

    sel = g_sel[["latitude","longitude"]].to_dict("records")
    def _min_miles(row):
        lat1, lon1 = row["latitude"], row["longitude"]
        if not sel: return 1e9
        return min(haversine_miles(lat1, lon1, s["latitude"], s["longitude"]) for s in sel)

    g_d["min_miles"] = g_d.apply(_min_miles, axis=1)
    g_d["covered"] = g_d["min_miles"] <= coverage_miles

    g_d_3857 = _project_3857(g_d)
    g_sel_3857 = _project_3857(g_sel)

    fig, ax = plt.subplots(figsize=(10, 10))
    g_d_3857[~g_d_3857["covered"]].plot(ax=ax, markersize=12, color="#9e9ac8", alpha=0.8, label="Uncovered")
    g_d_3857[g_d_3857["covered"]].plot(ax=ax, markersize=12, color="#31a354", alpha=0.8, label="Covered")
    g_sel_3857.plot(ax=ax, markersize=60, marker="^", color="#e34a33", edgecolor="black", label="Chosen facilities")
    cx.add_basemap(ax, source=cx.providers.CartoDB.Positron)
    ax.set_axis_off(); ax.legend(loc="lower left")
    _save_fig(fig, export_dir / "map_mclp.png")
    print(f"[Map] Saved -> {export_dir/'map_mclp.png'}")

# DEMAND
VALID_METRICS = {
    "sfr": "sfr",  
    "cs_enrollment": "cs_enrollment",
    "ri_asian": "ri_asian",
    "ri_black": "ri_black",
    "ri_hispanic": "ri_hispanic",
    "ri_white": "ri_white",
    "ri_female": "ri_female",
}

def compute_sfr_series(df: pd.DataFrame) -> pd.Series:
    teachers = df["certified_teachers"].fillna(0)
    students = df["cs_enrollment"].fillna(0)
    sfr = students / teachers.replace(0, np.nan)
    sfr = sfr.fillna(students)
    return sfr

def normalize_01(s: pd.Series) -> pd.Series:
    if s.isna().all():
        return s.fillna(0.0)
    m = s.min(skipna=True); M = s.max(skipna=True)
    if pd.isna(m) or pd.isna(M) or M <= m:
        return s.fillna(0.0)
    return (s - m) / (M - m)

def build_demand_facilities_one_metric(df: pd.DataFrame, teacher_seats: int,
                                       metric: str, aggregate_block_groups: bool
                                       ) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    """
    Returns (demand_df, facilities_df, metric_slug)
    demand_df columns: id, latitude, longitude, demand
    facilities_df columns: id, latitude, longitude, capacity
    """
    metric = metric.lower().strip()
    if metric not in VALID_METRICS:
        raise ValueError(f"Unknown demand metric '{metric}'. Valid: {list(VALID_METRICS.keys())}")

    tbl = df.copy()

    # compute metric column
    if metric == "sfr":
        tbl["sfr"] = compute_sfr_series(tbl)
        demand_raw = tbl["sfr"]
    else:
        col = VALID_METRICS[metric]
        demand_raw = tbl[col]

    # normalize demand to [0,1] so models are comparable across metrics
    demand_norm = normalize_01(demand_raw).fillna(0.0)

    # build demand table
    demand = tbl[["id","latitude","longitude"]].copy()
    demand["demand"] = demand_norm

    # build facilities: capacity by teachers
    facilities = tbl[["id","latitude","longitude","certified_teachers"]].copy()
    facilities["capacity"] = np.maximum(50, facilities["certified_teachers"].fillna(0) * float(teacher_seats)).astype(float)
    facilities = facilities[["id","latitude","longitude","capacity"]]

    if aggregate_block_groups:
        d_bg, f_bg = maybe_aggregate_block_groups(tbl.assign(**{f"metric_{metric}": demand_norm}),
                                                  teacher_seats, demand_col=f"metric_{metric}")
        if d_bg is not None and f_bg is not None:
            return d_bg, f_bg, metric

    return demand, facilities, metric

def run_location_models(
    demand_metric: str,
    p: int,
    coverage_miles: float,
    knearest: int,
    metric_type: str = "haversine",
    aggregate_block_groups: bool = False,
    plot_assignments: bool = False,
    scenario_slug: str | None = None,
):
    """
    Core function you can call from an API.
    Returns a dict with file paths / KPIs.
    """
    ENGINE = mk_engine()

    print("Loading schools…")
    df = fetch_data(ENGINE)
    if df.empty:
        raise RuntimeError("No valid schools after cleaning.")

    # Single metric
    metric = demand_metric.strip().lower()
    demand, facilities, metric_slug = build_demand_facilities_one_metric(
        df,
        teacher_seats=200, 
        metric=metric,
        aggregate_block_groups=aggregate_block_groups,
    )

    # export dir: include scenario, so each scenario has its own folder
    base_dir = BASE_EXPORT_DIR
    if scenario_slug:
      base_dir = base_dir / scenario_slug
    EXPORT_DIR = (base_dir / metric_slug)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    # Distances
    if metric_type == "network":
        bbox = bbox_from_points(demand, facilities)
        G = download_osm_graph_radius(bbox, radius_cap_miles=40.0)
        D, N = build_network_distances(demand, facilities, G)
    else:
        D, N = build_haversine_distances(demand, facilities)

    # K-nearest
    k = None if knearest == -1 else knearest
    if k:
        prune_knn(D, N, k)

    # Solve models
    if metric_type == "pmedian":
     solve_pmedian_capacitated(demand, facilities, D, N, p=p, export_dir=EXPORT_DIR)

    elif metric_type == "lscp":
     solve_lscp(demand, facilities, D, coverage_miles=coverage_miles, export_dir=EXPORT_DIR)

    elif metric_type == "mclp":
     solve_mclp(demand, facilities, D, p=p, coverage_miles=coverage_miles, export_dir=EXPORT_DIR)

    else:
     solve_pmedian_capacitated(demand, facilities, D, N, p=p, export_dir=EXPORT_DIR)
     solve_lscp(demand, facilities, D, coverage_miles=coverage_miles, export_dir=EXPORT_DIR)
     solve_mclp(demand, facilities, D, p=p, coverage_miles=coverage_miles, export_dir=EXPORT_DIR)

    plot_pmedian_static(
    demand,
    facilities,
    export_dir=EXPORT_DIR,
    plot_assignments=plot_assignments,
    sample_assignments=500
    )
    plot_lscp_static(
    demand,
    facilities,
    coverage_miles=coverage_miles,
    export_dir=EXPORT_DIR
    )
    plot_mclp_static(
    demand,
    facilities,
    coverage_miles=coverage_miles,
    export_dir=EXPORT_DIR
    )
    return {
        "status": "ok",
        "scenario": scenario_slug,
        "metric": metric_slug,
        "export_dir": str(EXPORT_DIR),
        "pmedian_facilities": str(EXPORT_DIR / "pmedian_facilities.csv"),
        "pmedian_assignments": str(EXPORT_DIR / "pmedian_assignments.csv"),
        "pmedian_map": str(EXPORT_DIR / "map_pmedian.png"),
        "pmedian_kpis": str(EXPORT_DIR / "pmedian_kpis.json"),
        "lscp_map": str(EXPORT_DIR / "map_lscp.png"),
        "lscp_kpis": str(EXPORT_DIR / "lscp_kpis.json"),
        "mclp_map": str(EXPORT_DIR / "map_mclp.png"),
        "mclp_kpis": str(EXPORT_DIR / "mclp_kpis.json"),
    }



if __name__ == "__main__":
    # keep CLI mode for debugging
    args = parse_args()
    run_location_models(
        demand_metric=args.demand_metrics,
        p=args.p,
        coverage_miles=args.coverage_miles,
        knearest=args.knearest,
        metric_type=args.metric,
        aggregate_block_groups=args.aggregate_block_groups,
        plot_assignments=args.plot_assignments,
        scenario_slug="cli_debug",
    )
pass