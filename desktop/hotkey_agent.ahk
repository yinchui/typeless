#Requires AutoHotkey v2.0
#SingleInstance Force
#Warn

global baseUrl := "http://127.0.0.1:8775"
global defaultMode := "cloud"

global recordingStarted := false
global currentSessionId := ""
global targetWindowId := 0
global toggleBusy := false
global pausePlaybackDuringRecording := true
global playbackPauseToggledForRecording := false
global waveformGui := 0
global waveformBars := []
global waveformTimerMs := 70
global runtimeDir := A_ScriptDir . "\..\service\runtime"
global logFile := runtimeDir . "\hotkey.log"

global settingsGui := 0
global settingsStatusText := 0
global settingsApiKeyEdit := 0
global settingsModeDDL := 0

InstallKeybdHook()
TraySetIcon("shell32.dll", 44)
EnsureRuntimeDir()
InitWaveformGui()
InitTrayMenu()
SyncModeFromServer()
TrayTip("Voice Text Organizer", "Hotkey agent started. Press Alt+Space to start/stop recording.", 2)
LogLine("agent started")

!Space::
{
    ; Run only after modifiers are released to avoid menu/accelerator interference.
    KeyWait("Space")
    KeyWait("Alt")
    ToggleRecordingByHotkey()
}

ToggleRecordingByHotkey()
{
    global toggleBusy
    if (toggleBusy)
    {
        LogLine("toggle ignored: request is busy")
        return
    }

    toggleBusy := true
    try
    {
        if (HasActiveRecording())
            StopRecordingSession()
        else
            StartRecordingSession()
    }
    finally
    {
        toggleBusy := false
    }
}

HasActiveRecording()
{
    global recordingStarted, currentSessionId
    return recordingStarted && currentSessionId != ""
}

StartRecordingSession()
{
    global recordingStarted, currentSessionId, targetWindowId
    try
    {
        PausePlaybackForRecording()
        targetWindowId := WinExist("A")
        selectedText := GetSelectedTextSafe()
        sessionId := ApiStartRecord(selectedText)
        if (sessionId = "")
        {
            TrayTip("Voice Text Organizer", "Could not start recording.", 2)
            LogLine("start returned empty session id")
            return
        }

        currentSessionId := sessionId
        recordingStarted := true
        ShowWaveformIndicator()
        TrayTip("Voice Text Organizer", "Recording started. Press Alt+Space again to stop.", 1)
        LogLine("start ok, session=" . sessionId . ", targetWindowId=" . targetWindowId)
    }
    catch Error as err
    {
        ResumePlaybackAfterRecording()
        HideWaveformIndicator()
        TrayTip("Voice Text Organizer", "Start failed: " err.Message, 3)
        LogLine("start failed: " . err.Message)
    }
}

StopRecordingSession()
{
    global recordingStarted, currentSessionId, targetWindowId
    if (!HasActiveRecording())
    {
        LogLine("stop ignored: no active recording")
        return
    }

    LogLine("stop requested, session=" . currentSessionId)
    try
    {
        result := ApiStopRecord(currentSessionId)
        finalText := result["final_text"]
        LogLine("stop ok, final length=" . StrLen(finalText))
        if (finalText = "")
        {
            TrayTip("Voice Text Organizer", "No final text returned.", 2)
            LogLine("stop returned empty final text")
            return
        }
        InsertText(finalText)
    }
    catch Error as err
    {
        TrayTip("Voice Text Organizer", "Stop failed: " err.Message, 3)
        LogLine("stop failed: " . err.Message)
    }
    finally
    {
        ResumePlaybackAfterRecording()
        HideWaveformIndicator()
        recordingStarted := false
        currentSessionId := ""
        targetWindowId := 0
    }
}

PausePlaybackForRecording()
{
    global pausePlaybackDuringRecording, playbackPauseToggledForRecording
    if (!pausePlaybackDuringRecording || playbackPauseToggledForRecording)
        return

    try
    {
        ; Global media key pause, works for most media players (e.g. NetEase Cloud Music).
        Send("{Media_Play_Pause}")
        playbackPauseToggledForRecording := true
        LogLine("playback paused for recording (media key)")
    }
    catch Error as err
    {
        LogLine("failed to pause playback: " . err.Message)
    }
}

