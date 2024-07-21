from __future__ import annotations
from dataclasses import dataclass
from random import randint, random
from threading import Thread
from time import time, sleep
import typing
import math

from pydub import AudioSegment
from PIL import UnidentifiedImageError, Image
import cairosvg

import ToolFuncs

AssetPath:str|None = None # Set this value before new any ScratchAsset object.
Assets:list[ScratchAsset] = []
Stage:ScratchTarget|None = None
ScratchEvalHelper = lambda *args, **kwargs: None

@dataclass
class ScratchVariable:
    name: str
    value: (
        int|
        float|
        bool|
        str
    )
    cloud:bool

@dataclass
class ScratchList:
    name: str
    items: list[int|float|str|bool]

@dataclass
class ScratchCodeBlock:
    opcode: str
    params: dict[str, str]
    next: str|None
    parent: str|None
    inputs: dict[str, list]
    fields: dict[str, list]
    shadow: bool
    topLevel: bool
    
    # mutations only
    tagName: str|None
    children: list|None
    proccode: str|None
    argumentids: list[str]|None
    warp: bool|None
    argumentnames: list[str]|None
    argumentdefaults: list[str]|None
    hasnext: bool|None

@dataclass
class ScratchAsset:
    assetId: str
    name: str
    md5ext:str # it is asset file path.
    dataFormat: str
    
    def __post_init__(self):
        self.pyresid = f"Asset_{randint(0, 2 << 31)}"
        self._fp = f"{AssetPath}\\{self.md5ext}"
        self.w, self.h = None, None
        self.scale = 1.0
        try:
            try:
                try:
                    self.data = Image.open(self._fp)
                    self.w, self.h = self.data.size
                except UnidentifiedImageError:
                    cairosvg.svg2png(url=self._fp, write_to=self._fp, scale=4)
                    self.data = Image.open(self._fp)
                    self.w, self.h = self.data.width / 4, self.data.height / 4
                    self.scale = 4.0
            except Exception:
                try:
                    tempfp = f"{AssetPath}\\pydub_{self.md5ext}.wav"
                    AudioSegment.from_file(self._fp).export(tempfp, format="wav")
                    with open(tempfp, "rb") as f:
                        self.data = f.read()
                except Exception as e:
                    print(f"Warning: Asset cannot load as image or sound, {self.md5ext}")
                    if isinstance(self, ScratchSound):
                        with open(self._fp, "rb") as f:
                            self.data = f.read()
                    elif isinstance(self, ScratchCostume):
                        self.data = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
                        self.w, self.h = self.data.size
        except Exception as e:
            print(f"Load asset error: {e}")
        
        Assets.append(self)

@dataclass
class ScratchCostume(ScratchAsset):
    bitmapResolution: int|float|None
    rotationCenterX: int|float
    rotationCenterY: int|float
    
@dataclass
class ScratchSound(ScratchAsset):
    rate: int|float
    sampleCount: int|float

