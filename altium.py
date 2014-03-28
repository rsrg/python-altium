#! /usr/bin/env python3

import struct
from io import SEEK_CUR

try:
    from OleFileIO_PL import OleFileIO
except ImportError:
    # Pillow version tends to do illegal seeks with Altium files
    from PIL.OleFileIO import OleFileIO

def read(file):
    """Returns a sequence of objects from an Altium *.SchDoc schematic file
    """
    
    ole = OleFileIO(file)
    stream = ole.openstream("FileHeader")
    
    objects = list()
    while True:
        length = stream.read(4)
        if not length:
            break
        (length,) = struct.unpack("<I", length)
        
        properties = stream.read(length - 1)
        obj = dict()
        for property in properties.split(b"|"):
            if not property:
                # Most (but not all) property lists are
                # prefixed with a pipe "|",
                # so ignore an empty property before the prefix
                continue
            
            (name, value) = property.split(b"=", 1)
            obj[name.decode("ascii")] = value
        
        objects.append(obj)
        
        # Skip over null terminator byte
        stream.seek(+1, SEEK_CUR)
    
    return objects

class Record:
    """Schematic object record types"""
    SCH_COMPONENT = b"1"
    PIN = b"2"
    LABEL = b"4"
    BEZIER = b"5"
    POLYLINE = b"6"
    POLYGON = b"7"
    ELLIPSE = b"8"
    ROUND_RECTANGLE = b"10"
    ELLIPTICAL_ARC = b"11"
    ARC = b"12"
    LINE = b"13"
    RECTANGLE = b"14"
    SHEET_SYMBOL = b"15"
    POWER_OBJECT = b"17"
    PORT = b"18"
    NO_ERC = b"22"
    NET_LABEL = b"25"
    WIRE = b"27"
    TEXT_FRAME = b"28"
    JUNCTION = b"29"
    IMAGE = b"30"
    SHEET = b"31"
    SHEET_NAME = b"32"
    SHEET_FILE_NAME = b"33"
    DESIGNATOR = b"34"
    PARAMETER = b"41"

class PinElectrical:
    """Signal types for a pin"""
    INPUT = b"0"
    IO = b"1"
    OUTPUT = b"2"
    OPEN_COLLECTOR = b"3"
    PASSIVE = b"4"
    HI_Z = b"5"
    OPEN_EMITTER = b"6"
    POWER = b"7"

class PowerObjectStyle:
    """Symbols for remote connections to common rails"""
    ARROW = b"1"
    BAR = b"2"
    GND = b"4"

class ParameterReadOnlyState:
    NAME = b"1"

class SheetStyle:
    """Preset sheet sizes"""
    A4 = b"0"
    A3 = b"1"
    A = b"5"

from vector import svg
from sys import stderr
from textwrap import TextWrapper
import os
import os.path
from datetime import date

