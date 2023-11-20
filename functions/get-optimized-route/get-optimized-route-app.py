import csv
import json
import os
import random
from functools import lru_cache
from itertools import accumulate

from tabulate import tabulate
import plotly.graph_objects as go
import boto3
from processing import get_optimized_route

location_client = boto3.client('location')
ddb_client = boto3.client('dynamodb')
neptune_client = boto3.client('neptune')

@lru_cache
def get_well_locations():
    'Load data from the sample well table into a dictionary of lists, where the key is the column name and the value is a list of the column values'
    with open('sample_wells.csv', 'r') as f:
        reader = csv.reader(f)
        input_well_table = [row for row in reader]
    return input_well_table

def get_production_impact(data_dict):
    'For example purposes, generate a random production change to address. Change this function to a query of your hydrocarbon volumes database to find which wells have unusually low production.'
    data_dict['production_vol_vs_plan'] = [0] + [int((random.random()-0.5)*100) for _ in range(len(data_dict['cordinate_pairs'])-1)]
    data_dict['production_vol_below_plan'] =  [-1*min(vol,0) for vol in data_dict['production_vol_vs_plan']]
    return data_dict

@lru_cache
def get_route_maxtrix(cordinate_pairs: tuple):
    'To adapt ths code sample to your company data, update this function to reference the '
    print('getting route')
    route_matrix_response = location_client.calculate_route_matrix(
        CalculatorName=os.environ['LOCATION_CALCULATOR_NAME'],
        DeparturePositions=cordinate_pairs,
        DestinationPositions=cordinate_pairs,
        TravelMode=os.environ['TRAVEL_MODE'],
        DistanceUnit=os.environ['DISTANCE_UNIT'])
    route_duration_matrix_min = [[int(x.get('DurationSeconds')/60) for x in row] for row in route_matrix_response['RouteMatrix']]
    return route_duration_matrix_min

def create_data_dictionary(input_well_table: list):
    data_dict = {input_well_table[0][i]: column for i, column in enumerate(tuple(zip(*input_well_table[1:])))}
    data_dict['cordinate_pairs'] = tuple(
        zip(
            map(float,data_dict['longitude']),
            map(float,data_dict['latitude'])
        )
    )
    return data_dict

def argsort(seq):
    return sorted(range(len(seq)), key=seq.__getitem__)

def query_ddb_and_write_record_on_404(primary_key: str, ddb_table: str, target_value_name: str, function_which_calculates_value: object, function_which_calculates_value_kw_args: dict):
    get_ddb_response = ddb_client.get_item(
        TableName = ddb_table,
        Key = primary_key
    )
    if 'Item' in get_ddb_response and target_value_name in get_ddb_response.get('Item'):
        print('Found route transition matrix in the dynamo db table.')
        return json.loads(get_ddb_response.get('Item').get(target_value_name).get('S'))
    else:
        print('Did not find route transition matrix in the dynamo db table.')
        calculated_target_value = function_which_calculates_value(**function_which_calculates_value_kw_args)
        ddb_client.put_item(
            TableName = ddb_table,
            Item = {
                **primary_key,
                target_value_name: {
                    'S': json.dumps(calculated_target_value)
                }
            },
        )
        return calculated_target_value
        