ResumePlaybackAfterRecording()
{
    global pausePlaybackDuringRecording, playbackPauseToggledForRecording
    if (!pausePlaybackDuringRecording || !playbackPauseToggledForRecording)
        return

    try
    {
        Send("{Media_Play_Pause}")
        LogLine("playback resumed after recording (media key)")
    }
    catch Error as err
    {
        LogLine("failed to resume playback: " . err.Message)
    }
    finally
    {
        playbackPauseToggledForRecording := false
    }
}

InitWaveformGui()
{
    global waveformGui, waveformBars
    if (IsObject(waveformGui))
        return

    waveformGui := Gui("-Caption +ToolWindow +AlwaysOnTop +E0x20")
    waveformGui.MarginX := 10
    waveformGui.MarginY := 10
    waveformGui.BackColor := "1D1D1D"

    waveformBars := []
    Loop 16
    {
        opts := (A_Index = 1 ? "x0 y0 " : "x+4 yp ")
        opts .= "w6 h30 +Vertical Background303030 c00D7FF Range0-100"
        bar := waveformGui.AddProgress(opts, 10)
        waveformBars.Push(bar)
    }

    waveformGui.Show("AutoSize Hide")
}

ShowWaveformIndicator()
{
    global waveformGui, waveformTimerMs
    InitWaveformGui()

    width := 0
    height := 0
    waveformGui.GetPos(, , &width, &height)
    x := Floor((A_ScreenWidth - width) / 2)
    y := A_ScreenHeight - height - 52

    waveformGui.Show("NA x" . x . " y" . y)
    SetTimer(UpdateWaveformIndicator, waveformTimerMs)
}

HideWaveformIndicator()
{
    global waveformGui
    SetTimer(UpdateWaveformIndicator, 0)
    if (IsObject(waveformGui))
        waveformGui.Hide()
}

UpdateWaveformIndicator()
{
    global waveformBars
    if (!IsObject(waveformBars) || waveformBars.Length = 0)
        return

    center := (waveformBars.Length + 1) / 2
    Loop waveformBars.Length
    {
        distance := Abs(A_Index - center)
        base := Round(78 - distance * 8)
        jitter := Random(-28, 22)
        value := base + jitter
        if (value < 8)
            value := 8
        if (value > 100)
            value := 100
        waveformBars[A_Index].Value := value
    }
}

InitTrayMenu()
{
    A_TrayMenu.Delete()
    A_TrayMenu.Add("Settings", OpenSettingsDialog)
    A_TrayMenu.Add("Open Logs Folder", OpenLogsFolder)
    A_TrayMenu.Add()
    A_TrayMenu.Add("Exit", ExitAgent)
}

OpenLogsFolder(*)
{
    global runtimeDir
    EnsureRuntimeDir()
    Run(runtimeDir)
}

ExitAgent(*)
{
    ResumePlaybackAfterRecording()
    HideWaveformIndicator()
    ExitApp()
}

SyncModeFromServer()
{
    global defaultMode
    try
    {
        current := ApiGetSettings()
        if (current.Has("default_mode") && current["default_mode"] != "")
            defaultMode := current["default_mode"]
    }
    catch
    {
        return
    }
}

OpenSettingsDialog(*)
{
    global settingsGui, settingsStatusText, settingsApiKeyEdit, settingsModeDDL
    EnsureSettingsGui()

    try
    {
        current := ApiGetSettings()
    }
    catch Error as err
    {
        MsgBox("Failed to load settings: " err.Message, "Voice Text Organizer", "Iconx")
        return
    }

    status := current["api_key_configured"] ? "Configured " . current["api_key_masked"] : "Not configured"
    settingsStatusText.Value := status
    settingsApiKeyEdit.Value := ""
    if (current["default_mode"] = "local")
        settingsModeDDL.Choose(2)
    else
        settingsModeDDL.Choose(1)

    settingsGui.Show("AutoSize")
}