@dataclass
class ScratchTarget:
    isStage: bool
    name: str
    variables: dict[str, ScratchVariable]
    lists: dict[str, ScratchList]
    broadcasts: dict[str, str]
    blocks: dict[str, ScratchCodeBlock]
    currentCostume: int
    costumes: list[ScratchCostume]
    sounds: list[ScratchSound]
    layerOrder: int
    volume: int|float
    
    # stage only
    tempo: int|float|None
    videoState: typing.Literal["on", "off", "on-flipped"]|None
    videoTransparency: int|float|None
    textToSpeechLanguage: str|None
    
    # sprite only
    visible: bool|None
    x: int|float|None
    y: int|float|None
    size: int|float|None
    direction: int|float|None
    draggable: bool|None
    rotationStyle: typing.Literal["all around", "left-right", "don't rotate"]|None
    
    def __post_init__(self):
        if self.isStage:
            global Stage
            Stage = self
        
        self.askans = ""
        self.timerst = time()
        self.timertime = 0.0
        self.timercallback: typing.Callable[[ScratchTarget], None] = lambda target: None
        self.isClone = False
        self.clones:list[ScratchTarget] = []
        
        Thread(target=self._timer, daemon=True).start()
    
    def ScratchEval(self, code:ScratchCodeBlock):
        match code.opcode:
            case "motion_xposition":
                return self.x
            case "motion_yposition":
                return self.y
            case "motion_direction":
                return self.direction
            case "looks_costumenumbername":
                if code.fields["NUMBER_NAME"][0] == "number":
                    return self.currentCostume + 1
                return self.costumes[self.currentCostume].name # name
            case "looks_backdropnumbername":
                if code.fields["NUMBER_NAME"][0] == "number":
                    return Stage.currentCostume + 1
                return Stage.costumes[Stage.currentCostume].name # name
            case "looks_size":
                return self.size
            case "sound_volume":
                return self.volume
            case "sensing_touchingobject":
                menuv = self.getInputValue(*code.inputs["TOUCHINGOBJECTMENU"])
                return ScratchEvalHelper(self, code, menuv=menuv)
            case "sensing_touchingcolor":
                color = ToolFuncs.unpack_color(self.getInputValue(*code.inputs["COLOR"]))
                return ScratchEvalHelper(self, code, color=color)
            case "sensing_coloristouchingcolor": ...
            case "sensing_distanceto": ...
            case "sensing_answer": 
                return self.askans
            case "sensing_keypressed": ...
            case "sensing_mousedown": ...
            case "sensing_mousex": ...
            case "sensing_mousey": ...
            case "sensing_loudness":
                return -1
            case "sensing_timer": 
                return time() - self.timerst
            case "sensing_of": ...
            case "sensing_current": ...
            case "sensing_dayssince2000":
                now = time() / 86400
                return now - 946684800
            case "sensing_username":
                return ""
            case "operator_add":
                n1 = self.getInputValue(*code.inputs["NUM1"])
                n2 = self.getInputValue(*code.inputs["NUM2"])
                return float(n1) + float(n2)
            case "operator_subtract":
                n1 = self.getInputValue(*code.inputs["NUM1"])
                n2 = self.getInputValue(*code.inputs["NUM2"])
                return float(n1) - float(n2)
            case "operator_multiply":
                n1 = self.getInputValue(*code.inputs["NUM1"])
                n2 = self.getInputValue(*code.inputs["NUM2"])
                return float(n1) * float(n2)
            case "operator_divide":
                n1 = self.getInputValue(*code.inputs["NUM1"])
                n2 = self.getInputValue(*code.inputs["NUM2"])
                try:
                    return float(n1) / float(n2)
                except ZeroDivisionError:
                    return float("inf")
            case "operator_random":
                f, t = self.getInputValue(*code.inputs["FROM"]), self.getInputValue(*code.inputs["TO"])
                f, t = float(f), float(t)
                return f + (t - f) * random()
            case "operator_gt":
                n1 = self.getInputValue(*code.inputs["OPERAND1"])
                n2 = self.getInputValue(*code.inputs["OPERAND2"])
                return float(n1) > float(n2)
            case "operator_lt":
                n1 = self.getInputValue(*code.inputs["OPERAND1"])
                n2 = self.getInputValue(*code.inputs["OPERAND2"])
                return float(n1) < float(n2)
            case "operator_equals":
                n1 = self.getInputValue(*code.inputs["OPERAND1"])
                n2 = self.getInputValue(*code.inputs["OPERAND2"])
                try:
                    return float(n1) == float(n2)
                except ValueError:
                    return str(n1) == str(n2)
            case "operator_and":
                v1 = self.getInputValue(*code.inputs["OPERAND1"])
                v2 = self.getInputValue(*code.inputs["OPERAND2"])
                return bool(v1) and bool(v2)
            case "operator_or":
                v1 = self.getInputValue(*code.inputs["OPERAND1"])
                v2 = self.getInputValue(*code.inputs["OPERAND2"])
                return bool(v1) or bool(v2)
            case "operator_not":
                return not self.getInputValue(*code.inputs["OPERAND"])
            case "operator_join":
                v1 = self.getInputValue(*code.inputs["STRING1"])
                v2 = self.getInputValue(*code.inputs["STRING2"])
                return str(v1) + str(v2)
            case "operator_letter_of":
                s = self.getInputValue(*code.inputs["STRING"])
                i = int(self.getInputValue(*code.inputs["LETTER"]))
                try:
                    if i - 1 >= 0:
                        return s[i - 1]
                    raise IndexError
                except IndexError:
                    return ""
            case "operator_length":
                return len(str(self.getInputValue(*code.inputs["STRING"])))
            case "operator_contains":
                m = self.getInputValue(*code.inputs["STRING1"])
                c = self.getInputValue(*code.inputs["STRING2"])
                return str(c) in str(m)
            case "operator_mod":
                n1 = self.getInputValue(*code.inputs["NUM1"])
                n2 = self.getInputValue(*code.inputs["NUM2"])
                try:
                    return float(n1) % float(n2)
                except ZeroDivisionError:
                    return float(n1)
            case "operator_round":
                n = str(self.getInputValue(*code.inputs["NUM"]))
                if "." not in n:
                    return int(n)
                s = n.split(".")[1]
                if not s:
                    return int(n)
                if int(s[0]) >= 5:
                    return int(n) + 1
                return int(n)
            case "operator_mathop":
                n = float(self.getInputValue(*code.inputs["NUM"]))
                try:
                    match code.fields["OPERATOR"][0]:
                        case "abs":
                            return abs(n)
                        case "floor":
                            return math.floor(n)
                        case "ceiling":
                            return math.ceil(n)
                        case "sqrt":
                            return math.sqrt(n)
                        case "sin":
                            return math.sin(math.radians(n))
                        case "cos":
                            return math.cos(math.radians(n))
                        case "tan":
                            return math.tan(math.radians(n))
                        case "asin":
                            return math.degrees(math.asin(n))
                        case "acos":
                            return math.degrees(math.acos(n))
                        case "atan":
                            return math.degrees(math.atan(n))
                        case "ln":
                            return math.log(n)
                        case "log":
                            return math.log10(n)
                        case "e ^":
                            return math.exp(n)
                        case "10 ^":
                            return math.pow(10, n)
                except Exception:
                    return 0.0
            case "data_variable":
                vn = code.params["VARIABLE"]
                gname = [i.name for i in Stage.variables.values()]
                lname = [i.name for i in self.variables.values()]
                if vn in gname:
                    e3 = list(Stage.variables.keys())[gname.index(vn)]
                elif vn in lname:
                    e3 = list(self.variables.keys())[lname.index(vn)]
                else:
                    return "0.0"
                return self.getInputValue(12, vn, e3)
            case "data_listcontents":
                vn = code.params["LIST"]
                gname = [Stage.lists[i].name for i in Stage.lists.keys()]
                lname = [self.lists[i].name for i in self.lists.keys()]
                if vn in gname:
                    e3 = list(Stage.lists.keys())[gname.index(vn)]
                elif vn in lname:
                    e3 = list(self.lists.keys())[lname.index(vn)]
                else:
                    return "0.0"
                return self.getInputValue(13, vn, e3)
            case "data_itemoflist":
                lid = code.fields["LIST"][1]
                pylist = self._get_listByid(lid).items
                i = int(self.getInputValue(*code.inputs["INDEX"]))
                try:
                    if i - 1 >= 0:
                        return pylist[i - 1]
                    raise IndexError
                except IndexError:
                    return ""
            case "data_itemnumoflist":
                lid = code.fields["LIST"][1]
                pylist = self._get_listByid(lid).items
                item = self.getInputValue(*code.inputs["ITEM"])
                try:
                    return pylist.index(item) + 1
                except ValueError:
                    return 0
            case "data_lengthoflist":
                lid = code.fields["LIST"][1]
                return len(self._get_listByid(lid).items)
            case "data_listcontainsitem":
                lid = code.fields["LIST"][1]
                pylist = self._get_listByid(lid).items
                item = self.getInputValue(*code.inputs["ITEM"])
                return item in pylist
            case "music_getTempo":
                return Stage.tempo
            case "motion_goto_menu":
                return code.fields["TO"][0]
            case "motion_glideto_menu":
                return code.fields["TO"][0]
            case "motion_pointtowards_menu":
                return code.fields["TOWARDS"][0]
            case "looks_costume":
                return code.fields["COSTUME"][0]
            case "looks_backdrops":
                return code.fields["BACKDROP"][0]
            case "sound_sounds_menu":
                return code.fields["SOUND_MENU"][0]
            case "event_whenkeypressed":
                return code.fields["KEY_OPTION"][0]
            case "event_whenbackdropswitchesto":
                return code.fields["BACKDROP"][0]
            case "event_whengreaterthan":
                return code.fields["WHENGREATERTHANMENU"][0]
            case "event_whenbroadcastreceived":
                return code.fields["BROADCAST_OPTION"][1]
            case "control_stop":
                return code.fields["STOP_OPTION"][0]
            case "control_create_clone_of_menu":
                return code.fields["CLONE_OPTION"][0]
            case "sensing_touchingobjectmenu":
                return code.fields["TOUCHINGOBJECTMENU"][0]
            case _:
                return "0.0"
    
    def _giv_run(self, value: str|list):
        if isinstance(value, str):
            return self.ScratchEval(self.blocks[value])
        return self.getInputValue(*value)
    
    def _giv_get(self, value: str|list):
        if isinstance(value, str):
            return self.blocks[value]
        return self._get_variableByid(value[2]).value # ele3
    
    def _get_variableByid(self, vid: str):
        try:
            return self.variables[vid]
        except KeyError:
            return Stage.variables[vid]
    
    def _get_listByid(self, lid: str):
        try:
            return self.lists[lid]
        except KeyError:
            return Stage.lists[lid]
    
    def getInputValue(self, itype: int, value: str|list, ele3 = None, ele4 = None, ele5 = None, r2c = True, *eles):
        match itype:
            case 1:
                if isinstance(value, str):
                    if r2c:
                        return self.ScratchEval(self.blocks[value])
                    return self.blocks[value]
                return self.getInputValue(*value)
            case 2:
                if r2c:
                    return self._giv_run(value)
                else:
                    return self.blocks[value]
            case 3:
                if r2c:
                    return self._giv_run(value)
                else:
                    return self.blocks[value]
            case 4|5|6|7|8:
                return float(value) if value else 0.0
            case 9|10:
                return value
            case 11:
                return ele3
            case 12:
                return self._get_variableByid(ele3).value
            case 13:
                return " ".join(map(str, self._get_listByid(ele3).items))
            case _:
                return "0.0"
    
    def _timer(self):
        while True:
            self.timertime = time() - self.timerst
            self.timercallback(self)
            sleep(1 / 30)
    
