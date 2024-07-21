from os import listdir, popen
from tempfile import gettempdir
from sys import argv
from time import time, sleep
from random import randint
from shutil import rmtree
from threading import Thread
from ctypes import windll
import copy
import math
import typing

from PIL import Image
from win32api import GetCursorPos
import webcvapis

import ToolFuncs
import ClineHelp
import ScratchObjects
import PlaySound

if len(argv) < 2:
    print(ClineHelp.HELP)
    ToolFuncs.exitProcess()

sb3_fp = argv[1]
if not ToolFuncs.isInvalidFile(sb3_fp):
    print("Invalid file.")
    ToolFuncs.exitProcess(1)

if not (ToolFuncs.isInvalidFile(".\\7z.exe") and ToolFuncs.isInvalidFile(".\\7z.dll")):
    print("7z.exe or 7z.dll not found.")
    ToolFuncs.exitProcess(1)

systempdir = gettempdir()
for dn in [i for i in listdir(systempdir) if ToolFuncs.isQfsiTempdir(systempdir, i)]:
    dp = f"{systempdir}\\{dn}"
    try:
        rmtree(dp)
    except Exception as e:
        print(f"Warning: {e.__class__}, {e}")
tempdir_dp = f"{systempdir}\\qfsi_tempdir_{time() + randint(0, 2 << 31)}"
tempunpack_dp = tempdir_dp + "\\unpack"

popen(f".\\7z.exe e \"{sb3_fp}\" -o\"{tempunpack_dp}\" >> nul").read()

if not ToolFuncs.isInvalidFile(f"{tempunpack_dp}\\project.json"):
    print("Invalid project.json.")
    ToolFuncs.exitProcess(1)

try:
    project_object = ToolFuncs.loadSb3(f"{tempunpack_dp}\\project.json", tempunpack_dp)
except Exception as e:
    print(f"Load project.json failed. err: {e.__class__}, {e}")
    ToolFuncs.exitProcess(1)

stage_w, stage_h = 480, 360
stage_mleft = -240
stage_mtop = 180
stage_mright = 240
stage_mbottom = -180
RunWait = 1 / 120
AFps = 120
soundbuffers = {} # if buffer is collected by python, sound will be stop.
PlaySound.setVolume(1.0)
Loudness = -1.0
rtssManager = ScratchObjects.ScratchRuntimeStackManager([])
KeyStates = {}
MouseStates = {}
Number = int|float

def KeyPress(
    key: str,
    shift: bool,
    ctrl: bool,
    alt: bool,
    repeat: bool,
    scratch_keypress_only: bool = False
):
    ScratchKeyPressEventKey = ToolFuncs.Key2Scratch(key)
    KeyStates[ScratchKeyPressEventKey] = True
    if ScratchKeyPressEventKey is not None:
        for target, codeblock, presskey in WhenKeyPressKeyNodes:
            if presskey == ScratchKeyPressEventKey or presskey == "any":
                RunCodeBlock(target, codeblock, rtssManager.get_new(target, codeblock))
    if scratch_keypress_only: return None

def KeyUp(
    key: str
):
    ScratchKeyPressEventKey = ToolFuncs.Key2Scratch(key)
    KeyStates[ScratchKeyPressEventKey] = False

def MouseWheel(
    x: int,
    y: int,
    detail: int|None,
    wheelDelta: int|None
):
    up = True
    if detail is not None:
        up = detail > 0
    if wheelDelta is not None:
        up = wheelDelta > 0
    
    KeyPress(
        key = "arrowup" if up else "arrowdown",
        shift = False,
        ctrl = False,
        alt = False,
        repeat = False,
        scratch_keypress_only = True
    )

def MouseDown(
    x: int,
    y: int,
    button: int
):
    "0: left, 1: middle, 2: right"
    MouseStates[button] = True
    for target, codeblock in WhenTargetClickedNodes:
        if PosInTarget(x, y, target):
            RunCodeBlock(target, codeblock, rtssManager.get_new(target, codeblock))

def MouseUp(
    x: int,
    y: int,
    button: int
):
    "0: left, 1: middle, 2: right"
    MouseStates[button] = False

def PosInTarget(x: Number, y: Number, target: ScratchObjects.ScratchTarget) -> bool:
    x, y = int(x), int(y)
    x, y = x - (target.x + stage_w / 2) / stage_w * w, y - (- target.y + stage_h / 2) / stage_h * h
    costume = target.costumes[target.currentCostume]
    deg = math.degrees(math.atan2(y, x))
    x, y = ToolFuncs.rotate_point(
        0, 0, deg - target.direction, math.sqrt(x ** 2 + y ** 2)
    )
    x, y = int(x * costume.scale), int(y * costume.scale)
    try: return costume.data.getpixel((x, y))[-1] > 0
    except IndexError: return False