def main(filename, renderer="svg"):
    """Convert an Altium *.SchDoc schematic file
    
    By default, the schematic is converted to an SVG file,
    written to the standard output. It may also be rendered using TK.
    """
    
    #~ renderer = {"svg", "tk"}[renderer]
    
    with open(filename, "rb") as file:
        objects = read(file)
        stat = os.stat(file.fileno())
    
    sheet = objects[1]
    assert sheet["RECORD"] == Record.SHEET
    (sheetstyle, size) = {SheetStyle.A4: ("A4", (1150, 760)), SheetStyle.A3: ("A3", (1550, 1150)), SheetStyle.A: ("A", (950, 760))}[sheet.get("SHEETSTYLE", SheetStyle.A4)]
    if "USECUSTOMSHEET" in sheet:
        size = tuple(int(sheet["CUSTOM" + "XY"[x]]) for x in range(2))
    
    # Units are 1/100" or 10 mils
    renderer = svg.Renderer(size, "in", 1/100,
        margin=0.3, line=1, down=-1, textsize=8.75, textbottom=True)
    
    for n in range(int(sheet["FONTIDCOUNT"])):
        n = format(1 + n)
        fontsize = int(sheet["SIZE" + n]) * 0.875
        family = sheet["FONTNAME" + n].decode("ascii")
        kw = dict()
        italic = sheet.get("ITALIC" + n)
        if italic:
            kw.update(italic=True)
        bold = sheet.get("BOLD" + n)
        if bold:
            kw.update(bold=True)
        renderer.addfont("font" + n, fontsize, family, **kw)
    renderer.start()
    
    def basearrow(renderer):
        renderer.polygon(((0, 0), (-2, -3), (5, 0), (-2, +3)))
    
    with renderer.element("defs", dict()):
        with renderer.element("marker",
        dict(overflow="visible", markerUnits="userSpaceOnUse", id="input")):
            with renderer.element("g", dict(transform="scale(-1)")):
                basearrow(renderer)
        
        with renderer.element("marker",
        dict(overflow="visible", markerUnits="userSpaceOnUse", id="output")):
            renderer.polygon(((0, +2.5), (7, 0), (0, -2.5)))
        
        with renderer.element("marker",
        dict(overflow="visible", markerUnits="userSpaceOnUse", id="io")):
            renderer.polygon(((-5, 0), (0, +2.5), (+5, 0), (0, -2.5)))
    
    symbols = list()
    @symbols.append
    def gnd(renderer):
        renderer.hline(b=10)
        renderer.vline(-7, +7, 10, width=1.5)
        renderer.vline(-4, +4, 13, width=1.5)
        renderer.vline(-1, +1, 16, width=1.5)
    @symbols.append
    def rail(renderer):
        renderer.hline(b=10)
        renderer.vline(-7, +7, 10, width=1.5)
    @symbols.append
    def arrow(renderer):
        renderer.hline(b=5)
        with renderer.offset((5, 0)) as offset:
            basearrow(offset)
    @symbols.append
    def dchevron(renderer):
        renderer.hline(b=5)
        renderer.polyline(((8, +4), (5, 0), (8, -4)))
        renderer.polyline(((11, +4), (8, 0), (11, -4)))
    @symbols.append
    def nc(renderer):
        renderer.line((+3, +3), (-3, -3), width=0.6)
        renderer.line((-3, +3), (+3, -3), width=0.6)
    renderer.addobjects(symbols)
    
    with renderer.offset((0, size[1])) as base:
        base.box(size, (0, -size[1]), width=0.6)
        base.box((x - 2 * 20 for x in size), (20, 20 - size[1]), width=0.6)
        for axis in range(2):
            for side in range(2):
                for n in range(4):
                    translate = [None] * 2
                    translate[axis] = size[axis] / 4 * (n + 0.5)
                    translate[axis ^ 1] = 10
                    if side:
                        translate[axis ^ 1] += size[axis ^ 1] - 20
                    translate[1] *= -1
                    with base.offset(translate) as ref:
                        label = chr(ord("1A"[axis]) + n)
                        ref.text(label, horiz=ref.CENTRE, vert=ref.CENTRE)
                        if n + 1 < 4:
                            x = size[axis] / 4 / 2
                            if axis:
                                ref.hline(-10, +10, -x, width=0.6)
                            else:
                                ref.vline(-10, +10, x, width=0.6)
        
        if "TITLEBLOCKON" in sheet:
            if not os.path.isabs(filename):
                cwd = os.getcwd()
                pwd = os.getenv("PWD")
                if os.path.samefile(pwd, cwd):
                    cwd = pwd
                filename = os.path.join(pwd, filename)
            with base.offset((size[0] - 20, 20 - size[1])) as block:
                points = ((-350, 0), (-350, 80), (-0, 80))
                block.polyline(points, width=0.6)
                block.hline(a=-350, y=50, width=0.6)
                block.vline(50, 20, -300, width=0.6)
                block.vline(50, 20, -100, width=0.6)
                block.hline(a=-350, y=20, width=0.6)
                block.hline(a=-350, y=10, width=0.6)
                block.vline(a=20, x=-150, width=0.6)
                
                block.text("Title", (-345, 70))
                block.text("Size", (-345, 40))
                block.text(sheetstyle, (-340, 30), vert=block.CENTRE)
                block.text("Number", (-295, 40))
                block.text("Revision", (-95, 40))
                block.text("Date", (-345, 10))
                d = format(date.fromtimestamp(stat.st_mtime), "%x")
                block.text(d, (-300, 10))
                block.text("File", (-345, 0))
                block.text(filename, (-300, 0))
                block.text("Sheet", (-145, 10))
                block.text("of", (-117, 10))
                block.text("Drawn By:", (-145, 0))
    
    for obj in objects:
        if (obj.keys() - {"INDEXINSHEET"} == {"RECORD", "OWNERPARTID", "LOCATION.X", "LOCATION.Y", "COLOR"} and
        obj["RECORD"] == b"29" and obj.get("INDEXINSHEET", b"-1") == b"-1" and obj["OWNERPARTID"] == b"-1"):
            location = (int(obj["LOCATION." + x]) for x in "XY")
            col = colour(obj["COLOR"])
            renderer.circle(2, location, colour=col)
        
        elif (obj.keys() - {"INDEXINSHEET", "IOTYPE", "ALIGNMENT"} == {"RECORD", "OWNERPARTID", "STYLE", "WIDTH", "LOCATION.X", "LOCATION.Y", "COLOR", "AREACOLOR", "TEXTCOLOR", "NAME", "UNIQUEID"} and
        obj["RECORD"] == Record.PORT and obj["OWNERPARTID"] == b"-1"):
            width = int(obj["WIDTH"])
            if "IOTYPE" in obj:
                points = "0,0 5,-5 {xx},-5 {x},0 {xx},+5 5,+5".format(x=width, xx=width - 5)
            else:
                points = "0,-5 {xx},-5 {x},0 {xx},+5 0,+5".format(x=width, xx=width - 5)
            shapeattrs = {"points": points}
            shapestyle = (("stroke-width", 0.6),)
            renderer._colour(shapeattrs, colour(obj["COLOR"]))
            shapeattrs["stroke"] = shapeattrs.pop("color")
            renderer._colour(shapeattrs, colour(obj["AREACOLOR"]))
            shapeattrs["fill"] = shapeattrs.pop("color")
            labelattrs = dict()
            renderer._colour(labelattrs, colour(obj["TEXTCOLOR"]))
            if (obj.get("ALIGNMENT") == b"2") ^ (obj["STYLE"] != b"7"):
                labelattrs["x"] = "10"
                labelpoint = (10, 0)
                anchor = "start"
                horiz = renderer.LEFT
            else:
                labelattrs["x"] = format(width - 10)
                labelpoint = (width - 10, 0)
                anchor = "end"
                horiz = renderer.RIGHT
            labelkw = dict()
            if obj["STYLE"] == b"7":
                shapeattrs.update(transform="rotate(90) translate({})".format(-width))
                labelattrs.update(transform="rotate(-90)")
                labelkw.update(angle=-90)
            labelstyle = [("dominant-baseline", "middle")]
            labelstyle.append(("text-anchor", anchor))
            offset = (int(obj["LOCATION." + x]) for x in "XY")
            with renderer.offset(offset) as offset:
                offset.emptyelement("polygon", shapeattrs, style=shapestyle)
                with offset.element("text", labelattrs, style=labelstyle):
                #    colour=colour(obj["TEXTCOLOR"]),
                #    point=labelpoint,
                #    vert=offset.CENTRE, horiz=horiz,
                #**labelkw)
                    offset.tree(*overline(obj["NAME"]))
        
        elif (obj.keys() - {"INDEXINSHEET"} >= {"RECORD", "OWNERPARTID", "LINEWIDTH", "COLOR", "LOCATIONCOUNT", "X1", "Y1", "X2", "Y2"} and
        obj["RECORD"] == Record.WIRE and obj["OWNERPARTID"] == b"-1" and obj["LINEWIDTH"] == b"1"):
            points = list()
            for location in range(int(obj["LOCATIONCOUNT"])):
                location = format(1 + location)
                points.append(tuple(int(obj[x + location]) for x in "XY"))
            renderer.polyline(points, colour=colour(obj["COLOR"]))
        elif (obj.keys() == {"RECORD", "OWNERINDEX"} and
        obj["RECORD"] in {b"46", b"48", b"44"} or
        obj.keys() - {"USECOMPONENTLIBRARY", "DESCRIPTION", "DATAFILECOUNT", "MODELDATAFILEENTITY0", "MODELDATAFILEKIND0", "DATALINKSLOCKED", "DATABASEDATALINKSLOCKED", "ISCURRENT", "INDEXINSHEET", "INTEGRATEDMODEL", "DATABASEMODEL"} == {"RECORD", "OWNERINDEX", "MODELNAME", "MODELTYPE"} and
        obj["RECORD"] == b"45" and obj.get("INDEXINSHEET", b"-1") == b"-1" and obj.get("USECOMPONENTLIBRARY", b"T") == b"T" and obj["MODELTYPE"] in {b"PCBLIB", b"SI", b"SIM", b"PCB3DLib"} and obj.get("DATAFILECOUNT", b"1") == b"1" and obj.get("ISCURRENT", b"T") == b"T" and obj.get("INTEGRATEDMODEL", b"T") == b"T" and obj.get("DATABASEMODEL", b"T") == b"T" and obj.get("DATALINKSLOCKED", b"T") == b"T" and obj.get("DATABASEDATALINKSLOCKED", b"T") == b"T" or
        obj.keys() >= {"RECORD", "AREACOLOR", "BORDERON", "CUSTOMX", "CUSTOMY", "DISPLAY_UNIT", "FONTIDCOUNT", "FONTNAME1", "HOTSPOTGRIDON", "HOTSPOTGRIDSIZE", "ISBOC", "SHEETNUMBERSPACESIZE", "SIZE1", "SNAPGRIDON", "SNAPGRIDSIZE", "SYSTEMFONT", "USEMBCS", "VISIBLEGRIDON", "VISIBLEGRIDSIZE"} and
        obj["RECORD"] == Record.SHEET and obj["AREACOLOR"] == b"16317695" and obj["BORDERON"] == b"T" and obj.get("CUSTOMMARGINWIDTH", b"20") == b"20" and obj.get("CUSTOMXZONES", b"6") == b"6" and obj.get("CUSTOMYZONES", b"4") == b"4" and obj["DISPLAY_UNIT"] == b"4" and obj["FONTNAME1"] == b"Times New Roman" and obj["HOTSPOTGRIDON"] == b"T" and obj["ISBOC"] == b"T" and obj["SHEETNUMBERSPACESIZE"] == b"4" and obj["SIZE1"] == b"10" and obj["SNAPGRIDON"] == b"T" and obj["SYSTEMFONT"] == b"1" and obj.get("TITLEBLOCKON", b"T") == b"T" and obj["USEMBCS"] == b"T" and obj["VISIBLEGRIDON"] == b"T" and obj["VISIBLEGRIDSIZE"] == b"10" or
        obj.keys() == {"HEADER", "WEIGHT"} and
        obj["HEADER"] == b"Protel for Windows - Schematic Capture Binary File Version 5.0" or
        obj.keys() - {"INDEXINSHEET"} == {"RECORD", "DESIMP0", "DESIMPCOUNT", "DESINTF", "OWNERINDEX"} and
        obj["RECORD"] == b"47" and obj["DESIMPCOUNT"] == b"1" or
        obj.keys() == {"RECORD", "ISNOTACCESIBLE", "OWNERPARTID", "FILENAME"} and
        obj["RECORD"] == b"39" and obj["ISNOTACCESIBLE"] == b"T" and obj["OWNERPARTID"] == b"-1"):
            pass
        
        elif (obj.keys() - {"ISMIRRORED", "ORIENTATION", "INDEXINSHEET", "COMPONENTDESCRIPTION", "SHEETPARTFILENAME", "DESIGNITEMID", "DISPLAYMODE", "NOTUSEDBTABLENAME", "LIBRARYPATH"} == {"RECORD", "OWNERPARTID", "UNIQUEID", "AREACOLOR", "COLOR", "CURRENTPARTID", "DISPLAYMODECOUNT", "LIBREFERENCE", "LOCATION.X", "LOCATION.Y", "PARTCOUNT", "PARTIDLOCKED", "SOURCELIBRARYNAME", "TARGETFILENAME"} and
        obj["RECORD"] == b"1" and obj["OWNERPARTID"] == b"-1" and obj["AREACOLOR"] == b"11599871" and obj["COLOR"] == b"128" and obj["PARTIDLOCKED"] == b"F" and obj["TARGETFILENAME"] == b"*"):
            pass
        
        elif (obj.keys() - {"TEXT", "OWNERINDEX", "ISHIDDEN", "READONLYSTATE", "INDEXINSHEET", "UNIQUEID", "LOCATION.X", "LOCATION.X_FRAC", "LOCATION.Y", "LOCATION.Y_FRAC", "ORIENTATION", "ISMIRRORED"} == {"RECORD", "OWNERPARTID", "COLOR", "FONTID", "NAME"} and
        obj["RECORD"] == Record.PARAMETER and obj["OWNERPARTID"] == b"-1"):
            if obj.get("ISHIDDEN") != b"T" and obj.keys() >= {"TEXT", "LOCATION.X", "LOCATION.Y"}:
                orient = obj.get("ORIENTATION")
                kw = {
                    None: dict(vert=renderer.BOTTOM, horiz=renderer.LEFT),
                    b"1": dict(vert=renderer.BOTTOM, horiz=renderer.LEFT),
                    b"2": dict(vert=renderer.TOP, horiz=renderer.RIGHT),
                }[orient]
                if orient == b"1":
                    kw.update(angle=+90)
                val = obj["TEXT"]
                if val.startswith(b"="):
                    for o in objects:
                        if o.get("RECORD") != Record.PARAMETER or o.get("OWNERINDEX") != obj["OWNERINDEX"]:
                            continue
                        if o["NAME"].lower() != val[1:].lower():
                            continue
                        val = o["TEXT"]
                        break
                    else:
                        raise LookupError("Parameter value for |OWNERINDEX={}|TEXT={}".format(obj["OWNERINDEX"].decode("ascii"), obj["TEXT"].decode("ascii")))
                    renderer.text(val.decode("ascii"),
                        colour=colour(obj["COLOR"]),
                        point=(int(obj["LOCATION." + x]) for x in "XY"),
                        font="font" + obj["FONTID"].decode("ascii"),
                    **kw)
                else:
                    text(renderer, obj, **kw)
        
        elif (obj.keys() - {"INDEXINSHEET", "ISMIRRORED", "LOCATION.X_FRAC", "LOCATION.Y_FRAC"} == {"RECORD", "OWNERINDEX", "OWNERPARTID", "LOCATION.X", "LOCATION.Y", "COLOR", "FONTID", "TEXT", "NAME", "READONLYSTATE"} and
        obj["RECORD"] == Record.DESIGNATOR and obj["OWNERPARTID"] == b"-1" and obj.get("INDEXINSHEET", b"-1") == b"-1" and obj["NAME"] == b"Designator" and obj["READONLYSTATE"] == b"1"):
            desig = obj["TEXT"].decode("ascii")
            owner = objects[1 + int(obj["OWNERINDEX"])]
            if int(owner["PARTCOUNT"]) > 2:
                desig += chr(ord("A") + int(owner["CURRENTPARTID"]) - 1)
            renderer.text(desig, (int(obj["LOCATION." + x]) for x in "XY"),
                colour=colour(obj["COLOR"]),
                font="font" + obj["FONTID"].decode(),
            )
        
        elif (obj.keys() >= {"RECORD", "OWNERPARTID", "OWNERINDEX", "LOCATIONCOUNT", "X1", "X2", "Y1", "Y2"} and
        obj["RECORD"] == Record.POLYLINE and obj.get("ISNOTACCESIBLE", b"T") == b"T" and obj.get("LINEWIDTH", b"1") == b"1"):
            if obj["OWNERPARTID"] == b"-1":
                current = True
            else:
                owner = objects[1 + int(obj["OWNERINDEX"])]
                current = (obj["OWNERPARTID"] == owner["CURRENTPARTID"] and
                    obj.get("OWNERPARTDISPLAYMODE", b"0") == owner.get("DISPLAYMODE", b"0"))
            if current:
                polyline(renderer, obj)
        
        elif (obj.keys() - {"OWNERPARTDISPLAYMODE", "INDEXINSHEET"} == {"RECORD", "OWNERINDEX", "OWNERPARTID", "COLOR", "ISNOTACCESIBLE", "LINEWIDTH", "LOCATION.X", "LOCATION.Y", "CORNER.X", "CORNER.Y"} and
        obj["RECORD"] == Record.LINE and obj["ISNOTACCESIBLE"] == b"T"):
            owner = objects[1 + int(obj["OWNERINDEX"])]
            if (obj["OWNERPARTID"] == owner["CURRENTPARTID"] and
            obj.get("OWNERPARTDISPLAYMODE", b"0") == owner.get("DISPLAYMODE", b"0")):
                renderer.line(
                    colour=colour(obj["COLOR"]),
                    width=int(obj["LINEWIDTH"]),
                    a=(int(obj["LOCATION." + x]) for x in "XY"),
                    b=(int(obj["CORNER." + x]) for x in "XY"),
                )
        
        elif (obj.keys() - {"NAME", "SWAPIDPIN", "OWNERPARTDISPLAYMODE", "ELECTRICAL", "DESCRIPTION", "SWAPIDPART", "SYMBOL_OUTEREDGE"} == {"RECORD", "OWNERINDEX", "OWNERPARTID", "DESIGNATOR", "FORMALTYPE", "LOCATION.X", "LOCATION.Y", "PINCONGLOMERATE", "PINLENGTH"} and
        obj["RECORD"] == Record.PIN and obj["FORMALTYPE"] == b"1"):
            if obj["OWNERPARTID"] == objects[1 + int(obj["OWNERINDEX"])]["CURRENTPARTID"]:
                pinlength = int(obj["PINLENGTH"])
                pinconglomerate = int(obj["PINCONGLOMERATE"])
                offset = (int(obj["LOCATION." + x]) for x in "XY")
                with renderer.offset(offset) as translated:
                    with translated.element("g", dict(transform="rotate({})".format((pinconglomerate & 3) * -90))):
                        lineattrs = dict()
                        linestart = 0
                        if "SYMBOL_OUTEREDGE" in obj:
                            translated.emptyelement("circle", {"r": "2.85", "cx": "3.15", "class": "outline"},
                                style=(("stroke-width", 0.6),))
                            linestart += 6
                        lineattrs.update(x2=format(pinlength))
                        electrical = obj.get("ELECTRICAL", PinElectrical.INPUT)
                        marker = {PinElectrical.INPUT: "input", PinElectrical.IO: "io", PinElectrical.OUTPUT: "output", PinElectrical.PASSIVE: None, PinElectrical.POWER: None}[electrical]
                        if marker:
                            lineattrs["marker-start"] = format("url(#{})".format(marker))
                            if electrical in {PinElectrical.INPUT, PinElectrical.IO}:
                                linestart += 5
                        if linestart:
                            lineattrs["x1"] = format(linestart)
                        translated.emptyelement("line", lineattrs)
                    
                    dirsvg = ((+1, 0), (0, -1), (-1, 0), (0, +1))[pinconglomerate & 0x03]  # SVG co-ordinates, not Altium coordinates
                    dir = ((+1, 0), (0, +1), (-1, 0), (0, -1))
                    dir = dir[pinconglomerate & 0x03]
                    
                    if pinconglomerate & 1:
                        rotatexform = ("rotate(-90)",)
                        kw = dict(angle=-90)
                    else:
                        rotatexform = ()
                        kw = dict()
                    
                    if pinconglomerate & 8 and "NAME" in obj:
                        style = [("dominant-baseline", "middle")]
                        anchor = ("end", "start")[pinconglomerate >> 1 & 1]
                        style.append(("text-anchor",  anchor))
                        tspans = overline(obj["NAME"])
                        transforms = ["translate({})".format(", ".join(format(-7 * dirsvg[x]) for x in range(2)))]
                        transforms.extend(rotatexform)
                        with translated.element("text", style=style):
                            translated.tree(*tspans)
                    
                    if pinconglomerate & 16:
                        designator = obj["DESIGNATOR"].decode("ascii")
                        aligns = (translated.LEFT, translated.RIGHT)
                        translated.text(designator,
                            horiz=aligns[pinconglomerate >> 1 & 1],
                            point=(+9 * x for x in dir),
                        **kw)
        
        elif (obj.keys() - {"INDEXINSHEET", "ORIENTATION", "STYLE", "ISCROSSSHEETCONNECTOR"} == {"RECORD", "OWNERPARTID", "COLOR", "LOCATION.X", "LOCATION.Y", "SHOWNETNAME", "TEXT"} and
        obj["RECORD"] == Record.POWER_OBJECT and obj["OWNERPARTID"] == b"-1"):
            orient = obj.get("ORIENTATION")
            if obj.get("ISCROSSSHEETCONNECTOR") == b"T":
                marker = "dchevron"
                offset = 14
            else:
                (marker, offset) = {PowerObjectStyle.ARROW: ("arrow", 12), PowerObjectStyle.BAR: ("rail", 12), PowerObjectStyle.GND: ("gnd", 20)}.get(obj["STYLE"], (None, 0))
            location = tuple(int(obj["LOCATION." + "XY"[x]]) for x in range(2))
            
            a = dict()
            renderer._colour(a, colour(obj["COLOR"]))
            a["transform"] = "translate({})".format(", ".join(format(location[x] * (+1, -1)[x]) for x in range(2)))
            with renderer.element("g", a):
                attrs = {"xlink:href": "#{}".format(marker)}
                if orient:
                    attrs.update(transform="rotate({})".format({b"2": 180, b"3": 90, b"1": 270}[orient]))
                renderer.emptyelement("use", attrs)
                
                if obj["SHOWNETNAME"] != b"F":
                    orients = {
                        b"2": (renderer.RIGHT, renderer.CENTRE, (-1, 0)),
                        b"3": (renderer.CENTRE, renderer.TOP, (0, -1)),
                        None: (renderer.LEFT, renderer.CENTRE, (+1, 0)),
                        b"1": (renderer.CENTRE, renderer.BOTTOM, (0, +1)),
                    }
                    (horiz, vert, pos) = orients[orient]
                    t = obj["TEXT"].decode("ascii")
                    pos = (p * offset for p in pos)
                    renderer.text(t, pos, horiz=horiz, vert=vert)
        
        elif (obj.keys() - {"INDEXINSHEET", "OWNERPARTDISPLAYMODE", "ISSOLID", "LINEWIDTH", "CORNERXRADIUS", "CORNERYRADIUS", "TRANSPARENT"} == {"RECORD", "OWNERINDEX", "OWNERPARTID", "AREACOLOR", "COLOR", "CORNER.X", "CORNER.Y", "ISNOTACCESIBLE", "LOCATION.X", "LOCATION.Y"} and
        obj["RECORD"] in {Record.RECTANGLE, Record.ROUND_RECTANGLE} and obj["ISNOTACCESIBLE"] == b"T" and obj.get("ISSOLID", b"T") == b"T"):
            owner = objects[1 + int(obj["OWNERINDEX"])]
            if (obj["OWNERPARTID"] == owner["CURRENTPARTID"] and
            obj.get("OWNERPARTDISPLAYMODE", b"0") == owner.get("DISPLAYMODE", b"0")):
                style = (("stroke-width", 0.6),)
                attrs = dict()
                renderer._colour(attrs, colour(obj["COLOR"]))
                attrs["stroke"] = attrs.pop("color")
                if "ISSOLID" in obj:
                    renderer._colour(attrs, colour(obj["AREACOLOR"]))
                    attrs["fill"] = attrs.pop("color")
                else:
                    attrs["fill"] = "none"
                topleft = tuple(int(obj[("LOCATION.X", "CORNER.Y")[x]]) * (+1, -1)[x] for x in range(2))
                attrs.update(("xy"[x], format(topleft[x])) for x in range(2))
                attrs.update((("width", "height")[x], format(int(obj[("CORNER.X", "LOCATION.Y")[x]]) * (+1, -1)[x] - topleft[x])) for x in range(2))
                for x in range(2):
                    radius = obj.get("CORNER{}RADIUS".format("XY"[x]))
                    if radius:
                        attrs["r" + "xy"[x]] = radius.decode("ascii")
                renderer.emptyelement("rect", attrs, style=style)
        
        elif (obj.keys() - {"INDEXINSHEET"} == {"RECORD", "OWNERPARTID", "COLOR", "FONTID", "LOCATION.X", "LOCATION.Y", "TEXT"} and
        obj["RECORD"] == Record.NET_LABEL and obj["OWNERPARTID"] == b"-1"):
            attrs = dict()
            renderer._colour(attrs, colour(obj["COLOR"]))
            attrs["transform"] = "translate({})".format(", ".join(format(int(obj["LOCATION." + "XY"[x]]) * (+1, -1)[x]) for x in range(2)))
            attrs["class"] = "font" + obj["FONTID"].decode("ascii")
            renderer.tree(("text", attrs, overline(obj["TEXT"])))
        
        elif (obj.keys() - {"INDEXINSHEET", "OWNERPARTDISPLAYMODE", "STARTANGLE", "SECONDARYRADIUS"} == {"RECORD", "OWNERPARTID", "OWNERINDEX", "COLOR", "ENDANGLE", "ISNOTACCESIBLE", "LINEWIDTH", "LOCATION.X", "LOCATION.Y", "RADIUS"} and
        obj["RECORD"] in {Record.ARC, Record.ELLIPTICAL_ARC} and obj["ISNOTACCESIBLE"] == b"T" and obj["LINEWIDTH"] == b"1" and obj.get("OWNERPARTDISPLAYMODE", b"1") == b"1"):
            owner = objects[1 + int(obj["OWNERINDEX"])]
            if (owner["CURRENTPARTID"] == obj["OWNERPARTID"] and
            owner.get("DISPLAYMODE", b"0") == obj.get("OWNERPARTDISPLAYMODE", b"0")):
                r = int(obj["RADIUS"])
                if obj["RECORD"] == Record.ELLIPTICAL_ARC:
                    r2 = obj.get("SECONDARYRADIUS")
                    if r2 is None:
                        r2 = 0
                    else:
                        r2 = int(r2)
                else:
                    r2 = r
                
                start = float(obj.get("STARTANGLE", 0))
                end = float(obj["ENDANGLE"])
                centre = (int(obj["LOCATION." + x]) for x in "XY")
                renderer.arc((r, r2), start, end, centre,
                    colour=colour(obj["COLOR"]),
                )
        
        elif (obj.keys() - {"INDEXINSHEET", "LINEWIDTH"} > {"RECORD", "AREACOLOR", "COLOR", "ISNOTACCESIBLE", "ISSOLID", "LOCATIONCOUNT", "OWNERINDEX", "OWNERPARTID"} and
        obj["RECORD"] == Record.POLYGON and obj["AREACOLOR"] == b"16711680" and obj["ISNOTACCESIBLE"] == b"T" and obj["ISSOLID"] == b"T" and obj.get("LINEWIDTH", b"1") == b"1" and obj["OWNERPARTID"] == b"1"):
            points = list()
            for location in range(int(obj["LOCATIONCOUNT"])):
                location = format(1 + location)
                points.append(tuple(int(obj[x + location]) for x in "XY"))
            renderer.polygon(colour=colour(obj["COLOR"]), points=points)
        elif (obj.keys() - {"INDEXINSHEET", "ISNOTACCESIBLE", "OWNERINDEX", "ORIENTATION", "JUSTIFICATION", "COLOR"} == {"RECORD", "FONTID", "LOCATION.X", "LOCATION.Y", "OWNERPARTID", "TEXT"} and
        obj["RECORD"] == Record.LABEL):
            if obj["OWNERPARTID"] == b"-1" or obj["OWNERPARTID"] == objects[1 + int(obj["OWNERINDEX"])]["CURRENTPARTID"]:
                text(renderer, obj)
        elif (obj.keys() - {"INDEXINSHEET"} == {"RECORD", "COLOR", "LOCATION.X", "LOCATION.Y", "OWNERPARTID"} and
        obj["RECORD"] == b"22" and obj["OWNERPARTID"] == b"-1"):
            attrs = {"xlink:href": "#nc"}
            renderer._colour(attrs, colour(obj["COLOR"]))
            for x in range(2):
                location = int(obj["LOCATION." + "XY"[x]])
                attrs["xy"[x]] = format(location * (1, -1)[x])
            renderer.emptyelement("use", attrs)
        elif (obj.keys() - {"CLIPTORECT"} == {"RECORD", "ALIGNMENT", "AREACOLOR", "CORNER.X", "CORNER.Y", "FONTID", "ISSOLID", "LOCATION.X", "LOCATION.Y", "OWNERPARTID", "Text", "WORDWRAP"} and
        obj["RECORD"] == b"28" and obj["ALIGNMENT"] == b"1" and obj["AREACOLOR"] == b"16777215" and obj.get("CLIPTORECT", b"T") == b"T" and obj["ISSOLID"] == b"T" and obj["OWNERPARTID"] == b"-1" and obj["WORDWRAP"] == b"T"):
            attrs = {"class": "font" + obj["FONTID"].decode("ascii")}
            lhs = int(obj["LOCATION.X"])
            attrs.update(transform="translate({}, {})".format(lhs, -int(obj["CORNER.Y"])))
            with renderer.element("text", attrs):
                wrapper = TextWrapper(width=(int(obj["CORNER.X"]) - lhs) / 4.375)  # Very hacky approximation of the size of each character as one en wide
                for hardline in obj["Text"].decode("ascii").split("~1"):
                    for softline in wrapper.wrap(hardline):
                        renderer.tree(("tspan", {"x": "0", "dy": "10", "xml:space": "preserve"}, (softline,)))
        
        elif (obj.keys() == {"RECORD", "OWNERINDEX", "ISNOTACCESIBLE", "OWNERPARTID", "LINEWIDTH", "COLOR", "LOCATIONCOUNT", "X1", "Y1", "X2", "Y2", "X3", "Y3", "X4", "Y4"} and
        obj["RECORD"] == Record.BEZIER and obj["ISNOTACCESIBLE"] == b"T" and obj["OWNERPARTID"] == b"1" and obj["LINEWIDTH"] == b"1" and obj["LOCATIONCOUNT"] == b"4"):
            a = dict()
            renderer._colour(a, colour(obj["COLOR"]))
            a["d"] = "M{} C {} {} {}".format(*(",".join(format(int(obj["XY"[x] + format(1 + n)]) * (+1, -1)[x]) for x in range(2)) for n in range(4)))
            renderer.emptyelement("path", a)
        
        elif (obj.keys() - {"RADIUS_FRAC", "SECONDARYRADIUS_FRAC"} == {"RECORD", "OWNERINDEX", "ISNOTACCESIBLE", "OWNERPARTID", "LOCATION.X", "LOCATION.Y", "RADIUS", "SECONDARYRADIUS", "COLOR", "AREACOLOR", "ISSOLID"} and
        obj["RECORD"] == Record.ELLIPSE and obj["ISNOTACCESIBLE"] == b"T" and obj.get("RADIUS_FRAC", b"94381") == b"94381" and obj["SECONDARYRADIUS"] == obj["RADIUS"] and obj.get("SECONDARYRADIUS_FRAC", b"22993") == b"22993" and obj["ISSOLID"] == b"T"):
            attrs = {
                "r": obj["RADIUS"].decode("ascii"),
                "stroke-width": "0.6",
            }
            renderer._colour(attrs, colour(obj["COLOR"]))
            attrs["stroke"] = attrs.pop("color")
            renderer._colour(attrs, colour(obj["AREACOLOR"]))
            attrs["fill"] = attrs.pop("color")
            attrs.update(("c" + "xy"[x], format(int(obj["LOCATION." + "XY"[x]]) * (+1, -1)[x])) for x in range(2))
            renderer.emptyelement("circle", attrs)
        
        elif (obj.keys() - {"INDEXINSHEET", "SYMBOLTYPE"} == {"RECORD", "OWNERPARTID", "LOCATION.X", "LOCATION.Y", "XSIZE", "YSIZE", "COLOR", "AREACOLOR", "ISSOLID", "UNIQUEID"} and
        obj["RECORD"] == Record.SHEET_SYMBOL and obj["OWNERPARTID"] == b"-1" and obj["ISSOLID"] == b"T" and obj.get("SYMBOLTYPE", b"Normal") == b"Normal"):
            attrs = {
                "width": obj["XSIZE"].decode("ascii"),
                "height": obj["YSIZE"].decode("ascii"),
            }
            style = (("stroke-width", 0.6),)
            renderer._colour(attrs, colour(obj["COLOR"]))
            attrs["stroke"] = attrs.pop("color")
            renderer._colour(attrs, colour(obj["AREACOLOR"]))
            attrs["fill"] = attrs.pop("color")
            attrs.update(("xy"[x], format(int(obj["LOCATION." + "XY"[x]]) * (+1, -1)[x])) for x in range(2))
            renderer.emptyelement("rect", attrs, style=style)
        
        elif (obj.keys() - {"INDEXINSHEET"} == {"RECORD", "OWNERINDEX", "OWNERPARTID", "LOCATION.X", "LOCATION.Y", "COLOR", "FONTID", "TEXT"} and
        obj["RECORD"] in {Record.SHEET_NAME, Record.SHEET_FILE_NAME} and obj.get("INDEXINSHEET", b"-1") == b"-1" and obj["OWNERPARTID"] == b"-1"):
            text(renderer, obj)
        
        elif (obj.keys() == {"RECORD", "OWNERINDEX", "INDEXINSHEET", "OWNERPARTID", "LOCATION.X", "LOCATION.Y", "CORNER.X", "CORNER.Y", "EMBEDIMAGE", "FILENAME"} and
        obj["RECORD"] == Record.IMAGE and obj["OWNERINDEX"] == b"1" and obj["OWNERPARTID"] == b"-1" and obj["EMBEDIMAGE"] == b"T" and obj["FILENAME"] == b"newAltmLogo.bmp"):
            start = list()
            dim = list()
            for x in "XY":
                start.append(int(obj["LOCATION." + x]))
                dim.append(int(obj["CORNER." + x]) - start[-1])
            renderer.box(dim, start, width=0.6)
        
        else:
            print("".join("|{}={!r}".format(p, v) for (p, v) in sorted(obj.items())), file=stderr)
    
    renderer.finish()

