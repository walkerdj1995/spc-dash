# First, get data from email attachments

# Import packages
import pandas as pd

# For now, get last 30 days DLO and Schedule for current and previous month
Sch = pd.read_csv('https://github.com/walkerdj1995/spc-dash/blob/master/WFMarGasSchedule.csv')
Dlo = pd.read_csv('https://github.com/walkerdj1995/spc-dash/blob/master/Last_30_Days.csv')

# Merge on the scheduled jobs
df = pd.merge(Sch, Dlo, left_on='ID', right_on='External Reference', how='left')

# Change duration to time in minutes
df['Duration'] = df['Duration'].fillna('0')
df['Process_Time'] = df['Process_Time']*60

def hm_to_m(s):
    t = 0
    for u in s.split(':'):
        t = 60 * t + int(u)
    return t


df.loc[:, 'Mins'] = df.loc[:, 'Duration'].apply(lambda x: hm_to_m(x))

# Combine Duplicate times
dups = df[df.duplicated(['ID'],keep=False)]
total_time = dups.groupby('ID').agg({'Mins':'sum','Name':'count'}).reset_index()

df2 = df.copy()
for i in range(0,len(total_time)):
    ref = total_time.loc[i,'ID']
    t = total_time.loc[i,'Mins']
    n = total_time.loc[i, 'Name']
    df2.loc[df2.ID == ref,'Mins'] = t
    df2.loc[df2.ID == ref, 'n_visits'] = n

df2 = df2.drop_duplicates(subset ="External Reference").reset_index(drop=True)

# Add Control Limits --- Start with default of +- 75%
df['UL'] = df.loc[:,'Process_Time'] + df.loc[:,'Process_Time']*0.75
df['LL'] = df.loc[:,'Process_Time'] - df.loc[:,'Process_Time']*0.75
df2['UL'] = df2.loc[:,'Process_Time'] + df2.loc[:,'Process_Time']*0.75
df2['LL'] = df2.loc[:,'Process_Time'] - df2.loc[:,'Process_Time']*0.75

# Remove null names and make external ref a str
df2['Name'] = df2['Name'].fillna('Not Complete')
df2['External Reference'] = df2['External Reference'].astype(str)
# Get Exceptions
ex = df2[(df2['Mins']>df2['UL']) |(df2['Mins']<df2['LL'])]
ex = ex[['ID','Site','Description_x','Name','Day_Sched','Finish Date','Mins','LL','UL']]

# Split df into jobs done and not done/not recorded
not_done = df[df['Job Code'].isnull()]
df = df[~df['Job Code'].isnull()]

# Indicate whether job was done on scheduled data
df.loc[:,'Day_Sched'] = pd.to_datetime(df.loc[:,'Day_Sched'],format = '%d/%m/%Y')
df.loc[:,'Finish Date'] = pd.to_datetime(df.loc[:,'Finish Date'],format = '%d/%m/%Y')

def compliance(row):
    if row['Day_Sched'] == row['Finish Date']:
        return(1)
    else:
        return(0)

df.loc[:,'Compliance'] = [0]*len(df)
df['Compliance'] = df.apply(lambda row: compliance(row),axis=1)

# Data for Compliance Charts
comp = df.groupby('Day_Sched').agg({'Compliance':'sum','ID':'count'}).reset_index()
comp['Prop'] = comp.loc[:,'Compliance']/comp.loc[:,'ID']

# Process Time Traces
refs = df['External Reference'].unique()
All_Traces = {}
for ref in refs:
    dff = df[df['External Reference']==ref].reset_index(drop=True)
    dff.loc[:, 'Finish Date'] = dff.loc[:, 'Finish Date'].apply(lambda x: x.to_pydatetime())
    tr_data = {ref:dff}
    All_Traces.update(tr_data)

# Create dashboard for control charts

import dash
import dash_bootstrap_components as dbc
import dash_core_components as dcc
import dash_html_components as html
import dash_table
from dash.dependencies import Input, Output
import plotly.express as px
import plotly.graph_objects as go
from dash.exceptions import PreventUpdate

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
server = app.server

app.layout = html.Div(children=[
    html.H1(children='Statistical Process Control'),

    dcc.Graph(
        id='compliance',
        figure={
            'data': [
                {'x': comp['Day_Sched'], 'y': comp['Prop'], 'type': 'line', 'name': 'Compliance'},
            ],
            'layout': {
                'title': 'Compliance Chart'
            }
        }
    ),

    dcc.Dropdown('job_type',options = [{'label':i,'value':i} for i in df['Description_x'].unique()]),
    dcc.RadioItems(id='views',options=[{'label':'Individual Visits','value':'ind'},{'label':'Total per Inspection','value':'tot'}]),
    dcc.Graph(
        id='process_times',
    ),
    dash_table.DataTable(
            id='exceptions',
            columns=[
                {"name": i, "id": i} for i in ex.columns
            ],
            data=ex.to_dict('records'))
])

@app.callback(
    Output('process_times','figure'),
    [Input('job_type','value'),
     Input('views','value')])

def update_pt_graph(typ,view):
    if view is None:
        raise PreventUpdate
    data = df[df['Description_x']==typ].reset_index(drop=True)
    data2 = df2[df2['Description_x'] == typ].reset_index(drop=True)
    if len(data)==0:
        raise PreventUpdate
    if len(data2)==0:
        raise PreventUpdate
    r = data['External Reference'].unique()
    tr_2_plot = [All_Traces[t] for t in r]
    upper_lim = data['UL'][0]
    lower_lim = data['LL'][0]
    if view == 'ind':
        fig = go.Figure()
        for p in tr_2_plot:
            fig.add_trace(go.Scatter(x = p['Finish Date'], y = p['Mins'],mode='lines+markers',line=dict(dash='dot'),name=str(p.loc[0,'External Reference'])))
    else:
        fig = px.scatter(data2.sort_values('External Reference'),x='External Reference',y='Mins',marginal_y="violin")
        fig.add_trace(go.Scatter(x=[min(data2['External Reference']), max(data2['External Reference'])], y=[upper_lim, upper_lim], mode="lines", name="Upper Control Limit"))
        fig.add_trace(go.Scatter(x=[min(data2['External Reference']), max(data2['External Reference'])], y=[lower_lim, lower_lim], mode="lines", name="Lower Control Limit"))
    return(fig)

if __name__ == '__main__':
    app.run_server(debug=True)
