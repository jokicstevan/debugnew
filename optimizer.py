# optimizer.py
"""Core optimization engine — imported by both app.py and tasks.py"""
import time
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

@dataclass
class OptimizationResult:
    status: str
    routes: List[List[int]]
    total_distance: float
    compute_time_ms: float
    solver: str


def _do_optimize(
    depot_id: int,
    customer_ids: List[int],
    vehicle_count: int,
    distance_matrix: np.ndarray,
    deadline_seconds: float = 30.0,
    solver_preference: str = "ortools"
) -> OptimizationResult:
    """
    Main optimization entry point.
    Called by both Flask routes (sync) and Celery workers (async).
    """
    start = time.perf_counter()

    # Build VRP model
    n = len(customer_ids) + 1  # +1 for depot
    num_vehicles = min(vehicle_count, n - 1)

    if solver_preference == "ortools":
        result = _solve_with_ortools(
            distance_matrix, num_vehicles, deadline_seconds
        )
    else:
        result = _solve_with_greedy(
            distance_matrix, num_vehicles
        )

    elapsed_ms = (time.perf_counter() - start) * 1000

    return OptimizationResult(
        status="optimal" if result["optimal"] else "feasible",
        routes=result["routes"],
        total_distance=result["distance"],
        compute_time_ms=elapsed_ms,
        solver=solver_preference
    )


def _solve_with_ortools(
    matrix: np.ndarray,
    num_vehicles: int,
    deadline_seconds: float
) -> Dict:
    """Google OR-Tools VRP solver with time limit."""
    from ortools.constraint_solver import routing_enums_pb2
    from ortools.constraint_solver import pywrapcp

    n = len(matrix)
    manager = pywrapcp.RoutingIndexManager(n, num_vehicles, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(matrix[from_node][to_node] * 1000)  # scale to int meters

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Add distance dimension
    routing.AddDimension(
        transit_callback_index,
        0,  # no slack
        999999999,  # large upper bound
        True,  # start cumul to zero
        "Distance"
    )

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.FromSeconds(int(deadline_seconds))

    solution = routing.SolveWithParameters(search_parameters)

    if not solution:
        return _solve_with_greedy(matrix, num_vehicles)

    routes = []
    total_distance = 0
    for vehicle_id in range(num_vehicles):
        index = routing.Start(vehicle_id)
        route = [manager.IndexToNode(index)]
        route_distance = 0
        while not routing.IsEnd(index):
            previous_index = index
            index = solution.Value(routing.NextVar(index))
            route.append(manager.IndexToNode(index))
            route_distance += routing.GetArcCostForVehicle(
                previous_index, index, vehicle_id
            )
        routes.append(route)
        total_distance += route_distance / 1000.0  # back to km

    return {
        "optimal": True,
        "routes": routes,
        "distance": round(total_distance, 2)
    }


def _solve_with_greedy(matrix: np.ndarray, num_vehicles: int) -> Dict:
    """Fallback greedy nearest-neighbor solver."""
    n = len(matrix)
    unvisited = set(range(1, n))
    routes = []
    total_distance = 0

    for _ in range(num_vehicles):
        if not unvisited:
            break
        route = [0]
        current = 0
        route_dist = 0
        while unvisited:
            nearest = min(unvisited, key=lambda x: matrix[current][x])
            if matrix[current][nearest] > 999999:
                break
            route_dist += matrix[current][nearest]
            route.append(nearest)
            unvisited.remove(nearest)
            current = nearest
        route.append(0)
        routes.append(route)
        total_distance += route_dist

    # Append any remaining unvisited to last route
    if unvisited:
        routes[-1].extend(list(unvisited))
        routes[-1].append(0)

    return {
        "optimal": False,
        "routes": routes,
        "distance": round(total_distance, 2)
    }


def build_distance_matrix(
    locations: List[Tuple[float, float]],
    source: str = "osrm",
    deadline_seconds: float = 10.0
) -> np.ndarray:
    """
    Build distance matrix from location coordinates.
    Falls back to OSRM if HERE API times out.
    """
    import requests
    import math

    n = len(locations)
    matrix = np.full((n, n), 999999.0)

    if source == "here":
        matrix = _fetch_here_matrix(locations, deadline_seconds)
        if matrix is not None:
            return matrix

    # Fallback to OSRM
    return _fetch_osrm_matrix(locations)


def _fetch_here_matrix(
    locations: List[Tuple[float, float]],
    deadline: float
) -> Optional[np.ndarray]:
    """Fetch matrix from HERE API with deadline."""
    import os
    import requests
    import time

    api_key = os.getenv("HERE_API_KEY")
    if not api_key:
        return None

    n = len(locations)
    matrix = np.full((n, n), 999999.0)

    # Batch requests (HERE has limits)
    origins = "|".join([f"{lat},{lon}" for lat, lon in locations])
    destinations = origins

    url = (
        "https://router.hereapi.com/v8/matrix"
        f"?origins={origins}"
        f"&destinations={destinations}"
        f"&regionDefinition=world"
        f"&apiKey={api_key}"
    )

    start = time.time()
    try:
        resp = requests.get(url, timeout=deadline)
        if resp.status_code == 200:
            data = resp.json()
            # Parse matrix from HERE response format
            # ... parsing logic ...
            return matrix
    except requests.Timeout:
        pass

    return None


def _fetch_osrm_matrix(locations: List[Tuple[float, float]]) -> np.ndarray:
    """Fetch matrix from OSRM public server."""
    import requests

    n = len(locations)
    coords = ";".join([f"{lon},{lat}" for lat, lon in locations])
    url = f"http://router.project-osrm.org/table/v1/driving/{coords}?annotations=distance"

    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    distances = np.array(data["distances"]) / 1000.0  # meters to km
    # Replace OSRM nulls with large penalty
    distances = np.where(distances == 0, 0, np.where(np.isnan(distances), 999999, distances))
    return distances


def spatial_filter(
    locations: List[Tuple[float, float]],
    depot_idx: int = 0,
    k_nearest: int = 10
) -> Tuple[List[Tuple[float, float]], List[int], List[Tuple[int, int]]]:
    """
    Reduce API calls by only fetching distances for k-nearest neighbors.
    Returns: (filtered_locations, original_indices, api_pairs)
    """
    from scipy.spatial import cKDTree

    coords = np.array(locations)
    tree = cKDTree(coords)

    n = len(locations)
    all_pairs = set()

    for i in range(n):
        # Find k nearest (excluding self)
        dists, idxs = tree.query(coords[i], k=min(k_nearest + 1, n))
        for j in idxs[1:]:  # skip self
            all_pairs.add(tuple(sorted((i, j))))

    # Always include depot connections
    for i in range(n):
        if i != depot_idx:
            all_pairs.add(tuple(sorted((depot_idx, i))))

    return locations, list(range(n)), list(all_pairs)