EnsureSettingsGui()
{
    global settingsGui, settingsStatusText, settingsApiKeyEdit, settingsModeDDL
    if (IsObject(settingsGui))
        return

    settingsGui := Gui("+AlwaysOnTop", "Voice Text Organizer - Settings")
    settingsGui.SetFont("s10", "Segoe UI")

    settingsGui.AddText("xm ym", "API Key status")
    settingsStatusText := settingsGui.AddText("xm w420", "Loading...")

    settingsGui.AddText("xm y+12", "API Key (leave empty to keep unchanged)")
    settingsApiKeyEdit := settingsGui.AddEdit("xm w420 Password")

    settingsGui.AddText("xm y+12", "Default mode")
    settingsModeDDL := settingsGui.AddDropDownList("xm w140", ["cloud", "local"])

    saveBtn := settingsGui.AddButton("xm y+18 w90", "Save")
    cancelBtn := settingsGui.AddButton("x+10 yp w90", "Cancel")

    saveBtn.OnEvent("Click", SaveSettingsFromDialog)
    cancelBtn.OnEvent("Click", HideSettingsDialog)
    settingsGui.OnEvent("Close", HideSettingsDialog)
}

SaveSettingsFromDialog(*)
{
    global defaultMode, settingsGui, settingsStatusText, settingsApiKeyEdit, settingsModeDDL

    apiKey := Trim(settingsApiKeyEdit.Value)
    mode := settingsModeDDL.Text
    if (mode = "")
        mode := "cloud"

    try
    {
        updated := ApiUpdateSettings(apiKey, mode)
    }
    catch Error as err
    {
        MsgBox("Save failed: " err.Message, "Voice Text Organizer", "Iconx")
        return
    }

    defaultMode := updated["default_mode"]
    status := updated["api_key_configured"] ? "Configured " . updated["api_key_masked"] : "Not configured"
    settingsStatusText.Value := status
    settingsApiKeyEdit.Value := ""
    settingsGui.Hide()
    TrayTip("Voice Text Organizer", "Settings saved and applied.", 2)
}

HideSettingsDialog(*)
{
    global settingsGui
    if (IsObject(settingsGui))
        settingsGui.Hide()
}

GetSelectedTextSafe()
{
    clipSaved := ClipboardAll()
    selected := ""
    try
    {
        A_Clipboard := ""
        Send("^c")
        if (ClipWait(0.2))
            selected := A_Clipboard
    }
    finally
    {
        A_Clipboard := clipSaved
    }
    return selected
}

InsertText(text)
{
    global targetWindowId

    if (targetWindowId && WinExist("ahk_id " . targetWindowId))
    {
        WinActivate("ahk_id " . targetWindowId)
        WinWaitActive("ahk_id " . targetWindowId, , 1)
    }

    ; Give the foreground app a brief moment to regain focus after hotkey release.
    Sleep(80)

    clipSaved := ClipboardAll()
    try
    {
        activeExe := ""
        activeClass := ""
        try
            activeExe := WinGetProcessName("A")
        try
            activeClass := WinGetClass("A")

        A_Clipboard := text
        ClipWait(0.5)
        Sleep(80)
        if (activeExe = "WindowsTerminal.exe")
            Send("^+v")
        else if (activeClass = "ConsoleWindowClass")
            Send("+{Insert}")
        else
            Send("^v")
        Sleep(160)
        LogLine(
            "insert via clipboard paste, length=" . StrLen(text)
            . ", exe=" . activeExe
            . ", class=" . activeClass
        )
    }
    catch
    {
        ; Fall back to direct text injection if paste path is unavailable.
        try
        {
            SendText(text)
            LogLine("insert via SendText fallback, length=" . StrLen(text))
        }
        catch Error as err
        {
            LogLine("insert failed: " . err.Message)
            throw err
        }
    }
    finally
    {
        A_Clipboard := clipSaved
    }
}

ApiStartRecord(selectedText)
{
    q := Chr(34)
    payload := "{" . q . "selected_text" . q . ":" . q . JsonEscape(selectedText) . q . "}"
    response := HttpPost("/v1/record/start", payload)
    return ExtractJsonString(response, "session_id")
}

ApiStopRecord(sessionId)
{
    global defaultMode
    q := Chr(34)
    payload := "{" . q . "session_id" . q . ":" . q . JsonEscape(sessionId) . q
    payload .= "," . q . "mode" . q . ":" . q . JsonEscape(defaultMode) . q . "}"
    response := HttpPost("/v1/record/stop", payload)

    result := Map()
    result["voice_text"] := ExtractJsonString(response, "voice_text")
    result["final_text"] := ExtractJsonString(response, "final_text")
    return result
}

ApiGetSettings()
{
    response := HttpGet("/v1/settings")
    return ParseSettingsResponse(response)
}

