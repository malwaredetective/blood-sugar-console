import os
import logging
import sys
import time
import pyfiglet
from apscheduler.schedulers.background import BackgroundScheduler
from colorama import Fore, Style, init
from datetime import datetime
from dotenv import load_dotenv
from libreview_api import LibreViewAPI, LibreViewAPIError
from zoneinfo import ZoneInfo

init(autoreset=True) 

load_dotenv() # This loads variables from .env into os.environ

EMAIL = os.getenv("LIBRE_FREESYTLE_EMAIL", "")
PASSWORD = os.getenv("LIBRE_FREESYTLE_PASSWORD", "")

api = LibreViewAPI(EMAIL, PASSWORD)

logging.getLogger('apscheduler').setLevel(logging.WARNING)

graph_data = None

def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')

def get_terminal_width():
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80

def get_blood_sugar_color(value):
    if value > 200:
        return Fore.RED
    elif value > 180:
        return Fore.YELLOW  
    elif 80 <= value <= 180:
        return Fore.GREEN
    elif 70 <= value < 80:
        return Fore.YELLOW  
    else:
        return Fore.RED

def print_centered(figlet_str, width, color=None):
    for line in figlet_str.splitlines():
        output = line.center(width)
        if color:
            output = color + output + Style.RESET_ALL
        print(output)

def print_blood_sugar():
    clear_console()
    terminal_width = get_terminal_width()
    title = pyfiglet.figlet_format("Blood Sugar Console", font="small")
    print_centered(title, terminal_width)

    if graph_data and "graphData" in graph_data and len(graph_data["graphData"]) > 0:
        latest_reading = graph_data["graphData"][-1]
        dt_utc = datetime.strptime(latest_reading["FactoryTimestamp"], '%m/%d/%Y %I:%M:%S %p')
        dt_utc = dt_utc.replace(tzinfo=ZoneInfo("UTC"))
        dt_cst = dt_utc.astimezone(ZoneInfo("America/Chicago"))
        cst_time_str = dt_cst.strftime('%Y-%m-%d %I:%M:%S %p %Z')
        value = latest_reading['Value']
        color = get_blood_sugar_color(value)
        value_fig = pyfiglet.figlet_format(str(value), font="big") 
        print()
        print_centered(value_fig, terminal_width, color)
        print(f"This reading was captured at: {cst_time_str}.".center(terminal_width))
    else:
        print("\n".join([
            "",
            "Waiting for the applicaiton to fetch updated results ...".center(terminal_width),
            ""
        ]))

def update_graph_data():
    global graph_data
    try:
        graph_data = api.get_graph_data()
    except LibreViewAPIError as e:
        print("Error fetching graph data:", e)
    print_blood_sugar()

scheduler = BackgroundScheduler()
scheduler.add_job(update_graph_data, 'interval', minutes=5)
scheduler.start()

update_graph_data()

try:
    while True:
        time.sleep(1)
except (KeyboardInterrupt, SystemExit):
    scheduler.shutdown()