def fixPosOutStage(x: Number, y: Number) -> tuple[Number, Number]:
    x = x if stage_mleft <= x <= stage_mright else (stage_mleft if x < stage_mleft else stage_mright)
    y = y if stage_mbottom <= y <= stage_mtop else (stage_mbottom if y < stage_mbottom else stage_mtop)
    return x, y

def ChangeBgCallback(target: ScratchObjects.ScratchTarget):
    currentName = ScratchObjects.Stage.costumes[ScratchObjects.Stage.currentCostume].name
    for target, codeblock, bgname in WhenChangeBgToNodes:
        if bgname == currentName:
            RunCodeBlock(target, codeblock, rtssManager.get_new(target, codeblock))

def TimerCallback(target: ScratchObjects.ScratchTarget):
    for i in WhenGtNodes:
        tempv, _, _ = i
        ttarget, codeblock, value, n2 = tempv
        if ttarget is not target: continue
        judge, jvar = False, None
        match n2:
            case "TIMER":
                judge = target.timertime > value
                jvar = target.timertime
            case "LOUDNESS":
                judge = Loudness > value
                jvar = Loudness
        if jvar is None: return None
        if not i[-2]:
            if i[-1] <= value and judge:
                i[-2] = True
        if judge and i[-2]:
            RunCodeBlock(target, codeblock, rtssManager.get_new(target, codeblock))
            i[-2] = False
        i[-1] = jvar

def ScratchEvalHelper(target: ScratchObjects.ScratchTarget, code:ScratchObjects.ScratchCodeBlock, **kwargs):
    match code.opcode:
        case "sensing_touchingobject":
            match kwargs["menuv"]:
                case "_mouse_":
                    return PosInTarget(*map(int, getMousePosOfWindow()), target)
                case "_edge_":
                    return not TargetInStage(target)
                case _:
                    targetbox = getTargetBox(target)
                    othbox = getTargetBox([i for i in project_object.targets if i.name == kwargs["menuv"]][0])
                    return any(batch_is_intersect(
                        [
                            (targetbox[0], targetbox[1]),
                            (targetbox[1], targetbox[2]),
                            (targetbox[2], targetbox[3]),
                            (targetbox[3], targetbox[0])
                        ],
                        [
                            (othbox[0], othbox[1]),
                            (othbox[1], othbox[2]),
                            (othbox[2], othbox[3]),
                            (othbox[3], othbox[0])
                        ],
                    ))
        case "sensing_touchingcolor": # FIXME, if color is below the target, it will return false. and i think it has more err.
            r, g, b = kwargs["color"]
            cvname = f"ofcr_cv{int(time() * randint(0, 2 << 31))}"
            ctxname = f"ofcr_ctx{int(time() * randint(0, 2 << 31))}"
            window.run_js_code(f'''var [{cvname}, {ctxname}] = createTempCanvas();''')
            RenderTarget(target, ctxname, False)
            ans = window.run_js_code(f"touchColorAtMainCv({r}, {g}, {b}, {ctxname});")
            window.run_js_code(f"delete {cvname}; delete {ctxname};")
            return ans
        case "sensing_coloristouchingcolor": # FIXME, if color is below the target, it will return false. and i think it has more err.
            r1, g1, b1 = kwargs["c1"]
            r2, g2, b2 = kwargs["c2"]
            cvname = f"ofcr_cv{int(time() * randint(0, 2 << 31))}"
            ctxname = f"ofcr_ctx{int(time() * randint(0, 2 << 31))}"
            window.run_js_code(f'''var [{cvname}, {ctxname}] = createTempCanvas();''')
            RenderTarget(target, ctxname, False)
            ans = window.run_js_code(f"colorTouchColor({r1}, {g1}, {b1}, {r2}, {g2}, {b2}, {ctxname});")
            window.run_js_code(f"delete {cvname}; delete {ctxname};")
            return ans
        case "sensing_distanceto":
            menuv = kwargs["menuv"]
            match menuv:
                case "_mouse_":
                    p = fixPosOutStage(*getMousePosOfScratch())
                case _:
                    ptarget = [i for i in project_object.targets if i.name == menuv][0]
                    p = ptarget.x, ptarget.y
            return math.sqrt((target.x - p[0]) ** 2 + (target.y - p[1]) ** 2)
        case "sensing_keypressed":
            key = kwargs["key"]
            if key == "any":
                return any(KeyStates.values())
            return KeyStates.get(key, False)
        case "sensing_mousedown":
            return any(MouseStates.values())
        case "sensing_mousex":
            return fixPosOutStage(*getMousePosOfScratch())[0]
        case "sensing_mousey":
            return fixPosOutStage(*getMousePosOfScratch())[1]
        case "sensing_of":
            datatarget_name = kwargs["datatarget_name"]
            targetproperty_name = kwargs["targetproperty_name"]
            
            match datatarget_name:
                case "_stage_":
                    datatarget = ScratchObjects.Stage
                    match targetproperty_name:
                        case "backdrop #":
                            return datatarget.currentCostume + 1
                        case "backdrop name":
                            return datatarget.costumes[datatarget.currentCostume].name
                        case "volume":
                            return datatarget.volume
                        case _: # target local variable
                            value = [i for i in datatarget.variables.values() if i.name == targetproperty_name][0].value
                            if isinstance(value, list):
                                return " ".join(map(str, value))
                            return value
                case _: # Sprite
                    datatarget = [i for i in project_object.targets if i.name == datatarget_name][0]
                    match targetproperty_name:
                        case "x position":
                            return datatarget.x
                        case "y position":
                            return datatarget.y
                        case "direction":
                            return datatarget.direction
                        case "costume #":
                            return datatarget.currentCostume + 1
                        case "costume name":
                            return datatarget.costumes[datatarget.currentCostume].name
                        case "size":
                            return datatarget.size
                        case "volume":
                            return datatarget.volume
                        case _: # target local variable
                            value = [i for i in datatarget.variables.values() if i.name == targetproperty_name][0].value
                            if isinstance(value, list):
                                return " ".join(map(str, value))
                            return value
        case _:
            assert False

