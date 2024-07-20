from os import listdir, popen
from tempfile import gettempdir
from sys import argv
from time import time, sleep
from random import randint
from shutil import rmtree
from threading import Thread
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
        print(f"Warning: {e}")
tempdir_dp = f"{systempdir}\\qfsi_tempdir_{time() + randint(0, 2 << 31)}"
tempunpack_dp = tempdir_dp + "\\unpack"

popen(f".\\7z.exe e \"{sb3_fp}\" -o\"{tempunpack_dp}\" >> nul").read()

if not ToolFuncs.isInvalidFile(f"{tempunpack_dp}\\project.json"):
    print("Invalid project.json.")
    ToolFuncs.exitProcess(1)

try:
    project_object = ToolFuncs.loadSb3(f"{tempunpack_dp}\\project.json", tempunpack_dp)
except Exception as e:
    print(f"Load project.json failed. err: {e}")
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

def KeyPress(
    key: str,
    shift: bool,
    ctrl: bool,
    alt: bool,
    repeat: bool,
    scratch_keypress_only: bool = False
):
    ScratchKeyPressEventKey = "space" if key == " " else (
        key if len(key) == 1 and ord("a") <= ord(key) <= ord("z") else (
            "down arrow" if key == "arrowdown" else (
                "up arrow" if key == "arrowup" else (
                    "left arrow" if key == "arrowleft" else (
                        "right arrow" if key == "arrowright" else (
                            key if len(key) == 1 and ord("0") <= ord(key) <= ord("9") else None
                        )
                    )
                )
            )
        )
    )
    if ScratchKeyPressEventKey is not None:
        for target, codeblock, presskey in WhenKeyPressKeyNodes:
            if presskey == ScratchKeyPressEventKey or presskey == "any":
                RunCodeBlock(target, codeblock)
    if scratch_keypress_only: return None

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
    for target, codeblock in WhenTargetClickedNodes:
        window.run_js_code(
            f"\
            ctx_backup = ctx;\
            ctx = offscreen_ctx;\
            ctx.clearRect(0, 0, offscreen_canvas_ele.width, offscreen_canvas_ele.height);\
            "
        )
        RenderTarget(target)
        window.run_js_wait_code()
        intarget = window.run_js_code(f"ctx.getImageData({x}, {y}, 1, 1).data[3] != 0.0;")
        window.run_js_code("ctx = ctx_backup; delete ctx_backup;")
        if intarget:
            RunCodeBlock(target, codeblock)

def ChangeBgCallback(target: ScratchObjects.ScratchTarget):
    currentName = ScratchObjects.Stage.costumes[ScratchObjects.Stage.currentCostume].name
    for target, codeblock, bgname in WhenChangeBgToNodes:
        if bgname == currentName:
            RunCodeBlock(target, codeblock)

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
            RunCodeBlock(target, codeblock)
            i[-2] = False
        i[-1] = jvar

