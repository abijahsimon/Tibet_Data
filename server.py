import io
import csv
from collections import namedtuple
from datetime import datetime

from flask import Flask, Response, render_template, request, abort

from natsort import natsort_keygen

import matplotlib
matplotlib.use('Agg') # use the Anti-Grain Geometry backend, which renders to a raster instead of a screen. This is necessary to use matplotlib in a server environment without a display.

import mplstereonet as mpl
from matplotlib.figure import Figure
from matplotlib.colors import to_rgb, LinearSegmentedColormap

from numpy import base_repr
import numpy as np

# POSIX timestamp in base 36, to cache-bust whenever server restarts
SERVER_EPOCH = base_repr(int(datetime.now().timestamp()), 36).lower()

# creates a color scale from totally transparent to the give end color
def color_scale(end_color):
    return LinearSegmentedColormap.from_list('colors', [(1,1,1,0), (*to_rgb(end_color), 0.5)])




class Loc(namedtuple('Locality', 'name measurements')):
    def json(self):
        d = self._asdict()
        d['measurements'] = [m.json() for m in self.measurements]
        return d

PLANE_TYPES = 'Foliation; Fault; Bedding; Overturned bedding; Cleavage'.split('; ')

class Plane(namedtuple('Plane', 'loc lat lng type strike dip')):
    def json(self):
        return self._asdict()

LINE_TYPES = 'Fold Axis; Slickenside; Lineation'.split('; ')

class Line(namedtuple('Line', 'loc lat lng type plunge trend')):
    def json(self):
        return self._asdict()


def int_from_string(str):
    try:
        return int(str)
    except ValueError:
        return None

all_locs = {}

with open('data/combined_plane_measurements_2019_2018_2016.csv') as file:
    plane_measurements = [Plane(
        loc=m['Locality'].strip(),
        lat=m['Latitude'].strip(),
        lng=m['Longitude'].strip(),
        type=m['Plane Type'].strip(),
        strike=int_from_string(m['strike'].strip()),
        dip=int_from_string(m['dip'].strip()),
    ) for m in csv.DictReader(file)]
    # DictReader takes the first row of the csv to name each column and format it 
    # as a dictionary 

    print('Plane measurements where strike or dip couldn\'t be parsed:',
        len([m for m in plane_measurements if m.strike == None or m.dip == None]))

    plane_measurements = [m for m in plane_measurements
        if m.strike != None and m.dip != None]

    # bad_plane_type_measurements = [plane for plane in plane_measurements
    #         if plane.type not in PLANE_TYPES]
    # bad_plane_types = {}
    # for plane in bad_plane_type_measurements:
    #     if plane.type not in bad_plane_types:
    #         bad_plane_types[plane.type] = 1
    #     else:
    #         bad_plane_types[plane.type] += 1
    # if bad_plane_types:
    #     print('Unrecognized Plane Types, by number of measurements:', bad_plane_types)

    # original order is geographic order, haven't decided whether to override
    # natsort_key = natsort_keygen()
    # plane_measurements.sort(key=lambda p: natsort_key(p.loc), reverse=True)

    for plane in plane_measurements:
        if plane.type in PLANE_TYPES:
            if plane.loc not in all_locs:
                all_locs[plane.loc] = Loc(name=plane.loc, measurements=[plane])
            else:
                all_locs[plane.loc].measurements.append(plane)

with open('data/2019_2018_2016_Field_measurements-line.csv') as file:
    line_measurements = [Line(
        loc=m['Locality'].strip(),
        lat=m['Latitude'].strip(),
        lng=m['Longitude'].strip(),
        type=m['Line Type'].strip(),
        plunge=int(m['Plunge'].strip()),
        trend=int(m['Trend'].strip()),
    ) for m in csv.DictReader(file)]

    bad_line_type_measurements = [line for line in line_measurements
            if line.type not in LINE_TYPES]
    bad_line_types = {}
    for line in bad_line_type_measurements:
        if line.type not in bad_line_types:
            bad_line_types[line.type] = 1
        else:
            bad_line_types[line.type] += 1
    if bad_line_types:
        print('Unrecognized Line Types, by number of measurements:', bad_line_types)

    for line in line_measurements:
        if line.loc not in all_locs:
            all_locs[line.loc] = Loc(line.loc, [line])
        else:
            all_locs[line.loc].measurements.append(line)