def MainInterpreter():
    global MasterCodeNodes
    global WhenKeyPressKeyNodes
    global WhenTargetClickedNodes
    global WhenChangeBgToNodes
    global WhenGtNodes
    global WhenReceiveNodes
    global WhenStartAsCloneNodes
    
    ScratchObjects.ScratchEvalHelper = ScratchEvalHelper
    
    Thread(target=Render, daemon=True).start()
    MasterCodeNodes = [(t, v) for t in project_object.targets for v in t.blocks.values() if v.opcode == "event_whenflagclicked"]
    WhenKeyPressKeyNodes = [(t, v, t.ScratchEval(v)) for t in project_object.targets for v in t.blocks.values() if v.opcode == "event_whenkeypressed"]
    WhenTargetClickedNodes = [(t, v) for t in project_object.targets for v in t.blocks.values() if v.opcode == "event_whenthisspriteclicked"]
    WhenChangeBgToNodes = [(t, v, t.ScratchEval(v)) for t in project_object.targets for v in t.blocks.values() if v.opcode == "event_whenbackdropswitchesto"]
    WhenGtNodes = [[(t, v, float(t.getInputValue(*v.inputs["VALUE"])), t.ScratchEval(v)), True, None] for t in project_object.targets for v in t.blocks.values() if v.opcode == "event_whengreaterthan"]
    WhenReceiveNodes = [(v, t.ScratchEval(v)) for t in project_object.targets for v in t.blocks.values() if v.opcode == "event_whenbroadcastreceived"]
    WhenStartAsCloneNodes = [(t, v) for t in project_object.targets for v in t.blocks.values() if v.opcode == "control_start_as_clone"]
    
    window.jsapi.set_attr("KeyPress", KeyPress)
    window.jsapi.set_attr("KeyUp", KeyUp)
    window.jsapi.set_attr("MouseWheel", MouseWheel)
    window.jsapi.set_attr("MouseDown", MouseDown)
    window.jsapi.set_attr("MouseUp", MouseUp)
    window.run_js_code("_KeyPress = (e) => {pywebview.api.call_attr('KeyPress', e.key.toLowerCase(), e.shiftKey, e.ctrlKey, e.altKey, e.repeat);};")
    window.run_js_code("_KeyUp = (e) => {pywebview.api.call_attr('KeyUp', e.key.toLowerCase());};")
    window.run_js_code("_MouseWheel = (e) => {pywebview.api.call_attr('MouseWheel', e.clientX, e.clientY, e.delta, e.wheelDelta);};")
    window.run_js_code("_MouseDown = (e) => {pywebview.api.call_attr('MouseDown', e.clientX, e.clientY, e.button);};")
    window.run_js_code("_MouseUp = (e) => {pywebview.api.call_attr('MouseUp', e.clientX, e.clientY, e.button);};")
    window.run_js_code("window.addEventListener('keydown', _KeyPress);")
    window.run_js_code("window.addEventListener('keyup', _KeyUp);")
    window.run_js_code("window.addEventListener('wheel', _MouseWheel);")
    window.run_js_code("window.addEventListener('mousedown', _MouseDown);")
    window.run_js_code("window.addEventListener('mouseup', _MouseUp);")
    
    for target in project_object.targets:
        target.timerst = time()
        target.timercallback = TimerCallback
    
    for i in MasterCodeNodes:
        Thread(target=FlagClicked_ThreadInterator, args=i, daemon=True).start()

def FlagClicked_ThreadInterator(target: ScratchObjects.ScratchTarget, node: ScratchObjects.ScratchCodeBlock):
    if node.next:
        RunCodeBlock(target, target.blocks[node.next], rtssManager.get_new(target, node))