@dataclass
class ScratchProject:
    targets: list[ScratchTarget]

class ScratchContext:
    def __init__(self, target: ScratchTarget, master: ScratchCodeBlock, substack: str = "SUBSTACK") -> None:
        self.target = target
        self.master = master
        self.running = master
        self.substack = substack
        
    def __iter__(self):
        return self
    
    def __next__(self) -> ScratchCodeBlock|None:
        if self.running is self.master:
            self.running = self.target.getInputValue(*self.running.inputs[self.substack], r2c=False)
            if self.running is None:
                raise StopIteration
        else:
            if self.running.next:
                self.running = self.target.blocks[self.running.next]
            else:
                self.running = self.master
                raise StopIteration
        
        return self.running

@dataclass
class ScratchRuntimeStack:
    target: ScratchTarget
    stack_first: ScratchCodeBlock
    stack_id: str = ""
    stopped: bool = False
    
    def __post_init__(self):
        self.stack_id = f"RuntimeStack_{time() * randint(0, 2 << 31)}"

@dataclass
class ScratchRuntimeStackManager:
    stacks: list[ScratchRuntimeStack]

    def get_new(self, target: ScratchTarget, codeblock: ScratchCodeBlock) -> ScratchRuntimeStack:
        stack = ScratchRuntimeStack(target, codeblock)
        self.stacks.append(stack)
        return stack

    def destory_stack(self, stack: ScratchRuntimeStack):
        self.stacks.remove(stack)
    
    def get_stacks(self, target: ScratchTarget) -> list[ScratchRuntimeStack]:
        return [i for i in self.stacks if i.target is target]