def summary_from_loc(loc):
    num_planes = 0
    plane_types = {}
    num_lines = 0
    line_types = {}
    for m in loc.measurements:
        if type(m) == Plane:
            num_planes += 1
            t = m.type if m.type != 'Overturned bedding' else 'Bedding-OT'
            if t not in plane_types:
                plane_types[t] = [m]
            else:
                plane_types[t].append(m)
        elif type(m) == Line:
            num_lines += 1
            if m.type not in line_types:
                line_types[m.type] = [m]
            else:
                line_types[m.type].append(m)
        else:
            raise Exception('Unrecognized measurement type: ' + repr(type(m)))

    if num_lines == 0:
        if len(plane_types) <= 2:
            return ', '.join(f"{len(plane_types[t])} {t}s" for t in plane_types)
        else:
            return '%s Planes' % len(loc.measurements)
    elif num_planes == 0:
        if len(line_types) <= 2:
            return ', '.join(f"{len(line_types[t])} {t}" for t in line_types)
        else:
            return '%s Lines' % len(loc.measurements)
    else:
        return '%s Planes, %s Lines' % (num_planes, num_lines)

def label_from_measurement(m):
    if type(m) == Plane:
        return '%s: %s (%03d/%02d)' % (m.loc, m.type, m.strike, m.dip)
    elif type(m) == Line:
        return '%s: %s (%02d\u2192%03d)' % (m.loc, m.type, m.plunge, m.trend)
    else:
        raise Exception('Unrecognized measurement type: ' + repr(type(m)))

def color_from_type(type):
  if type == 'Foliation':
    return 'blue'
  elif type == 'Fold Axis'  or type == 'Lineation':
    return 'green'
  elif type == 'Fault' or type == 'Slickenside':
    return 'red'
  elif type == 'Bedding' or type == 'Overturned bedding':
    return 'black'
  elif type == 'Cleavage':
    return 'grey'
  else:
    raise Exception ('Unexpected measurement type', type)


app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html",
        server_epoch=SERVER_EPOCH,
        loc_options=[
            (all_locs[l].name, "%s (%s)" % (all_locs[l].name, summary_from_loc(all_locs[l])))
            for l in all_locs],
        measurement_options={
            loc_name: [{
                    'id': '%s:%s' % (loc_name, i),
                    'label': label_from_measurement(m),
                    'type': m.type,
                } for i, m in enumerate(loc.measurements)]
            for loc_name, loc in all_locs.items()
        })


@app.route("/stereonet.svg")
def stereonet():
    measurements = []
    print('measurements URL param:', request.args.get('measurements'))
    loc_names = set() #set is like a list but there's no order AND IT DEDUPLICATES AUTOMATICALLY
    if request.args.get('measurements'):
        try:
            for loc_arg in request.args.get('measurements').split('/'):
                loc_name, meas_ids = loc_arg.split(':')
                loc_names.add(loc_name)
                if not meas_ids: continue
                measurements += [all_locs[loc_name].measurements[int(i)] for i in meas_ids.split(',')]
        except (ValueError, KeyError):
            abort(400, "Invalid 'measurements' parameter")
    print('measurements:', measurements)
    fig = Figure(figsize=(1.5,1.5), dpi=300)
    # fig.tight_layout()
    ax = fig.add_subplot(1,1,1, projection='equal_area_stereonet')
    ax.set_azimuth_ticks([]) #get rid of the bad ticks in the default stereonet labels

    num_planes = 0
    plane_types = {}
    num_lines = 0
    line_types = {}
    for m in measurements:
        if type(m) == Plane:
            num_planes += 1
            t = (m.type if m.type != 'Overturned bedding' else 'Bedding-OT')
            if t not in plane_types:
                plane_types[t] = [m]
            else:
                plane_types[t].append(m)
        elif type(m) == Line:
            num_lines += 1
            if m.type not in line_types:
                line_types[m.type] = [m]
            else:
                line_types[m.type].append(m)
        else:
            raise Exception('Unrecognized measurement type: ' + repr(type(m)))
            
    N_fontsize = 5
    
    x = -18
    y = -8
    # ax.annotate(f"N={num_planes} (Total Planar Features)", xy = [x,y], fontsize= N_fontsize, xycoords = 'axes points')
    # y -= 6
    # ax.annotate(f"N={num_lines} (Total Linear Features)", xy = [x,y], fontsize=N_fontsize, xycoords = 'axes points')
    # y -= 6
    summary = []
    if num_planes > 0:
        summary.append(f"{num_planes} Planes")
    if num_lines > 0:
        summary.append(f"{num_lines} Line{'s' if num_lines > 1 else ''}")
    if num_planes > 0 and num_lines > 0:
        ax.annotate(f"N = {len(measurements)} ({num_planes} Plane{'s' if num_planes > 1 else ''}, {num_lines} Line{'s' if num_lines > 1 else ''})", xy=[x, y], fontsize=N_fontsize, xycoords = 'axes points', fontweight="bold")
    else:
        planes = f"Plane{'s' if num_planes > 1 else ''}"
        lines = f"Line{'s' if num_lines > 1 else ''}"
        ax.annotate(f"N = {len(measurements)} {planes if num_planes > 0 else lines}", xy=[x, y], fontsize=N_fontsize, xycoords = 'axes points', fontweight="bold")

    y -= 8
    

    for plane_type, plane_measurements in plane_types.items():  #items = a way to get both the keys and the values at the same time. It's a method
        ax.annotate(f"{len(plane_measurements)} {plane_type} Plane{'s' if len(plane_measurements) > 1 else ''}", xy=[x, y], fontsize=N_fontsize, xycoords = 'axes points')
        y -= 7

    for line_type, line_measurements in line_types.items():  #items = a way to get both the keys and the values at the same time. It's a method
        print('annotating for line type:', line_type, len(line_measurements))
        ax.annotate(f"{len(line_measurements)} {line_type} Line{'s' if len(line_measurements) > 1 else ''}", xy=[x, y], fontsize=N_fontsize, xycoords = 'axes points')
        y -= 7
        
    ax.annotate(f"N", xy = [38,88], xycoords = 'axes points')
    ax.annotate(f"\u257b", xy = [40.5,84], fontsize = 4, xycoords = 'axes points') #North tick
    ax.annotate(f"\u257b", xy = [40.5,-1.5], fontsize = 4, xycoords = 'axes points') #South tick