def getMousePosOfScratch() -> tuple[float, float]:
    cpos_x, cpos_y = getMousePosOfWindow()
    cpos_x, cpos_y = cpos_x / w, cpos_y / h
    cpos_x, cpos_y = cpos_x * stage_w - stage_w / 2, cpos_y * stage_h - stage_h / 2
    return cpos_x, -cpos_y

def getMousePosOfWindow() -> tuple[float, float]:
    try:
        cpos_x, cpos_y = GetCursorPos()
        cpos_x, cpos_y = cpos_x - window.winfo_x(), cpos_y - window.winfo_y()
        cpos_x, cpos_y = cpos_x - dw_legacy, cpos_y - dh_legacy
        return cpos_x, cpos_y
    except Exception: # window closed
        return 0.0, 0.0

def FixOutStageTarget(target: ScratchObjects.ScratchTarget):
    if target.x < stage_mleft:
        target.x = stage_mleft
    elif target.x > stage_mright:
        target.x = stage_mright
    if target.y > stage_mtop:
        target.y = stage_mtop
    elif target.y < stage_mbottom:
        target.y = stage_mbottom

def FixTooBigTarget(target: ScratchObjects.ScratchTarget):
    costume = target.costumes[target.currentCostume]
    mins = min(stage_w * 1.5 / costume.w * 100, stage_h * 1.5 / costume.h * 100)
    if target.size > mins:
        target.size = mins

def DestoryStack(stack: ScratchObjects.ScratchRuntimeStack):
    try: rtssManager.destory_stack(stack)
    except ValueError: pass

def TargetInStage(target: ScratchObjects.ScratchTarget) -> bool:
    lt, rt, rb, lb  = getTargetBox(target)
    return pointInScreen(lt) and pointInScreen(rt) and pointInScreen(rb) and pointInScreen(lb)

def pointInScreen(x: float, y: float) -> bool:
    return 0 <= x <= w and 0 <= y <= h

def getTargetBox(target: ScratchObjects.ScratchTarget) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]:
    costume = target.costumes[target.currentCostume]
    x, y = (target.x + stage_w / 2) / stage_w * w, (- target.y + stage_h / 2) / stage_h * h
    tw, th = costume.w * target.size / 100, costume.h * target.size / 100
    tw /= 480; th /= 360
    tw *= w; th *= h
    if target.rotationStyle == "don't rotate":
        lt = x - tw / 2, y - th / 2
        rt = x + tw / 2, y - th / 2
        rb = x + tw / 2, y + th / 2
        lb = x - tw / 2, y + th / 2
        return lt, rt, rb, lb
    elif target.rotationStyle == "left-right":
        deg = 90 if target.direction >= 0 else -90
    else:
        deg = target.direction
    lt = - tw / 2, - th / 2
    rt = + tw / 2, - th / 2
    rb = + tw / 2, + th / 2
    lb = - tw / 2, + th / 2
    lt = ToolFuncs.rotate_point2(*lt, deg + 90)
    rt = ToolFuncs.rotate_point2(*rt, deg + 90)
    rb = ToolFuncs.rotate_point2(*rb, deg + 90)
    lb = ToolFuncs.rotate_point2(*lb, deg + 90)
    lt = lt[0] + x, lt[1] + y
    rt = rt[0] + x, rt[1] + y
    rb = rb[0] + x, rb[1] + y
    lb = lb[0] + x, lb[1] + y
    return lt, rt, rb, lb

def batch_is_intersect(
    lines_group_1:typing.List[typing.Tuple[
        typing.Tuple[float, float],
        typing.Tuple[float, float]
    ]],
    lines_group_2:typing.List[typing.Tuple[
        typing.Tuple[float, float],
        typing.Tuple[float, float]
    ]]
) -> typing.Generator[bool, None, None]:
    for i in lines_group_1:
        for j in lines_group_2:
            yield is_intersect(i,j)

def is_intersect(
    line_1:typing.Tuple[
        typing.Tuple[float, float],
        typing.Tuple[float, float]
    ],
    line_2:typing.Tuple[
        typing.Tuple[float, float],
        typing.Tuple[float, float]
    ]
) -> bool:
    if (
        max(line_1[0][0], line_1[1][0]) < min(line_2[0][0], line_2[1][0]) or
        max(line_2[0][0], line_2[1][0]) < min(line_1[0][0], line_1[1][0]) or
        max(line_1[0][1], line_1[1][1]) < min(line_2[0][1], line_2[1][1]) or
        max(line_2[0][1], line_2[1][1]) < min(line_1[0][1], line_1[1][1])
    ):
        return False
    else:
        return True