def MainInterpreter():
    global MasterCodeNodes
    global WhenKeyPressKeyNodes
    global WhenTargetClickedNodes
    global WhenChangeBgToNodes
    global WhenGtNodes
    global WhenReceiveNodes
    
    Thread(target=Render, daemon=True).start()
    MasterCodeNodes = [(t, v) for t in project_object.targets for v in t.blocks.values() if v.opcode == "event_whenflagclicked"]
    WhenKeyPressKeyNodes = [(t, v, t.ScratchEval(v)) for t in project_object.targets for v in t.blocks.values() if v.opcode == "event_whenkeypressed"]
    WhenTargetClickedNodes = [(t, v) for t in project_object.targets for v in t.blocks.values() if v.opcode == "event_whenthisspriteclicked"]
    WhenChangeBgToNodes = [(t, v, t.ScratchEval(v)) for t in project_object.targets for v in t.blocks.values() if v.opcode == "event_whenbackdropswitchesto"]
    WhenGtNodes = [[(t, v, float(t.getInputValue(*v.inputs["VALUE"])), t.ScratchEval(v)), True, None] for t in project_object.targets for v in t.blocks.values() if v.opcode == "event_whengreaterthan"]
    WhenReceiveNodes = [(v, t.ScratchEval(v)) for t in project_object.targets for v in t.blocks.values() if v.opcode == "event_whenbroadcastreceived"]
    
    window.jsapi.set_attr("KeyPress", KeyPress)
    window.jsapi.set_attr("MouseWheel", MouseWheel)
    window.jsapi.set_attr("MouseDown", MouseDown)
    window.run_js_code("_KeyPress = (e) => {pywebview.api.call_attr('KeyPress', e.key.toLowerCase(), e.shiftKey, e.ctrlKey, e.altKey, e.repeat);};")
    window.run_js_code("_MouseWheel = (e) => {pywebview.api.call_attr('MouseWheel', e.clientX, e.clientY, e.delta, e.wheelDelta);};")
    window.run_js_code("_MouseDown = (e) => {pywebview.api.call_attr('MouseDown', e.clientX, e.clientY, e.button);};")
    window.run_js_code("window.addEventListener('keydown', _KeyPress);")
    window.run_js_code("window.addEventListener('wheel', _MouseWheel);")
    window.run_js_code("window.addEventListener('mousedown', _MouseDown);")
    
    for target in project_object.targets:
        target.timerst = time()
        target.timercallback = TimerCallback
    
    for i in MasterCodeNodes:
        Thread(target=FlagClicked_ThreadInterator, args=i, daemon=True).start()

def FlagClicked_ThreadInterator(target: ScratchObjects.ScratchTarget, node: ScratchObjects.ScratchCodeBlock):
    if node.next:
        RunCodeBlock(target, target.blocks[node.next])

def getMousePosOfScratch() -> tuple[float, float]:
    try:
        cpos_x, cpos_y = GetCursorPos()
        cpos_x, cpos_y = cpos_x - window.winfo_x(), cpos_y - window.winfo_y()
        cpos_x, cpos_y = cpos_x - dw_legacy, cpos_y - dh_legacy
        cpos_x, cpos_y = cpos_x / w, cpos_y / h
        cpos_x, cpos_y = cpos_x * stage_w - stage_w / 2, cpos_y * stage_h - stage_h / 2
        return cpos_x, -cpos_y
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

@ToolFuncs.ThreadFunc
def RunCodeBlock(target: ScratchObjects.ScratchTarget, codeblock: ScratchObjects.ScratchCodeBlock, runtext:bool=True):
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
            
            case "looks_sayforsecs": pass
            
            case "looks_say": pass
            
            case "looks_thinkforsecs": pass
            
            case "looks_think": pass
            
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
            
            case "looks_switchbackdroptoandwait": ...
            
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
            
            case "sound_changeeffectby": pass
            
            case "sound_seteffectto": pass
            
            case "sound_cleareffects": pass
            
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
                            Thread(target=RunCodeBlock, args=(target, broadcast_codeblock), daemon=True).start()
                        else:
                            RunCodeBlock(target, broadcast_codeblock)
            
            case "control_wait":
                sleep(float(target.getInputValue(*codeblock.inputs["DURATION"])))
            
            case "control_repeat":
                Run_Repeat(target, codeblock)
                
            case "control_forever":
                Run_Forever(target, codeblock)
            
            case "control_if":
                ifvar = target.getInputValue(*codeblock.inputs["CONDITION"])
                if ifvar:
                    Run_If(target, codeblock)
            
            case "control_if_else":
                ifvar = target.getInputValue(*codeblock.inputs["CONDITION"])
                Run_IfElse(target, codeblock, ifvar)
            
            case "control_wait_until":
                while not target.getInputValue(*codeblock.inputs["CONDITION"]): sleep(RunWait)
            
            case "control_repeat_until":
                get_ifvar = lambda: target.getInputValue(*codeblock.inputs["CONDITION"])
                Run_RepeatUntil(target, codeblock, get_ifvar)
            
            case "control_stop":
                print(codeblock)

            case "sensing_resettimer":
                target.timerst = time()
    except StopAsyncIteration as e:
        print(f"Error in RunCodeBlock: {e}")
    
    sleep(RunWait)
    if codeblock.next and runtext:
        RunCodeBlock(target, target.blocks[codeblock.next])

