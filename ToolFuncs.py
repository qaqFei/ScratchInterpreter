from os.path import exists, isfile, isdir
from ctypes import windll
from json import load
from threading import Thread
from math import radians, sin, cos
from time import time, sleep

import ScratchObjects

def exitProcess(state:int = 0):
    windll.kernel32.ExitProcess(state)

def isInvalidFile(fp:str):
    return exists(fp) and isfile(fp)

def isQfsiTempdir(td:str, dn:str):
    return dn.startswith("qfsi_tempdir_") and isdir(f"{td}\\{dn}")

def _loadSb3_loadVariables(variables:dict):
    return {
        k: ScratchObjects.ScratchVariable(
            name = v[0],
            value = v[1],
            cloud = v[2] if len(v) > 2 else False
        )
        for k, v in variables.items()
    }
    
def _loadSb3_loadLists(lists:dict):
    return {
        k: ScratchObjects.ScratchList(
            name = v[0],
            items = v[1]
        )
        for k, v in lists.items()
    }

def _loadSb3_loadCodeBlocks(codeBlocks:dict):
    for v in codeBlocks.values():
        if "mutation" in v:
            v.update(v["mutation"])
            del v["mutation"]
    return {
        k: ScratchObjects.ScratchCodeBlock(
            opcode = v.get("opcode", ""),
            params = v.get("params", {}),
            next = v.get("next", None),
            parent = v.get("parent", None),
            inputs = v.get("inputs", {}),
            fields = v.get("fields", {}),
            shadow = v.get("shadow", False),
            topLevel = v.get("topLevel", False),
            
            tagName = v.get("tagName", None),
            children = v.get("children", None),
            proccode = v.get("proccode", None),
            argumentids = v.get("argumentids", None),
            warp = v.get("warp", None),
            argumentnames = v.get("argumentnames", None),
            argumentdefaults = v.get("argumentdefaults", None),
            hasnext = v.get("hasnext", None)
        )
        for k, v in codeBlocks.items() if isinstance(v, dict)
    }

def _loadSb3_loadAssets(assets:list):
    r = []
    for i in assets:
        asset_kwargs = {
            "assetId": i.get("assetId", ""),
            "name": i.get("name", ""),
            "md5ext": i.get("md5ext", ""),
            "dataFormat": i.get("dataFormat", "")
        }
        if "rotationCenterX" in i and "rotationCenterY" in i:
            r.append(ScratchObjects.ScratchCostume(
                **asset_kwargs,
                bitmapResolution = i.get("bitmapResolution", 1.0),
                rotationCenterX = i.get("rotationCenterX", 0),
                rotationCenterY = i.get("rotationCenterY", 0)
            ))
        else:
            r.append(ScratchObjects.ScratchSound(
                **asset_kwargs,
                rate = i.get("rate", 0.0),
                sampleCount = i.get("sampleCount", 0.0)
            ))
    return r

def loadSb3(fp:str, AssetPath:str):
    with open(fp, "r", encoding="utf-8") as f:
        sb3_data:dict = load(f)
    
    ScratchObjects.AssetPath = AssetPath
    
    obj = ScratchObjects.ScratchProject(
        targets = [
            ScratchObjects.ScratchTarget(
                isStage = target_jsonitem.get("isStage", False),
                name = target_jsonitem.get("name", ""),
                variables = _loadSb3_loadVariables(target_jsonitem.get("variables", {})),
                lists = _loadSb3_loadLists(target_jsonitem.get("lists", {})),
                broadcasts = target_jsonitem.get("broadcasts", {}),
                blocks = _loadSb3_loadCodeBlocks(target_jsonitem.get("blocks", {})),
                currentCostume = target_jsonitem.get("currentCostume", 0),
                costumes = _loadSb3_loadAssets(target_jsonitem.get("costumes", [])),
                sounds = _loadSb3_loadAssets(target_jsonitem.get("sounds", [])),
                layerOrder = target_jsonitem.get("layerOrder", 0),
                volume = target_jsonitem.get("volume", 100),
                tempo = target_jsonitem.get("tempo", None),
                videoState = target_jsonitem.get("videoState", None),
                videoTransparency = target_jsonitem.get("videoTransparency", None),
                textToSpeechLanguage = target_jsonitem.get("textToSpeechLanguage", None),
                visible = target_jsonitem.get("visible", True),
                x = target_jsonitem.get("x", 0.0), y = target_jsonitem.get("y", 0.0),
                size = target_jsonitem.get("size", 100),
                direction = target_jsonitem.get("direction", 90),
                draggable = target_jsonitem.get("draggable", False),
                rotationStyle = target_jsonitem.get("rotationStyle", "all around")
            )
            for target_jsonitem in sb3_data.get("targets", [])
        ]
    )
    
    return obj

def ThreadFunc(f):
    def wrapper(*args, **kwargs):
        t = Thread(target=f, args=args, kwargs=kwargs)
        t.start()
        t.join()
    return wrapper

def rotate_point(x, y, deg, r):
    rad = radians(deg)
    xo = r * sin(rad)
    yo = r * cos(rad)
    return x + xo, y + yo

def unpack_color(color: str):
    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)
    return r, g, b

def rotate_point2(x, y, deg):
    c = cos(radians(deg))
    s = sin(radians(deg))
    matrix = [[c, -s], [s, c]]
    new_x = matrix[0][0] * x + matrix[0][1] * y
    new_y = matrix[1][0] * x + matrix[1][1] * y
    return new_x, new_y

def MessageBox(title: str, msg: str, flag: int):
    return windll.user32.MessageBoxW(None, msg, title, flag)

def MessageBoxTimeout(title: str, msg: str, flag: int, timeout: int = 0):
    dialogst = time()
    r = windll.user32.MessageBoxTimeoutW(None, msg, title, flag, 0, timeout)
    needwait = timeout / 1000 - (time() - dialogst)
    if needwait > 0.0:
        sleep(needwait)
    return r