@ToolFuncs.ThreadFunc
def RunCodeBlock(
    target: ScratchObjects.ScratchTarget,
    codeblock: ScratchObjects.ScratchCodeBlock,
    stack: ScratchObjects.ScratchRuntimeStack,
    runtext:bool=True
):
    if stack.stopped:
        DestoryStack(stack)
        return None
    
    try:
        match codeblock.opcode:
            case "motion_movesteps":
                target.x, target.y = ToolFuncs.rotate_point(
                    target.x, target.y, target.direction,
                    float(target.getInputValue(*codeblock.inputs["STEPS"]))
                )
                FixOutStageTarget(target)
                
            case "motion_turnright":
                target.direction += float(target.getInputValue(*codeblock.inputs["DEGREES"]))
                
            case "motion_turnleft":
                target.direction -= float(target.getInputValue(*codeblock.inputs["DEGREES"]))
                
            case "motion_goto":
                menuv = target.getInputValue(*codeblock.inputs["TO"])
                match menuv:
                    case "_random_":
                        target.x, target.y = randint(stage_mleft, stage_mright), randint(stage_mbottom, stage_mtop)
                    case "_mouse_":
                        target.x, target.y = getMousePosOfScratch()
                    case _:
                        movetarget = [i for i in project_object.targets if i.name == menuv][0]
                        target.x, target.y = movetarget.x, movetarget.y
                FixOutStageTarget(target)
                
            case "motion_gotoxy":
                target.x, target.y = float(target.getInputValue(*codeblock.inputs["X"])), float(target.getInputValue(*codeblock.inputs["Y"]))
                FixOutStageTarget(target)
                
            case "motion_glideto" | "motion_glidesecstoxy":
                asec = float(target.getInputValue(*codeblock.inputs["SECS"]))
                rx, ry = target.x, target.y
                
                if codeblock.opcode == "motion_glideto":
                    menuv = target.getInputValue(*codeblock.inputs["TO"])
                    match menuv:
                        case "_random_":
                            tx, ty = randint(stage_mleft, stage_mright), randint(stage_mbottom, stage_mtop)
                        case "_mouse_":
                            tx, ty = getMousePosOfScratch()
                        case _:
                            movetarget = [i for i in project_object.targets if i.name == menuv][0]
                            tx, ty = movetarget.x, movetarget.y
                else: # motion_glidesecstoxy
                    tx, ty = float(target.getInputValue(*codeblock.inputs["X"])), float(target.getInputValue(*codeblock.inputs["Y"]))
                        
                ast = time()
                while time() - ast < asec:
                    p = ((time() - ast) / asec) ** 2
                    p = 1.0 - (1.0 - p) ** 4 # ease
                    nx, ny = rx + (tx - rx) * p, ry + (ty - ry) * p
                    target.x, target.y = nx, ny
                    FixOutStageTarget(target)
                    sleep(1 / AFps)
                target.x, target.y = tx, ty
                FixOutStageTarget(target)
                
            case "motion_pointindirection":
                target.direction = float(target.getInputValue(*codeblock.inputs["DIRECTION"]))
                
            case "motion_pointtowards":
                menuv = target.getInputValue(*codeblock.inputs["TOWARDS"])
                match menuv:
                    case "_mouse_":
                        twx, twy = getMousePosOfScratch()
                    case _:
                        movetarget = [i for i in project_object.targets if i.name == menuv][0]
                        twx, twy = movetarget.x, movetarget.y
                
                twx, twy = twx - target.x, twy - target.y
                target.direction = 90 - math.degrees(math.atan2(twy, twx))
            
            case "motion_changexby":
                dx = float(target.getInputValue(*codeblock.inputs["DX"]))
                target.x += dx
                FixOutStageTarget(target)
            
            case "motion_setx":
                target.x = float(target.getInputValue(*codeblock.inputs["X"]))
                FixOutStageTarget(target)
            
            case "motion_changeyby":
                dy = float(target.getInputValue(*codeblock.inputs["DY"]))
                target.y += dy
                FixOutStageTarget(target)
            
            case "motion_sety":
                target.y = float(target.getInputValue(*codeblock.inputs["Y"]))
                FixOutStageTarget(target)
            
            case "motion_ifonedgebounce":
                costume = target.costumes[target.currentCostume]
                left = target.x - costume.w / 2
                top = target.y + costume.h / 2
                right = target.x + costume.w / 2
                bottom = target.y - costume.h / 2
                
                if left < stage_mleft:
                    target.direction *= -1
                    target.x = stage_mleft + costume.w / 2
                elif right > stage_mright:
                    target.direction *= -1
                    target.x = stage_mright - costume.w / 2
                
                if top > stage_mtop:
                    target.direction = 180 - target.direction
                    target.y = stage_mtop - costume.h / 2
                elif bottom < stage_mbottom:
                    target.direction = 180 - target.direction
                    target.y = stage_mbottom + costume.h / 2
            
            case "motion_setrotationstyle":
                target.rotationStyle = codeblock.fields["STYLE"][0]
            
            case "looks_sayforsecs":
                msg = str(target.getInputValue(*codeblock.inputs["MESSAGE"]))
                waitms = int(float(target.getInputValue(*codeblock.inputs["SECS"])) * 1000)
                ToolFuncs.MessageBoxTimeout(f"{target.name} is saying", msg, 0x40, waitms)
            
            case "looks_say":
                msg = str(target.getInputValue(*codeblock.inputs["MESSAGE"]))
                Thread(target=ToolFuncs.MessageBox, args=(f"{target.name} is saying", msg, 0x40), daemon=True).start()
            
            case "looks_thinkforsecs":
                msg = str(target.getInputValue(*codeblock.inputs["MESSAGE"]))
                waitms = int(float(target.getInputValue(*codeblock.inputs["SECS"])) * 1000)
                ToolFuncs.MessageBoxTimeout(f"{target.name} is thinking", msg, 0x40, waitms)
            
            case "looks_think":
                msg = str(target.getInputValue(*codeblock.inputs["MESSAGE"]))
                Thread(target=ToolFuncs.MessageBox, args=(f"{target.name} is thinking", msg, 0x40), daemon=True).start()
            
            case "looks_switchcostumeto":
                costume_name = target.getInputValue(*codeblock.inputs["COSTUME"])
                target.currentCostume = [i.name for i in target.costumes].index(str(costume_name))
            
            case "looks_nextcostume":
                target.currentCostume = (target.currentCostume + 1) % len(target.costumes)
            
            case "looks_switchbackdropto":
                backdrop_name = target.getInputValue(*codeblock.inputs["BACKDROP"])
                match backdrop_name:
                    case "next backdrop":
                        ScratchObjects.Stage.currentCostume = (ScratchObjects.Stage.currentCostume + 1) % len(ScratchObjects.Stage.costumes)
                    case "previous backdrop":
                        ScratchObjects.Stage.currentCostume = (ScratchObjects.Stage.currentCostume - 1) % len(ScratchObjects.Stage.costumes) # for example, -1 % 3 = 2
                    case "random backdrop":
                        ScratchObjects.Stage.currentCostume = randint(0, len(ScratchObjects.Stage.costumes) - 1)
                    case _:
                        ScratchObjects.Stage.currentCostume = [i.name for i in ScratchObjects.Stage.costumes].index(backdrop_name)
                ChangeBgCallback(target)
            
            case "looks_switchbackdroptoandwait": # XXX, in scratch i cannot find this block, but it is exists in wiki...
                codeblock.opcode = "looks_switchbackdropto"
                RunCodeBlock(target, codeblock, stack, False)
            
            case "looks_nextbackdrop":
                ScratchObjects.Stage.currentCostume = (ScratchObjects.Stage.currentCostume + 1) % len(ScratchObjects.Stage.costumes)
                ChangeBgCallback(target)
            
            case "looks_changesizeby":
                target.size += float(target.getInputValue(*codeblock.inputs["CHANGE"]))
                FixTooBigTarget(target)
            
            case "looks_setsizeto":
                target.size = float(target.getInputValue(*codeblock.inputs["SIZE"]))
                FixTooBigTarget(target)
            
            case "looks_changeeffectby": ...
            
            case "looks_seteffectto": ...
            
            case "looks_cleargraphiceffects": ...
            
            case "looks_show":
                target.visible = True
                
            case "looks_hide":
                target.visible = False
                
            case "looks_gotofrontback": ...
            
            case "looks_goforwardbackwardlayers": ...
            
            case "sound_playuntildone" | "sound_play":
                menuv = target.getInputValue(*codeblock.inputs["SOUND_MENU"])
                sound_data = [i for i in target.sounds if i.name == menuv][0].data
                soundbuffers[sound_data], waitt = PlaySound.Play(sound_data)
                
                if codeblock.opcode == "sound_playuntildone":
                    waitt.join()
            
            case "sound_stopallsounds":
                soundbuffers.clear()
            
            case "sound_changeeffectby": ...
            
            case "sound_seteffectto": ...
            
            case "sound_cleareffects": ...
            
            case "sound_changevolumeby":
                target.volume += float(target.getInputValue(*codeblock.inputs["VOLUME"]))
                if target.volume < 0.0: target.volume = 0.0
                elif target.volume > 100.0: target.volume = 100.0
                PlaySound.setVolume(target.volume / 100.0)
            
            case "sound_setvolumeto":
                target.volume = float(target.getInputValue(*codeblock.inputs["VOLUME"]))
                if target.volume < 0.0: target.volume = 0.0
                elif target.volume > 100.0: target.volume = 100.0
                PlaySound.setVolume(target.volume / 100.0)
            
            case "event_broadcast" | "event_broadcastandwait":
                bcname = target.getInputValue(*codeblock.inputs["BROADCAST_INPUT"])
                if bcname not in ScratchObjects.Stage.broadcasts:
                    bcname = list(ScratchObjects.Stage.broadcasts.keys())[list(ScratchObjects.Stage.broadcasts.values()).index(bcname)]
                for broadcast_codeblock, n in WhenReceiveNodes:
                    if bcname == n:
                        if codeblock.opcode == "event_broadcast":
                            Thread(target=RunCodeBlock, args=(target, broadcast_codeblock, rtssManager.get_new(target, codeblock)), daemon=True).start()
                        else:
                            RunCodeBlock(target, broadcast_codeblock, rtssManager.get_new(target, codeblock))
            
            case "control_wait":
                sleep(float(target.getInputValue(*codeblock.inputs["DURATION"])))
            
            case "control_repeat":
                Run_Repeat(target, codeblock, stack)
                
            case "control_forever":
                Run_Forever(target, codeblock, stack)
            
            case "control_if":
                ifvar = target.getInputValue(*codeblock.inputs["CONDITION"])
                if ifvar:
                    Run_If(target, codeblock, stack)
            
            case "control_if_else":
                ifvar = target.getInputValue(*codeblock.inputs["CONDITION"])
                Run_IfElse(target, codeblock, ifvar, stack)
            
            case "control_wait_until":
                while not target.getInputValue(*codeblock.inputs["CONDITION"]): sleep(RunWait)
            
            case "control_repeat_until":
                get_ifvar = lambda: target.getInputValue(*codeblock.inputs["CONDITION"])
                Run_RepeatUntil(target, codeblock, get_ifvar, stack)
            
            case "control_stop":
                stopv = target.ScratchEval(codeblock).split(" ")[0]
                match stopv:
                    case "all":
                        for i in rtssManager.stacks:
                            i.stopped = True
                            DestoryStack(i)
                    case "this":
                        stack.stopped = True
                        DestoryStack(stack)
                    case "other":
                        for i in rtssManager.get_stacks(target):
                            if i is stack: continue
                            i.stopped = True
                            DestoryStack(i)
            
            case "control_create_clone_of":
                menuv = target.getInputValue(*codeblock.inputs["CLONE_OPTION"])
                match menuv:
                    case "_myself_":
                        clone_master = target
                    case _:
                        clone_master = [i for i in project_object.targets if i.name == menuv][0]
                
                clone_target = copy.copy(clone_master)
                clone_target.clones = []
                clone_target.isClone = True
                for ttarget, tcodeblock in WhenStartAsCloneNodes:
                    if ttarget is clone_master:
                        Thread(target=RunCodeBlock, args=(clone_target, tcodeblock, rtssManager.get_new(clone_target, tcodeblock)), daemon=True).start()
                project_object.targets.append(clone_target)
            
            case "control_delete_this_clone":
                if target.isClone:
                    project_object.targets.remove(target)
                    for i in rtssManager.get_stacks(target):
                        i.stopped = True
                        DestoryStack(i)

            case "sensing_askandwait":
                question = str(target.getInputValue(*codeblock.inputs["QUESTION"]))
                while True:
                    answer = window.run_js_code(f"prompt('{window.process_code_string_syntax_tostring(f"{target.name} is asking:\n    {question}")}');")
                    if answer is not None: break
                target.askans = answer
            
            case "sensing_setdragmode":
                target.draggable = target.ScratchEval(codeblock) == "draggable"
            
            case "sensing_resettimer":
                target.timerst = time()
    except Exception as e:
        print(f"Error in RunCodeBlock: {e.__class__}, {e}")
    
    sleep(RunWait)
    if codeblock.next and runtext:
        try:
            RunCodeBlock(target, target.blocks[codeblock.next], stack)
        except KeyError as e:
            print(f"Error in RunCodeBlock: Unknow Codeblock {e.__class__}, {e}")