def colour(c):
    return (x / 0xFF for x in int(c).to_bytes(3, "little"))

def text(renderer, obj, **kw):
    c = obj.get("COLOR")
    if c:
        kw["colour"] = colour(c)
    renderer.text(obj["TEXT"].decode("ascii"),
        point=(int(obj["LOCATION." + x]) for x in "XY"),
        font="font" + obj["FONTID"].decode("ascii"),
    **kw)

def overline(name):
    tspans = list()
    name = name.decode("ascii")
    if name.startswith("\\"):
        name = name[1:]
    
    barstart = 0
    plainstart = 0
    while True:
        backslash = name.find("\\", plainstart)
        if backslash < 0:
            break
        plain = name[plainstart:backslash - 1]
        if plain:
            bar = name[barstart:plainstart:2]
            if bar:
                tspans.append(("tspan", {"text-decoration": "overline"}, (bar,)))
            tspans.append(("tspan", dict(), (plain,)))
            barstart = backslash - 1
        plainstart = backslash + 1
    bar = name[barstart:plainstart:2]
    if bar:
        tspans.append(("tspan", {"text-decoration": "overline"}, (bar,)))
    plain = name[plainstart:]
    if plain:
        tspans.append(("tspan", dict(), (plain,)))
    return tspans

def polyline(renderer, obj):
    points = list()
    for location in range(int(obj["LOCATIONCOUNT"])):
        location = format(1 + location)
        points.append(tuple(int(obj[x + location]) for x in "XY"))
    kw = dict(points=points)
    c = obj.get("COLOR")
    if c:
        kw.update(colour=colour(c))
    renderer.polyline(**kw)

if __name__ == "__main__":
    from funcparams import command
    command()