# set white background; dunno why .set_facecolor() doesn't seem to ¸work
    ax.density_contourf([], [], colors=['white', 'white'])

    for m in measurements:
        linewidth = 0.25
        if type(m) == Plane:
            # print(request.args)
            # print(request.args.get('planes'))
            if request.args.get('planes'):
                ax.plane(m.strike, m.dip, color=color_from_type(m.type),
                        linewidth=linewidth)
                        # linewidth=0.25, label=m.type+" Plane") # alternative label


            ax.pole(m.strike, m.dip, '+', color=color_from_type(m.type), 
                markersize=3, markeredgewidth=0.45)
                # label=m.type+ " Pole", markersize=3, markeredgewidth=0.45) # alternative label
        elif type(m) == Line:
            ax.line(m.plunge, m.trend, 'o', color=color_from_type(m.type), markersize=2, fillstyle='full')
        else:
            raise Exception('Unrecognized measurement type: ' + repr(type(m)))

    planes_by_type = {}
    for m in measurements:
        if type(m) == Plane:
            if m.type not in planes_by_type:
                planes_by_type[m.type] = [m]
            else:
                planes_by_type[m.type].append(m)

    for plane_type, planes in planes_by_type.items():
        strikes = [m.strike for m in planes]
        dips = [m.dip for m in planes]


        
    if request.args.get('density_contours'):
            ax.density_contourf(strikes, dips, cmap=color_scale(color_from_type(plane_type)))

    if request.args.get('mean_plane'):
        for plane_type, planes in planes_by_type.items():
                strikes = [m.strike for m in planes]
                dips = [m.dip for m in planes]
                # Find the mean plane
                fit_strike, fit_dip = mpl.fit_pole(strikes, dips)
                template = u'Mean {}: {:03.0f}\u00b0/{:02.0f}\u00b0 (n={})'.format(plane_type, fit_strike, fit_dip, len(strikes))


                # ax.annotate(f"Mean Plane = {fit_strike, fit_dip}", xy = [38,88], xycoords = 'axes points')
                    #Add legend, useful for website but not for map


                ax.plane(fit_strike, fit_dip,'-',color=color_from_type(plane_type), lw=1, label=template) 
        # Plot MEAN great circle
                # ax.density_contourf(strikes, dips, cmap=color_scale(color_from_type(plane_type)))
        def legend_without_duplicate_labels(ax):
            fontsize = 4

            handles, labels = ax.get_legend_handles_labels()
            unique = [(h, l) for i, (h, l) in enumerate(zip(handles, labels)) if l not in labels[:i]]
            angle = np.deg2rad(67.5)
            ax.legend(*zip(*unique), 
                    loc = "lower left", shadow=False, 
                    bbox_to_anchor=(.5 + np.cos(angle)/2, .5 + np.sin(angle)/2),
                    fontsize = fontsize,
                    framealpha=0)
        legend_without_duplicate_labels(ax)

    ax.grid(color='grey', linestyle='-', linewidth=0.2)
    



    # ax.legend()
    # ax.set_title(f"the location is {loc_name}", fontsize=3)

    with io.BytesIO() as pseudo_file:
        fig.savefig(pseudo_file, transparent=True, format="svg", pad_inches=0, bbox_inches="tight")
        content = pseudo_file.getvalue()

    res = Response(content, mimetype="image/svg+xml")
    res.headers['Content-Disposition'] = f"inline; filename=Stereonet_{'__'.join(sorted(loc_names))}.svg"
    if request.args.get('server_epoch'):
        res.cache_control.max_age = 31536000 # 1 year, in seconds
        res.cache_control.immutable = True
        res.cache_control.public = True
    return res