@ToolFuncs.ThreadFunc
def Run_Forever(target: ScratchObjects.ScratchTarget, codeblock: ScratchObjects.ScratchCodeBlock, stack: ScratchObjects.ScratchRuntimeStack):
    if codeblock.inputs["SUBSTACK"][1] is None:
        while True:
            if stack.stopped:
                return None
            sleep(RunWait)
        
    context = ScratchObjects.ScratchContext(target, codeblock)
    while True:
        for running in context:
            RunCodeBlock(target, running, stack, False)

@ToolFuncs.ThreadFunc
def Run_Repeat(target: ScratchObjects.ScratchTarget, codeblock: ScratchObjects.ScratchCodeBlock, stack: ScratchObjects.ScratchRuntimeStack):
    looptimes = int(target.getInputValue(*codeblock.inputs["TIMES"]))
    if looptimes <= 0: return None
    if codeblock.inputs["SUBSTACK"][1] is None:
        for _ in [None] * looptimes:
            if stack.stopped:
                return None
            sleep(RunWait)
    
    context = ScratchObjects.ScratchContext(target, codeblock)
    for _ in [None] * looptimes:
        for running in context:
            RunCodeBlock(target, running, stack, False)

@ToolFuncs.ThreadFunc
def Run_If(target: ScratchObjects.ScratchTarget, codeblock: ScratchObjects.ScratchCodeBlock, stack: ScratchObjects.ScratchRuntimeStack):
    context = ScratchObjects.ScratchContext(target, codeblock)
    for running in context:
        RunCodeBlock(target, running, stack, False)