ApiUpdateSettings(apiKey, mode)
{
    q := Chr(34)
    payload := "{" . q . "default_mode" . q . ":" . q . JsonEscape(mode) . q
    if (apiKey != "")
        payload .= "," . q . "api_key" . q . ":" . q . JsonEscape(apiKey) . q
    payload .= "}"
    response := HttpPut("/v1/settings", payload)
    return ParseSettingsResponse(response)
}

ParseSettingsResponse(response)
{
    result := Map()
    result["default_mode"] := ExtractJsonString(response, "default_mode")
    result["api_key_masked"] := ExtractJsonString(response, "api_key_masked")
    result["api_key_configured"] := ExtractJsonBool(response, "api_key_configured")
    return result
}

HttpGet(endpoint)
{
    return HttpRequest("GET", endpoint)
}

HttpPost(endpoint, body)
{
    return HttpRequest("POST", endpoint, body)
}

HttpPut(endpoint, body)
{
    return HttpRequest("PUT", endpoint, body)
}

HttpRequest(method, endpoint, body := "", allowRetry := true)
{
    global baseUrl
    req := ComObject("WinHttp.WinHttpRequest.5.1")
    try
    {
        req.Open(method, baseUrl endpoint, false)
        if (method = "POST" || method = "PUT")
            req.SetRequestHeader("Content-Type", "application/json; charset=utf-8")
        req.Send(body)
    }
    catch Error as err
    {
        if (allowRetry && TryStartBackend())
            return HttpRequest(method, endpoint, body, false)
        throw Error("Cannot connect to backend: " err.Message)
    }

    responseText := GetUtf8ResponseText(req)
    if (req.Status < 200 || req.Status >= 300)
        throw Error("HTTP " req.Status " " responseText)
    return responseText
}

TryStartBackend()
{
    serviceScript := A_ScriptDir . "\..\scripts\run-service.ps1"
    if !FileExist(serviceScript)
    {
        LogLine("backend start skipped: missing script " . serviceScript)
        return false
    }

    quoted := Chr(34) . serviceScript . Chr(34)
    LogLine("starting backend via " . serviceScript)
    Run("powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File " . quoted,, "Hide")
    return WaitBackendReady(15000)
}

WaitBackendReady(timeoutMs := 6000)
{
    global baseUrl
    startTick := A_TickCount
    Loop
    {
        req := ComObject("WinHttp.WinHttpRequest.5.1")
        try
        {
            req.Open("GET", baseUrl . "/health", false)
            req.Send()
            if (req.Status = 200)
                return true
        }
        catch
        {
            ; keep waiting
        }

        if ((A_TickCount - startTick) >= timeoutMs)
            return false
        Sleep(250)
    }
}

GetUtf8ResponseText(req)
{
    stream := ComObject("ADODB.Stream")
    stream.Type := 1  ; binary
    stream.Open()
    stream.Write(req.ResponseBody)
    stream.Position := 0
    stream.Type := 2  ; text
    stream.Charset := "utf-8"
    text := stream.ReadText()
    stream.Close()
    return text
}

LogLine(message)
{
    global logFile
    try
    {
        FileAppend(FormatTime(, "yyyy-MM-dd HH:mm:ss") . " " . message . "`n", logFile, "UTF-8")
    }
}

EnsureRuntimeDir()
{
    global runtimeDir
    try
    {
        DirCreate(runtimeDir)
    }
}

ExtractJsonString(json, key)
{
    q := Chr(34)
    pattern := q . key . q . "\s*:\s*" . q . "((?:\\.|[^" . q . "\\])*)" . q
    if !RegExMatch(json, pattern, &m)
        return ""

    val := m[1]
    val := StrReplace(val, "\\n", "`n")
    val := StrReplace(val, "\\r", "`r")
    val := StrReplace(val, "\\t", "`t")
    val := StrReplace(val, "\\" . Chr(34), Chr(34))
    val := StrReplace(val, "\\\\", Chr(92))
    return val
}

ExtractJsonBool(json, key)
{
    q := Chr(34)
    pattern := q . key . q . "\s*:\s*(true|false)"
    if !RegExMatch(json, pattern, &m)
        return false
    return (m[1] = "true")
}

JsonEscape(text)
{
    text := StrReplace(text, Chr(92), "\\")
    text := StrReplace(text, Chr(34), Chr(92) . Chr(34))
    text := StrReplace(text, "`r", "")
    text := StrReplace(text, "`n", "\n")
    return text
}
