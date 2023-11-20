"""
Here we solve the operator routing problem by framing it as a traveling salesman problem where:
- There is no cost for transition between notes
- There is a cost for skipping a node equal to the ammout of production which won't be addressed
- There is a time constraint for the maximum amount of time in the field

This works because it minimizes the amount of production not addressed, which is the same as maximizing the addressed produciton.
"""
import sys
import json
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

def get_routes(solution, routing, manager):
    """Get vehicle routes from a solution and store them in an array."""
    # Get vehicle routes and store them in a two dimensional array whose
    # i,j entry is the jth location visited by vehicle i along its route.
    routes = []
    for route_nbr in range(routing.vehicles()):
        index = routing.Start(route_nbr)
        route = [manager.IndexToNode(index)]
        while not routing.IsEnd(index):
            index = solution.Value(routing.NextVar(index))
            route.append(manager.IndexToNode(index))
        routes.append(route)
    return routes

def interpret_solution(data, manager, routing, solution):
    """Prints solution on console."""
    print(f"Objective: {solution.ObjectiveValue()}")
    time_dimension = routing.GetDimensionOrDie("Time")
    # production_dimension = routing.GetDimensionOrDie("Production")
    total_time = total_production = last_node = 0
    for vehicle_id in range(data["num_vehicles"]):
        index = routing.Start(vehicle_id)
        plan_output = f"Route for vehicle {vehicle_id}:\n"
        while not routing.IsEnd(index):
            time_var = time_dimension.CumulVar(index)
            node_index = manager.IndexToNode(index)
            total_production += data['production_vol_below_plan'][node_index]
            plan_output += (
                f"{node_index}"
                f" Cum_Production={total_production}"
                f" Cumulative_Time={solution.Min(time_var)}"
                f" Travel_Time={data['time_matrix_min'][last_node][node_index]}"
                "\n"
            )
            last_node = node_index
            index = solution.Value(routing.NextVar(index))
        time_var = time_dimension.CumulVar(index)
        # production_var = production_dimension.CumulVar(index)
        node_index = manager.IndexToNode(index)
        plan_output += (
            f"{node_index}"
            f" Production={data['production_vol_below_plan'][node_index]}"
            f" Cumulative_Time={solution.Min(time_var)}"
            f" Travel_Time={data['time_matrix_min'][last_node][node_index]}\n"
        )
        plan_output += f"Time of the route: {solution.Min(time_var)}min\n"
        plan_output += f"Production decrease impacted: {total_production}\n"
        print(plan_output)
        total_time += solution.Min(time_var)
    print(f"Total time of all routes: {total_time}min")
    return {'production_impacted': total_production, 'total_time_minuntes': total_time}

def get_optimized_route(data: dict) -> dict:
    # Create the routing index manager.
    manager = pywrapcp.RoutingIndexManager(
        len(data['time_matrix_min']),
        data['num_vehicles'],
        data['depo'])
    
    # Create Routing Model.
    routing = pywrapcp.RoutingModel(manager)
    
    # Add a time constraint
    # Create and register a transit callback.
    def time_callback(from_index, to_index):
        """Returns the distance between the two nodes."""
        # Convert from routing variable Index to distance matrix NodeIndex.
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return data["time_matrix_min"][from_node][to_node] + data['stop_time_at_node_min']

    transit_callback_index = routing.RegisterTransitCallback(time_callback)
    dimension_name = "Time"
    routing.AddDimension(
        transit_callback_index,
        0,  # no slack
        data['max_travel_time_min'],  # vehicle maximum travel time
        True,  # start cumul to zero
        dimension_name,
    )
    time_dimension = routing.GetDimensionOrDie(dimension_name)
    
    # Define cost of each arc.
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
    
    # Allow to drop nodes. The simulator pays a penelty for each node dropped of the production what won't be impacted.
    for node in range(1, len(data["time_matrix_min"])):
        routing.AddDisjunction([manager.NodeToIndex(node)], 100*data['production_vol_below_plan'][node])
    
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.FromSeconds(30)
    
    # When an initial solution is given for search, the model will be closed with the default
    # search parameters unless it is explicitly closed with the custom search parameters.
    initial_solution = routing.ReadAssignmentFromRoutes(data["initial_routes"], True)
    routing.CloseModelWithParameters(search_parameters)
    solution = routing.SolveFromAssignmentWithParameters(
        initial_solution, search_parameters
    )
    
    print('Solver Status:',routing.status())
    
    if solution:
        output = interpret_solution(data, manager, routing, solution)
        output['routes'] = get_routes(solution, routing, manager)
        print(json.dumps(output))
        return output
    else:
        print('No solution found !')
    
if __name__ == '__main__':
    data = json.loads(sys.argv[1])
    get_optimized_route(data)