@ToolFuncs.ThreadFunc
def Run_IfElse(target: ScratchObjects.ScratchTarget, codeblock: ScratchObjects.ScratchCodeBlock, ifvar: bool, stack: ScratchObjects.ScratchRuntimeStack):
    substack = "SUBSTACK" if ifvar else "SUBSTACK2"
    context = ScratchObjects.ScratchContext(target, codeblock, substack)
    for running in context:
        RunCodeBlock(target, running, stack, False)

@ToolFuncs.ThreadFunc
def Run_RepeatUntil(target: ScratchObjects.ScratchTarget, codeblock: ScratchObjects.ScratchCodeBlock, get_ifvar: typing.Callable[[], bool], stack: ScratchObjects.ScratchRuntimeStack):
    if codeblock.inputs["SUBSTACK"][1] is None: return None
        
    context = ScratchObjects.ScratchContext(target, codeblock)
    while not get_ifvar():
        for running in context:
            RunCodeBlock(target, running, stack, False)

def Render():
    while True:
        window.clear_canvas(wait_execute=True)
        window.run_js_code(f"stage_ctx.clearRect(0, 0, {w}, {h});", add_code_array=True)
        soeredtarget = sorted(project_object.targets, key = lambda x: x.layerOrder)
        stagetargets = filter(lambda x: x.isStage, soeredtarget)
        spritetargets = filter(lambda x: not x.isStage, soeredtarget)
        
        for target in stagetargets:
            RenderTarget(target)
        window.run_js_code(f"ctx.drawImage(stage_cvele, 0, 0);", add_code_array=True)
        
        for target in spritetargets:
            RenderTarget(target)
            
        window.run_js_wait_code()
        sleep(1 / 120)

