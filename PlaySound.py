from struct import unpack
from threading import Thread
from ctypes import windll

from pywintypes import WAVEFORMATEX
from win32comext.directsound.directsound import DirectSoundCreate,DSBUFFERDESC,IID_IDirectSoundNotify
from win32event import CreateEvent,WaitForSingleObject

from functools import cache

@cache
def _wav_header_unpack(data):
    (
        format,
        nchannels,
        samplespersecond,
        datarate,
        blockalign,
        bitspersample,
        data,
        datalength
    ) = unpack("<4sl4s4slhhllhh4sl", data)[5:]
    wfx = WAVEFORMATEX()
    wfx.wFormatTag = format
    wfx.nChannels = nchannels
    wfx.nSamplesPerSec = samplespersecond
    wfx.nAvgBytesPerSec = datarate
    wfx.nBlockAlign = blockalign
    wfx.wBitsPerSample = bitspersample
    return datalength, wfx

def Play(data:bytes):
    hdr = data[0:44]

    sdesc = DSBUFFERDESC()
    sdesc.dwBufferBytes,sdesc.lpwfxFormat = _wav_header_unpack(hdr)
    sdesc.dwFlags=16640

    DirectSound = DirectSoundCreate(None, None)
    DirectSound.SetCooperativeLevel(None, 2)
    event = CreateEvent(None, 0, 0, None)

    buffer = DirectSound.CreateSoundBuffer(sdesc, None)
    buffer.QueryInterface(IID_IDirectSoundNotify).SetNotificationPositions((-1, event))
    buffer.Update(0, data[44:])
    buffer.Play(0)
    waitt = Thread(target=WaitForSingleObject, args=(event, -1), daemon=True)
    waitt.start()
    return buffer, waitt

def setVolume(volume:float):
    "volume: 0.0-1.0"
    windll.winmm.waveOutSetVolume(None, int(volume * ((2 << 15) - 1)))