def lambda_handler(event, context):
    route_well_ddb_key = {
            'route_name': {
                'S': 'ExampleRouteName1'
            }
        }
    input_well_table = query_ddb_and_write_record_on_404(
        primary_key = route_well_ddb_key,
        ddb_table = os.environ['ROUTE_WELL_TABLE_NAME'],
        target_value_name = 'wells',
        function_which_calculates_value = get_well_locations,
        function_which_calculates_value_kw_args = {}
    )
    
    data_dict = create_data_dictionary(input_well_table)
    
    data_dict = get_production_impact(data_dict)
    
    # Create a naive route to address the production change by visiting each well in order of the production decrease.
    initial_routes = [argsort(data_dict['production_vol_below_plan'])[::-1]]
    initial_routes[0].remove(0) #Remove the home node from the initial solution
    
    # Calculate the route matrix. First attempt to find in the Amazon Dynamo DB table. If it's not there, calcualte it using Amazon Location Services
    route_matrix_ddb_key = {
            'well_name_hash': {
                'S': str(hash(data_dict['well_name']))
            }
        }
    route_duration_matrix_min = query_ddb_and_write_record_on_404(
        primary_key = route_matrix_ddb_key,
        ddb_table = os.environ['ROUTE_MATRIX_TABLE_NAME'],
        target_value_name = 'route_duration_matrix_min',
        function_which_calculates_value = get_route_maxtrix,
        function_which_calculates_value_kw_args = {'cordinate_pairs': data_dict['cordinate_pairs']}
    )
    
    # Capure the data for the optimization task
    data = {
        "time_matrix_min": route_duration_matrix_min,
        "production_vol_below_plan": data_dict["production_vol_below_plan"],
        "num_vehicles": 1,
        "depo": 0,
        "stop_time_at_node_min": 30,
        "max_travel_time_min": 12*60,
        "initial_routes": initial_routes
    }
    
    # Run the optimization task and process the results
    optimized_route_info = get_optimized_route(data)
    optimized_route_nodes = optimized_route_info['routes'][0]
    data_dict['visit_order'] = ['']*len(data_dict['production_vol_vs_plan'])
    for i, j in enumerate(optimized_route_nodes):
        data_dict['visit_order'][j] = str(i)
    
    # Find the point by point navigation points of the optimized route.
    optimized_route_coordinates = [data_dict['cordinate_pairs'][node] for node in optimized_route_nodes]
    response = location_client.calculate_route(
            CalculatorName=os.environ['LOCATION_CALCULATOR_NAME'],
            DepartNow=False,
            DeparturePosition=optimized_route_coordinates[0],
            DestinationPosition=optimized_route_coordinates[-1],
            DistanceUnit=os.environ['DISTANCE_UNIT'],
            IncludeLegGeometry=True,
            TravelMode=os.environ['TRAVEL_MODE'],  # |'Truck'|'Walking',
            WaypointPositions=optimized_route_coordinates[1:-1]
        )
    all_way_points = []
    for i, leg in enumerate(response['Legs']):
        all_way_points.append([list(optimized_route_coordinates[i])] + leg['Geometry']['LineString'] + [list(optimized_route_coordinates[i+1])])
    
    #Sort the initial well table and add calcualted data for plotting.
    sorted_well_table = [row[:-1] + [vol, visit_order] for row, vol, visit_order in zip(
        input_well_table,
        ['production_vs_plan_boed'] + data_dict['production_vol_vs_plan'], 
        ['optimized_well_visit_order'] + data_dict['visit_order']
    )]
    sorted_well_table[1:] = sorted(sorted_well_table[1:], key = lambda x: x[-2])
    sorted_well_table[0] = [f'<b>{col_name.replace("_", " ")}</b>' for col_name in sorted_well_table[0]] #Make bold the column names
    
    # Calculate a naive impacted production based on the naive route for comparison.
    cum_travel_time_naive = list(accumulate([data['time_matrix_min'][from_node][to_node]+data['stop_time_at_node_min'] for from_node, to_node in zip([0] + initial_routes[0][:-1],initial_routes[0])]))
    total_travel_time = [cum_time+data['time_matrix_min'][node][0] for node, cum_time in zip([0] + initial_routes[0][:-1], cum_travel_time_naive)]
    last_node_visited = next(i for i, travel_time in enumerate(total_travel_time) if travel_time > data['max_travel_time_min']) -1
    naive_impacted_production = -1*sum(data_dict['production_vol_vs_plan'][node] for node in initial_routes[0][:last_node_visited])
    incremental_impact = optimized_route_info['production_impacted']/naive_impacted_production-1
    print(f'Impacted {incremental_impact:.0%} more production drops using an optimized route!')
    
    # Create a plotly map box plot for display in the web page.
    fig = go.Figure()
    waypoint_flat_list = [pair for route in all_way_points for pair in route]
    arc_long_lat_list = list(zip(*waypoint_flat_list))
    fig.add_trace(
        go.Scattermapbox(
            mode = "lines",
            lon = arc_long_lat_list[0],
            lat = arc_long_lat_list[1],
            opacity = 1,
            showlegend = False,
            hoverinfo='none',
        ),
    )
    fig.add_trace(
        go.Scattermapbox(
            mode = "markers+text",
            lon = list(map(float,data_dict['longitude'])),
            lat = list(map(float,data_dict['latitude'])),
            marker = {
                'size':10, 
                'color': list(map(float,data_dict['production_vol_vs_plan'])), 
                'colorscale':['red','yellow','green'], 
                'colorbar': {'title': 'Daily BOE/Day Change'},
                'showscale': True},
            text = data_dict['visit_order'],
            textposition="bottom center",
            textfont=dict(
                size=18,
                color="Black"
            ),
            showlegend = False,
            hoverinfo='text',
            hovertext = [f'{well_name} production diff: {prod_vol}' for well_name, prod_vol in zip(data_dict['well_name'],data_dict['production_vol_vs_plan'])]
        )
    )
    fig.update_layout(
        height=500,
        mapbox_style="white-bg",
        mapbox=dict(
            center=go.layout.mapbox.Center(
                lat=sum(map(float,data_dict['latitude']))/len(data_dict['latitude']),
                lon=sum(map(float,data_dict['longitude']))/len(data_dict['longitude'])
            ),
            pitch=0,
            zoom=9
        ),
        mapbox_layers=[
            {
                "below": 'traces',
                "sourcetype": "raster",
                "sourceattribution": "United States Geological Survey",
                "source": [
                    "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}"
                ]
            }
          ]
    )
    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    
    # Create the html to dispay in the web page.
    html =  f"""
    <html>
        <head>
            <title>Optimized Routing</title>
            <style>
            table {{
                border-collapse: collapse;
                border-spacing: 5px;
                border: 1px solid #ddd;
                width: 100%;
            }}
            th, td {{
                text-align: left;
                padding-top: 2px;
                padding-bottom: 2px;
                padding-left: 0px;
                padding-right: 16px;
            }}
            tr:nth-child(even) {{
                background-color: #f2f2f2;
            }}
            </style>
        </head>
        <body>
            <h1>Field Production Operator Driving Route Optimization To Maximize Hydrocarbon Production</h1>
            <p> The operator impacted {incremental_impact:.0%} more production drops using an optimized route than visiting wells in order of production decrease! </p>
            <p> In {optimized_route_info['total_time_minuntes']/60.:.1f} hours the operator visited {len(optimized_route_nodes)-2} wells with a cumulative {optimized_route_info['production_impacted']} BOE/Day production decrease. </p>
            {fig.to_html(full_html=False, include_plotlyjs='cdn')}
            <p>
                Each point on the map above shows one of the wells that the production operator is responsible for. 
                The color of the point corresponds to recent producton rate changes. 
                This operator lives in Farmington NM (far west point) and ends their 12 hour shift back at their home.
            </p>
            <p> Refresh this page to randomize each well's production numbers and recieve a new optimized route recommendation.</p>
            <p> </p>
            {tabulate(sorted_well_table, tablefmt='unsafehtml')}
        </body>
    </html>
    """
    
    # Return the html for display in the website
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "text/html",
        },
        "body": html,
    }