def RenderTarget(target: ScratchObjects.ScratchTarget, ctxname: str = "ctx", wait: bool = True):
    if target.tempo is not None:
        # stage
        costume = target.costumes[target.currentCostume]
        imp = costume.w / costume.h
        if imp == w / h:
            render_x, render_y = 0, 0
            render_w, render_h = w, h
        elif imp > w / h:
            imh = w / imp
            render_x, render_y = 0, h / 2 - imh / 2
            render_w, render_h = w, imh
        else:
            imw = h * imp
            render_x, render_y = w / 2 - imw / 2, 0
            render_w, render_h = imw, h
        window.run_js_code(f"\
            stage_ctx.drawImage({window.get_img_jsvarname(costume.pyresid)}, {render_x}, {render_y}, {render_w}, {render_h});\
        ", add_code_array=wait)
    else:
        # sprite
        if not target.visible:
            return None
        costume = target.costumes[target.currentCostume]
        tempdeg = target.direction % (360 if target.direction >= 0 else -360)
        usd = False # Upsidedown
        if target.rotationStyle == "all around":
            deg = tempdeg
        elif target.rotationStyle == "left-right":
            deg = 90 if tempdeg >= 0 else -90
            if deg == -90: usd = True
        else:
            deg = 90
        tw, th = costume.w * target.size / 100, costume.h * target.size / 100
        tw /= 480; th /= 360
        tw *= w; th *= h
        if costume.bitmapResolution is not None: tw /= costume.bitmapResolution; th /= costume.bitmapResolution
        x, y = ((target.x / 480) + 0.5) * w, ((-target.y / 360) + 0.5) * h
        window.run_js_code(
            f"\
            {ctxname}.drawRotateImage(\
                {window.get_img_jsvarname(costume.pyresid)},\
                {x}, {y}, {tw}, {th}, {deg - 90}, 1.0, {"true" if usd else "false"}\
            );\
            ",
            add_code_array=wait
        )

def Boot():
    for asset in ScratchObjects.Assets:
        if isinstance(asset.data, Image.Image):
            window.reg_img(asset.data, asset.pyresid)
    window.load_allimg()
    window.shutdown_fileserver()
    Thread(target=MainInterpreter, daemon=True).start()

window = webcvapis.WebCanvas(
    width = 0, height = 0,
    x = 0, y = 0,
    debug = "--debug" in argv,
    title = "Scratch Interpreter",
    resizable = False
)

window_size = min(window.winfo_screenwidth(), window.winfo_screenheight()) * 0.75 * 3
w, h = int(window_size * 0.4), int(window_size * 0.3)
window.resize(w, h)
w_legacy, h_legacy = window.winfo_legacywindowwidth(), window.winfo_legacywindowheight()
dw_legacy, dh_legacy = w - w_legacy, h - h_legacy
window.resize(w + dw_legacy, h + dh_legacy)
window.move(int(window.winfo_screenwidth() / 2 - (w + dw_legacy) / 2), int(window.winfo_screenheight() / 2 - (h + dh_legacy) / 2))

Thread(target=Boot, daemon=True).start()
window.loop_to_close()
ToolFuncs.exitProcess()