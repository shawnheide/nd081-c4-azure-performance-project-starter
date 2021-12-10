from flask import Flask, request, render_template
import os
import redis
import socket
import logging

# App Insights
from opencensus.ext.azure.log_exporter import AzureLogHandler
from opencensus.ext.azure.log_exporter import AzureEventHandler
from opencensus.ext.azure import metrics_exporter
from opencensus.stats import stats as stats_module
from opencensus.trace import config_integration
from opencensus.ext.azure.trace_exporter import AzureExporter
from opencensus.trace.samplers import ProbabilitySampler
from opencensus.trace.tracer import Tracer
from opencensus.ext.flask.flask_middleware import FlaskMiddleware

app = Flask(__name__)

# Load configurations from environment or config file
app.config.from_pyfile('config_file.py')

connection_string = app.config.get("APP_INSIGHTS_CONNECTION_STRING")

config_integration.trace_integrations(['logging'])
config_integration.trace_integrations(['requests'])

# Setup logger
logger = logging.getLogger(__name__)

# Logging python logs
log_handler = AzureLogHandler(connection_string=connection_string)
log_handler.setFormatter(logging.Formatter('%(traceId)s %(spanId)s %(message)s'))
logger.addHandler(log_handler)

# Logging custom Events
event_handler = AzureEventHandler(connection_string=connection_string)
logger.addHandler(event_handler)

# Set the logging level
logger.setLevel(logging.INFO)

# Metrics
stats = stats_module.stats
view_manager = stats.view_manager

exporter = metrics_exporter.new_metrics_exporter(enable_standard_metrics=True, connection_string=connection_string)
view_manager.register_exporter(exporter)

# Tracing
azure_exporter = AzureExporter(connection_string=connection_string)
sampler = ProbabilitySampler(1.0)
tracer = Tracer(exporter=azure_exporter, sampler=sampler)

# Requests
middleware = FlaskMiddleware(app, exporter=azure_exporter, sampler=sampler)

def get_config_value(name):
    if (name in os.environ and os.environ[name]):
        value = os.environ[name]
    else:
        value = app.config[name]

    return value

button1 = get_config_value('VOTE1VALUE')
button2 = get_config_value('VOTE2VALUE')
title = get_config_value('TITLE')

# Redis Connection
r = redis.Redis()

# Change title to host name to demo NLB
if app.config['SHOWHOST'] == "true":
    title = socket.gethostname()

# Init Redis
if not r.get(button1): r.set(button1,0)
if not r.get(button2): r.set(button2,0)

def get_vote_count(button):
    return int(r.get(button).decode('utf-8'))

def trace_vote(vote_name):
    with tracer.span(name=vote_name) as span:
        print(vote_name)

def log_votes(vote_name, n_votes):
    properties = {'custom_dimensions': {vote_name: n_votes}}
    logger.info(vote_name, extra=properties)

@app.route('/', methods=['GET', 'POST'])
def index():

    if request.method == 'GET':

        # Get current values
        n_votes_cat = get_vote_count(button1)
        trace_vote('Cats Vote')
        
        n_votes_dog = get_vote_count(button2)
        trace_vote('Dogs Vote')

    elif request.method == 'POST':

        if request.form['vote'] == 'reset':

            # Empty table and return results
            r.set(button1,0)
            r.set(button2,0)

        else:

            # Insert vote result into DB
            vote = request.form['vote']
            r.incr(vote,1)

        # Get current values
        n_votes_cat = get_vote_count(button1)
        log_votes('Cats Vote', n_votes_cat)

        n_votes_dog = get_vote_count(button2)
        log_votes('Dogs Vote', n_votes_dog)

    # Return results
    return render_template("index.html", value1=n_votes_cat, value2=n_votes_dog, button1=button1, button2=button2, title=title)

if __name__ == "__main__":
    # comment line below when deploying to VMSS
    # app.run() # local

    # uncomment the line below before deployment to VMSS
    app.run(host='0.0.0.0', threaded=True, debug=True) # remote