@ToolFuncs.ThreadFunc
def Run_Forever(target: ScratchObjects.ScratchTarget, codeblock: ScratchObjects.ScratchCodeBlock):
    if codeblock.inputs["SUBSTACK"][1] is None:
        while True: sleep(RunWait)
        
    context = ScratchObjects.ScratchContext(target, codeblock)
    while True:
        for running in context:
            RunCodeBlock(target, running, False)

@ToolFuncs.ThreadFunc
def Run_Repeat(target: ScratchObjects.ScratchTarget, codeblock: ScratchObjects.ScratchCodeBlock):
    looptimes = int(target.getInputValue(*codeblock.inputs["TIMES"]))
    if looptimes <= 0: return None
    if codeblock.inputs["SUBSTACK"][1] is None:
        sleep(RunWait * looptimes)
    
    context = ScratchObjects.ScratchContext(target, codeblock)
    for _ in [None] * looptimes:
        for running in context:
            RunCodeBlock(target, running, False)

@ToolFuncs.ThreadFunc
def Run_If(target: ScratchObjects.ScratchTarget, codeblock: ScratchObjects.ScratchCodeBlock):
    context = ScratchObjects.ScratchContext(target, codeblock)
    for running in context:
        RunCodeBlock(target, running, False)

@ToolFuncs.ThreadFunc
def Run_IfElse(target: ScratchObjects.ScratchTarget, codeblock: ScratchObjects.ScratchCodeBlock, ifvar: bool):
    substack = "SUBSTACK" if ifvar else "SUBSTACK2"
    context = ScratchObjects.ScratchContext(target, codeblock, substack)
    for running in context:
        RunCodeBlock(target, running, False)

@ToolFuncs.ThreadFunc
def Run_RepeatUntil(target: ScratchObjects.ScratchTarget, codeblock: ScratchObjects.ScratchCodeBlock, get_ifvar: typing.Callable[[], bool]):
    if codeblock.inputs["SUBSTACK"][1] is None: return None
        
    context = ScratchObjects.ScratchContext(target, codeblock)
    while not get_ifvar():
        for running in context:
            RunCodeBlock(target, running, False)

def Render():
    while True:
        window.clear_canvas(wait_execute=True)
        
        for target in sorted(project_object.targets, key = lambda x: x.layerOrder):
            RenderTarget(target)
            
        window.run_js_wait_code()
        sleep(1 / 120)

def RenderTarget(target: ScratchObjects.ScratchTarget):
    if target.tempo is not None:
        # stage
        costome = target.costumes[target.currentCostume]
        imp = costome.w / costome.h
        if imp == w / h:
            window.create_image(
                costome.pyresid,
                0, 0,
                w, h,
                wait_execute = True
            )
        elif imp > w / h:
            imh = w / imp
            window.create_image(
                costome.pyresid,
                0, h / 2 - imh / 2,
                w, imh,
                wait_execute = True
            )
        else:
            imw = h * imp
            window.create_image(
                costome.pyresid,
                w / 2 - imw / 2, 0,
                imw, h,
                wait_execute = True
            )
    else:
        # sprite
        if not target.visible:
            return None
        costome = target.costumes[target.currentCostume]
        tempdeg = target.direction % (360 if target.direction >= 0 else -360)
        usd = False # Upsidedown
        if target.rotationStyle == "all around":
            deg = tempdeg
        elif target.rotationStyle == "left-right":
            deg = 90 if tempdeg >= 0 else -90
            if deg == -90: usd = True
        else:
            deg = 90
        tw, th = costome.w * target.size / 100, costome.h * target.size / 100
        tw /= 480; th /= 360
        tw *= w; th *= h
        if costome.bitmapResolution is not None: tw /= costome.bitmapResolution; th /= costome.bitmapResolution
        x, y = ((target.x / 480) + 0.5) * w, ((-target.y / 360) + 0.5) * h
        window.run_js_code(
            f"\
            {"usd = true; " if usd else ""}ctx.drawRotateImage(\
                {window.get_img_jsvarname(costome.pyresid)},\
                {x}, {y}, {tw}, {th}, {deg - 90}, 1.0\
            ); {"usd = false;" if usd else ""}\
            ",
            add_code_array=True
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