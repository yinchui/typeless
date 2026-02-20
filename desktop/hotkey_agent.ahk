#Requires AutoHotkey v2.0
#SingleInstance Force
#Warn

global baseUrl := "http://127.0.0.1:8775"
global defaultMode := "cloud"
global defaultLanguageHint := "zh"
global httpResolveTimeoutMs := 10000
global httpConnectTimeoutMs := 10000
global httpSendTimeoutMs := 120000
global httpReceiveTimeoutMs := 600000

global recordingStarted := false
global currentSessionId := ""
global targetWindowId := 0
global replaceSelectionOnInsert := false
global toggleBusy := false
global pausePlaybackDuringRecording := true
global playbackPauseToggledForRecording := false
global waveformGui := 0
global waveformBars := []
global waveformTimerMs := 70
global runtimeDir := EnvGet("VTO_RUNTIME_DIR")
if (runtimeDir = "")
{
    SplitPath(A_ScriptDir, &scriptDirName)
    if (StrLower(scriptDirName) = "desktop")
        runtimeDir := A_ScriptDir . "\..\runtime"
    else
        runtimeDir := A_ScriptDir . "\runtime"
}
if (runtimeDir != "")
{
    EnvSet("VTO_RUNTIME_DIR", runtimeDir)
}
global logFile := runtimeDir . "\hotkey.log"

global settingsGui := 0
global settingsStatusText := 0
global settingsApiKeyEdit := 0
global settingsModeDDL := 0
global settingsPersonalizedCheck := 0
global personalizedAcousticEnabled := true

global dashboardGui := 0
global dashboardMainBg := 0
global dashboardHomeControls := []
global dashboardDictControls := []
global dashboardNavHome := 0
global dashboardNavDict := 0
global dashboardMetricPersonality := 0
global dashboardMetricTotalTime := 0
global dashboardMetricChars := 0
global dashboardMetricSaved := 0
global dashboardMetricSpeed := 0
global dashboardDictSearch := 0
global dashboardDictList := 0
global dashboardDictDeleteBtn := 0
global dashboardDictSamplesBtn := 0
global dashboardWordEntries := []
global dashboardRecordingStartTick := 0
global dashboardTotalSeconds := 0
global dashboardTotalChars := 0
global dashboardAvgCharsPerMinute := 0
global dashboardSavedSeconds := 0
global dashboardProfileScore := 0
global dashboardUpdateLink := 0
global appReleaseUrl := "https://github.com/yinchui/typeless/releases"
global latestReleaseVersion := ""
global latestUpdateCheckAt := ""
global hasAppUpdate := false
global updateTipShownVersion := ""

global termSampleGui := 0
global termSampleTermText := 0
global termSampleStatusText := 0
global termSampleList := 0
global termSampleStartBtn := 0
global termSampleDeleteBtn := 0
global termSamplePlayBtn := 0
global termSampleCurrentTerm := ""
global termSampleRecordingSessionId := ""
global termSampleRecordingTerm := ""
global termSampleBusy := false

InstallKeybdHook()
TraySetIcon("shell32.dll", 44)
EnsureRuntimeDir()
InitWaveformGui()
InitTrayMenu()
SyncModeFromServer()
CheckForAppUpdate()
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
    global recordingStarted, currentSessionId, targetWindowId, replaceSelectionOnInsert, dashboardRecordingStartTick
    try
    {
        PausePlaybackForRecording()
        targetWindowId := WinExist("A")
        selectedText := GetSelectedTextSafe()
        replaceSelectionOnInsert := (selectedText != "")
        ; Keep caret stable for in-place insertion. Full-text probing uses Ctrl+A and can move caret.
        existingText := ""
        sessionId := ApiStartRecord(selectedText, existingText)
        if (sessionId = "")
        {
            TrayTip("Voice Text Organizer", "Could not start recording.", 2)
            LogLine("start returned empty session id")
            return
        }

        currentSessionId := sessionId
        recordingStarted := true
        dashboardRecordingStartTick := A_TickCount
        ShowWaveformIndicator()
        LogLine(
            "start ok, session=" . sessionId
            . ", targetWindowId=" . targetWindowId
            . ", replaceSelectionOnInsert=" . (replaceSelectionOnInsert ? "true" : "false")
        )
    }
    catch Error as err
    {
        replaceSelectionOnInsert := false
        dashboardRecordingStartTick := 0
        ResumePlaybackAfterRecording()
        HideWaveformIndicator()
        TrayTip("Voice Text Organizer", "Start failed: " err.Message, 3)
        LogLine("start failed: " . err.Message)
    }
}

StopRecordingSession()
{
    global recordingStarted, currentSessionId, targetWindowId, replaceSelectionOnInsert
    if (!HasActiveRecording())
    {
        LogLine("stop ignored: no active recording")
        return
    }

    LogLine("stop requested, session=" . currentSessionId)
    try
    {
        result := ApiStopRecord(currentSessionId)
        finalText := NormalizeOutputText(result["final_text"])
        LogLine("stop ok, final length=" . StrLen(finalText))
        if (finalText = "")
        {
            TrayTip("Voice Text Organizer", "No final text returned.", 2)
            LogLine("stop returned empty final text")
            return
        }
        InsertText(finalText, replaceSelectionOnInsert)
        LoadDashboardDataFromServer()
        RefreshDashboardHomeMetrics()
        RefreshDashboardDictionaryList()
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
        replaceSelectionOnInsert := false
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

    waveformGui := Gui("-Caption +ToolWindow +AlwaysOnTop +E0x20 +E0x08000000")
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
    A_TrayMenu.Add("Open Dashboard", OpenDashboard)
    A_TrayMenu.Add("Settings", OpenSettingsDialog)
    A_TrayMenu.Add("Open Logs Folder", OpenLogsFolder)
    A_TrayMenu.Add()
    A_TrayMenu.Add("Exit", ExitAgent)
    A_TrayMenu.Default := "Open Dashboard"
    A_TrayMenu.ClickCount := 1
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
    HideDashboard()
    ExitApp()
}

SyncModeFromServer()
{
    global defaultMode, personalizedAcousticEnabled
    try
    {
        current := ApiGetSettings()
        if (current.Has("default_mode") && current["default_mode"] != "")
            defaultMode := current["default_mode"]
        if (current.Has("personalized_acoustic_enabled"))
            personalizedAcousticEnabled := current["personalized_acoustic_enabled"]
    }
    catch
    {
        return
    }
}

CheckForAppUpdate()
{
    global latestReleaseVersion, latestUpdateCheckAt, appReleaseUrl, hasAppUpdate, updateTipShownVersion
    try
    {
        info := ApiGetAppVersion()
        latestReleaseVersion := info["latest_version"]
        latestUpdateCheckAt := info["checked_at"]
        appReleaseUrl := info["release_url"]
        hasAppUpdate := info["has_update"]

        if (hasAppUpdate && latestReleaseVersion != "" && updateTipShownVersion != latestReleaseVersion)
        {
            updateTipShownVersion := latestReleaseVersion
            TrayTip("Voice Text Organizer", "New version found: v" . latestReleaseVersion, 3)
            LogLine("update available: " . latestReleaseVersion . ", url=" . appReleaseUrl)
        }
    }
    catch Error as err
    {
        LogLine("update check failed: " . err.Message)
    }
}

RefreshDashboardUpdateLink()
{
    global dashboardUpdateLink, hasAppUpdate, latestReleaseVersion
    if (!IsObject(dashboardUpdateLink))
        return

    if (hasAppUpdate && latestReleaseVersion != "")
    {
        dashboardUpdateLink.Value := "发现新版本 v" . latestReleaseVersion
        dashboardUpdateLink.Visible := true
    }
    else
    {
        dashboardUpdateLink.Value := ""
        dashboardUpdateLink.Visible := false
    }
}

OnDashboardUpdateLinkClick(*)
{
    global appReleaseUrl
    if (appReleaseUrl = "")
        appReleaseUrl := "https://github.com/yinchui/typeless/releases"
    Run(appReleaseUrl)
}

OpenSettingsDialog(*)
{
    global settingsGui, settingsStatusText, settingsApiKeyEdit, settingsModeDDL, settingsPersonalizedCheck
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
    settingsPersonalizedCheck.Value := current["personalized_acoustic_enabled"] ? 1 : 0

    settingsGui.Show("AutoSize")
}

EnsureSettingsGui()
{
    global settingsGui, settingsStatusText, settingsApiKeyEdit, settingsModeDDL, settingsPersonalizedCheck
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

    settingsPersonalizedCheck := settingsGui.AddCheckBox("xm y+12", "Enable personalized acoustic enhancement")
    settingsPersonalizedCheck.Value := 1

    saveBtn := settingsGui.AddButton("xm y+18 w90", "Save")
    cancelBtn := settingsGui.AddButton("x+10 yp w90", "Cancel")

    saveBtn.OnEvent("Click", SaveSettingsFromDialog)
    cancelBtn.OnEvent("Click", HideSettingsDialog)
    settingsGui.OnEvent("Close", HideSettingsDialog)
}

SaveSettingsFromDialog(*)
{
    global defaultMode, personalizedAcousticEnabled
    global settingsGui, settingsStatusText, settingsApiKeyEdit, settingsModeDDL, settingsPersonalizedCheck

    apiKey := Trim(settingsApiKeyEdit.Value)
    mode := settingsModeDDL.Text
    if (mode = "")
        mode := "cloud"
    personalizedEnabled := settingsPersonalizedCheck.Value = 1

    try
    {
        updated := ApiUpdateSettings(apiKey, mode, personalizedEnabled)
    }
    catch Error as err
    {
        MsgBox("Save failed: " err.Message, "Voice Text Organizer", "Iconx")
        return
    }

    defaultMode := updated["default_mode"]
    personalizedAcousticEnabled := updated["personalized_acoustic_enabled"]
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

OpenDashboard(*)
{
    EnsureDashboardGui()
    CheckForAppUpdate()
    LoadDashboardDataFromServer()
    RefreshDashboardHomeMetrics()
    RefreshDashboardDictionaryList()
    RefreshDashboardUpdateLink()
    dashboardGui.Show("w1420 h900 Center")
}

HideDashboard(*)
{
    global dashboardGui
    if (IsObject(dashboardGui))
        dashboardGui.Hide()
}

EnsureDashboardGui()
{
    global dashboardGui, dashboardMainBg
    global dashboardHomeControls, dashboardDictControls
    global dashboardNavHome, dashboardNavDict
    global dashboardMetricPersonality, dashboardMetricTotalTime, dashboardMetricChars
    global dashboardMetricSaved, dashboardMetricSpeed
    global dashboardDictSearch, dashboardDictList, dashboardDictDeleteBtn, dashboardDictSamplesBtn
    global dashboardUpdateLink

    if (IsObject(dashboardGui))
        return

    dashboardHomeControls := []
    dashboardDictControls := []

    dashboardGui := Gui("+MinSize1200x760 -MaximizeBox", "Voice Text Organizer")
    dashboardGui.SetFont("s10", "Microsoft YaHei UI")
    dashboardGui.BackColor := "ECECED"
    dashboardGui.MarginX := 0
    dashboardGui.MarginY := 0

    dashboardGui.AddText("x14 y14 w246 h868 BackgroundF1F1F2")
    brand := dashboardGui.AddText("x40 y52 w132 h30 c111111 +BackgroundTrans", "Typeless")
    brand.SetFont("s18 w700")
    tag := dashboardGui.AddText("x176 y54 w84 h28 +0x200 +Center BackgroundDCE6FF c2C4EAA", "Pro Trial")
    tag.SetFont("s10 w600")

    dashboardNavHome := dashboardGui.AddText("x28 y132 w216 h42 +0x100 +0x200 BackgroundE4E4E6 c111111", "  首页")
    dashboardNavDict := dashboardGui.AddText("x28 y182 w216 h42 +0x100 +0x200 BackgroundF1F1F2 c666666", "  词典")
    dashboardNavHome.SetFont("s11 w600")
    dashboardNavDict.SetFont("s11 w600")
    dashboardNavHome.OnEvent("Click", OnDashboardNavHomeClick)
    dashboardNavDict.OnEvent("Click", OnDashboardNavDictClick)

    sideSettings := dashboardGui.AddText("x28 y828 w102 h34 +0x100 +0x200 +Center BackgroundFFFFFF c2E2E2E", "设置")
    sideLogs := dashboardGui.AddText("x142 y828 w102 h34 +0x100 +0x200 +Center BackgroundFFFFFF c2E2E2E", "日志")
    sideSettings.SetFont("s10 w600")
    sideLogs.SetFont("s10 w600")
    sideSettings.OnEvent("Click", OpenSettingsDialog)
    sideLogs.OnEvent("Click", OpenLogsFolder)

    dashboardMainBg := dashboardGui.AddText("x274 y14 w1132 h868 BackgroundF8F8F9")

    homeTitle := dashboardGui.AddText("x306 y60 w860 h42 c111111 +BackgroundTrans", "自然说话，完美书写 - 在任何应用中")
    homeTitle.SetFont("s26 w700")
    AddDashboardControl("home", homeTitle)

    homeSubTitle := dashboardGui.AddText("x306 y106 w760 h24 c666666 +BackgroundTrans", "Press Alt + Space to start/stop recording and insert text.")
    homeSubTitle.SetFont("s11")
    AddDashboardControl("home", homeSubTitle)

    dashboardUpdateLink := dashboardGui.AddText("x1128 y106 w230 h24 c2C4EAA +BackgroundTrans +0x100 +Right", "")
    dashboardUpdateLink.SetFont("s10 w600 underline")
    dashboardUpdateLink.OnEvent("Click", OnDashboardUpdateLinkClick)
    AddDashboardControl("home", dashboardUpdateLink)

    homeStatsWrap := dashboardGui.AddText("x302 y146 w1076 h258 BackgroundF0F0F1")
    AddDashboardControl("home", homeStatsWrap)

    leftCard := dashboardGui.AddText("x322 y166 w536 h218 BackgroundFFFFFF")
    AddDashboardControl("home", leftCard)
    dashboardMetricPersonality := dashboardGui.AddText("x350 y196 w140 h56 c111111 +BackgroundTrans", "0%")
    dashboardMetricPersonality.SetFont("s40 w700")
    AddDashboardControl("home", dashboardMetricPersonality)
    leftLabel := dashboardGui.AddText("x350 y260 w220 h24 c6D6D6D +BackgroundTrans", "鏁翠綋涓€у寲")
    leftLabel.SetFont("s14")
    AddDashboardControl("home", leftLabel)

    cardTimeBg := dashboardGui.AddText("x876 y166 w240 h104 BackgroundFFFFFF")
    AddDashboardControl("home", cardTimeBg)
    dashboardMetricTotalTime := dashboardGui.AddText("x896 y186 w220 h36 c161616 +BackgroundTrans", "0 min")
    dashboardMetricTotalTime.SetFont("s22 w700")
    AddDashboardControl("home", dashboardMetricTotalTime)
    cardTimeLabel := dashboardGui.AddText("x896 y226 w220 h22 c666666 +BackgroundTrans", "Total recording time")
    cardTimeLabel.SetFont("s11")
    AddDashboardControl("home", cardTimeLabel)

    cardCharsBg := dashboardGui.AddText("x1124 y166 w240 h104 BackgroundFFFFFF")
    AddDashboardControl("home", cardCharsBg)
    dashboardMetricChars := dashboardGui.AddText("x1144 y186 w210 h36 c161616 +BackgroundTrans", "0 chars")
    dashboardMetricChars.SetFont("s22 w700")
    AddDashboardControl("home", dashboardMetricChars)
    cardCharsLabel := dashboardGui.AddText("x1144 y226 w210 h22 c666666 +BackgroundTrans", "口述字数")
    cardCharsLabel.SetFont("s11")
    AddDashboardControl("home", cardCharsLabel)

    cardSavedBg := dashboardGui.AddText("x876 y280 w240 h104 BackgroundFFFFFF")
    AddDashboardControl("home", cardSavedBg)
    dashboardMetricSaved := dashboardGui.AddText("x896 y300 w220 h34 c161616 +BackgroundTrans", "0 min")
    dashboardMetricSaved.SetFont("s20 w700")
    AddDashboardControl("home", dashboardMetricSaved)
    cardSavedLabel := dashboardGui.AddText("x896 y338 w220 h22 c666666 +BackgroundTrans", "节省时间")
    cardSavedLabel.SetFont("s11")
    AddDashboardControl("home", cardSavedLabel)

    cardSpeedBg := dashboardGui.AddText("x1124 y280 w240 h104 BackgroundFFFFFF")
    AddDashboardControl("home", cardSpeedBg)
    dashboardMetricSpeed := dashboardGui.AddText("x1144 y300 w210 h34 c161616 +BackgroundTrans", "0 chars/min")
    dashboardMetricSpeed.SetFont("s18 w700")
    AddDashboardControl("home", dashboardMetricSpeed)
    cardSpeedLabel := dashboardGui.AddText("x1144 y338 w210 h22 c666666 +BackgroundTrans", "平均口述速度")
    cardSpeedLabel.SetFont("s11")
    AddDashboardControl("home", cardSpeedLabel)

    dictTitle := dashboardGui.AddText("x306 y58 w320 h72 c111111 +BackgroundTrans", "词典")
    dictTitle.SetFont("s42 w700")
    AddDashboardControl("dict", dictTitle)

    dictNewWordBtn := dashboardGui.AddText("x1258 y66 w96 h34 +0x100 +0x200 +Center Background1B1D22 cFFFFFF", "新词")
    dictNewWordBtn.SetFont("s11 w700")
    dictNewWordBtn.OnEvent("Click", OnDashboardNewWordClick)
    AddDashboardControl("dict", dictNewWordBtn)

    dashboardDictDeleteBtn := dashboardGui.AddText("x1148 y66 w96 h34 +0x100 +0x200 +Center BackgroundFFFFFF c1B1D22", "删除词条")
    dashboardDictDeleteBtn.SetFont("s10 w700")
    dashboardDictDeleteBtn.OnEvent("Click", OnDashboardDeleteSelectedClick)
    AddDashboardControl("dict", dashboardDictDeleteBtn)

    dashboardDictSamplesBtn := dashboardGui.AddText("x1038 y66 w96 h34 +0x100 +0x200 +Center BackgroundFFFFFF c1B1D22", "录音样本")
    dashboardDictSamplesBtn.SetFont("s10 w700")
    dashboardDictSamplesBtn.OnEvent("Click", OnDashboardOpenTermSamplesClick)
    AddDashboardControl("dict", dashboardDictSamplesBtn)

    dashboardDictSearch := dashboardGui.AddEdit("x306 y124 w470 h36 -VScroll")
    dashboardDictSearch.SetFont("s11", "Microsoft YaHei UI")
    dashboardDictSearch.OnEvent("Change", OnDashboardSearchChange)
    AddDashboardControl("dict", dashboardDictSearch)

    dictListBg := dashboardGui.AddText("x306 y172 w1056 h676 BackgroundFFFFFF")
    AddDashboardControl("dict", dictListBg)

    dashboardDictList := dashboardGui.AddListView("x318 y184 w1032 h652", ["Term", "Samples", "Status"])
    dashboardDictList.SetFont("s11", "Microsoft YaHei UI")
    dashboardDictList.ModifyCol(1, 640)
    dashboardDictList.ModifyCol(2, 120)
    dashboardDictList.ModifyCol(3, 220)
    dashboardDictList.OnEvent("DoubleClick", OnDashboardDictRowDoubleClick)
    AddDashboardControl("dict", dashboardDictList)

    dashboardGui.OnEvent("Close", HideDashboard)
    dashboardGui.OnEvent("Escape", HideDashboard)
    SetDashboardPage("home")
}

AddDashboardControl(page, control)
{
    global dashboardHomeControls, dashboardDictControls
    if (page = "home")
        dashboardHomeControls.Push(control)
    else
        dashboardDictControls.Push(control)
}

OnDashboardNavHomeClick(*)
{
    SetDashboardPage("home")
}

OnDashboardNavDictClick(*)
{
    SetDashboardPage("dict")
}

SetDashboardPage(page)
{
    global dashboardHomeControls, dashboardDictControls
    global dashboardNavHome, dashboardNavDict
    showHome := (page = "home")

    for _, control in dashboardHomeControls
        control.Visible := showHome
    for _, control in dashboardDictControls
        control.Visible := !showHome

    if (showHome)
    {
        dashboardNavHome.Opt("+BackgroundE4E4E6 c111111")
        dashboardNavDict.Opt("+BackgroundF1F1F2 c444444")
    }
    else
    {
        dashboardNavHome.Opt("+BackgroundF1F1F2 c444444")
        dashboardNavDict.Opt("+BackgroundE4E4E6 c111111")
    }
}

TrackDashboardRecordingDuration()
{
    global dashboardRecordingStartTick, dashboardTotalSeconds
    if (dashboardRecordingStartTick <= 0)
        return

    elapsedMs := A_TickCount - dashboardRecordingStartTick
    dashboardRecordingStartTick := 0
    if (elapsedMs <= 0)
        return

    elapsedSec := Floor(elapsedMs / 1000.0)
    if (elapsedSec <= 0)
        elapsedSec := 1
    dashboardTotalSeconds += elapsedSec
    RefreshDashboardHomeMetrics()
}

TrackDashboardFinalText(text)
{
    global dashboardTotalChars
    if (text = "")
        return

    dashboardTotalChars += StrLen(text)
    RefreshDashboardHomeMetrics()
}

LoadDashboardDataFromServer()
{
    global dashboardTotalSeconds, dashboardTotalChars
    global dashboardAvgCharsPerMinute, dashboardSavedSeconds, dashboardProfileScore
    global dashboardWordEntries

    try
    {
        summary := ApiGetDashboardSummary()
        dashboardTotalSeconds := summary["total_duration_seconds"]
        dashboardTotalChars := summary["total_chars"]
        dashboardAvgCharsPerMinute := summary["average_chars_per_minute"]
        dashboardSavedSeconds := summary["saved_seconds"]
        dashboardProfileScore := summary["profile_score"]

        termsBlob := ApiGetDashboardTermsBlob()
        dashboardWordEntries := ParseDashboardTermsBlob(termsBlob)
    }
    catch Error as err
    {
        LogLine("dashboard sync failed: " . err.Message)
    }
}

RefreshDashboardHomeMetrics()
{
    global dashboardMetricPersonality, dashboardMetricTotalTime
    global dashboardMetricChars, dashboardMetricSaved, dashboardMetricSpeed
    global dashboardTotalSeconds, dashboardTotalChars, dashboardWordEntries
    global dashboardAvgCharsPerMinute, dashboardSavedSeconds, dashboardProfileScore

    if (!IsObject(dashboardMetricTotalTime))
        return

    dashboardMetricTotalTime.Value := FormatDashboardDuration(dashboardTotalSeconds)
    dashboardMetricChars.Value := FormatDashboardChars(dashboardTotalChars)
    dashboardMetricSaved.Value := FormatDashboardDuration(dashboardSavedSeconds)

    speed := dashboardAvgCharsPerMinute
    if (speed < 0)
        speed := 0
    dashboardMetricSpeed.Value := speed . " chars/min"

    profileScore := dashboardProfileScore
    if (profileScore < 0 || profileScore > 99)
        profileScore := 0
    dashboardMetricPersonality.Value := profileScore . "%"
}

FormatDashboardDuration(totalSeconds)
{
    if (totalSeconds <= 0)
        return "0 min"

    totalMinutes := Floor(totalSeconds / 60)
    if (totalMinutes <= 0)
        return "1 min"

    if (totalMinutes < 60)
        return totalMinutes . " min"

    hours := Floor(totalMinutes / 60)
    minutes := Mod(totalMinutes, 60)
    if (minutes = 0)
        return hours . " h"
    return hours . " h " . minutes . " min"
}

FormatDashboardChars(totalChars)
{
    if (totalChars < 1000)
        return totalChars . " chars"

    k := Round(totalChars / 1000.0, 1)
    if (Mod(k, 1) = 0)
        k := Round(k)
    return k . "K chars"
}

OnDashboardNewWordClick(*)
{
    ib := InputBox("请输入新词", "添加词条")
    if (ib.Result != "OK")
        return

    word := Trim(ib.Value)
    if (word = "")
        return

    try
    {
        addResult := ApiAddDashboardManualTerm(word)
        if (!addResult["ok"])
            throw Error("save failed")
    }
    catch Error as err
    {
        MsgBox("添加失败: " . err.Message, "Voice Text Organizer", "Iconx")
        return
    }

    LoadDashboardDataFromServer()
    RefreshDashboardDictionaryList()
    OpenTermSamplesDialog(addResult["term"])
}

OnDashboardOpenTermSamplesClick(*)
{
    global dashboardDictList
    if (!IsObject(dashboardDictList))
        return

    row := dashboardDictList.GetNext(0)
    if (!row)
    {
        MsgBox("请先选择一个词条。", "Voice Text Organizer", "Icon!")
        return
    }

    term := Trim(dashboardDictList.GetText(row, 1))
    if (term = "")
        return
    OpenTermSamplesDialog(term)
}

OnDashboardDictRowDoubleClick(ctrl, row)
{
    if (!row)
        return
    term := Trim(ctrl.GetText(row, 1))
    if (term = "")
        return
    OpenTermSamplesDialog(term)
}

OnDashboardDeleteSelectedClick(*)
{
    global dashboardDictList
    if (!IsObject(dashboardDictList))
        return

    selectedTerms := []
    row := 0
    while (row := dashboardDictList.GetNext(row))
    {
        word := Trim(dashboardDictList.GetText(row, 1))
        if (word != "")
            selectedTerms.Push(word)
    }

    if (selectedTerms.Length = 0)
    {
        MsgBox("请先在词典里选择要删除的词。", "Voice Text Organizer", "Icon!")
        return
    }

    confirm := MsgBox(
        "确认删除选中的 " . selectedTerms.Length . " 个词吗？`n删除后词条及样本会一起删除。",
        "Voice Text Organizer",
        "OKCancel Icon!"
    )
    if (confirm != "OK")
        return

    try
    {
        for _, term in selectedTerms
            ApiDeleteDashboardTerm(term)
    }
    catch Error as err
    {
        MsgBox("删除失败: " . err.Message, "Voice Text Organizer", "Iconx")
        return
    }

    LoadDashboardDataFromServer()
    RefreshDashboardDictionaryList()
}

OnDashboardSearchChange(*)
{
    RefreshDashboardDictionaryList()
}

RefreshDashboardDictionaryList()
{
    global dashboardDictList, dashboardDictSearch, dashboardWordEntries
    if (!IsObject(dashboardDictList))
        return

    query := ""
    if (IsObject(dashboardDictSearch))
        query := Trim(StrLower(dashboardDictSearch.Value))

    dashboardDictList.Delete()
    for _, entry in dashboardWordEntries
    {
        word := entry["word"]
        if (query != "" && !InStr(StrLower(word), query))
            continue

        dashboardDictList.Add("", word, entry["sample_count"], ConvertTermStatusLabel(entry["status"]))
    }
}

ConvertTermStatusLabel(status)
{
    if (status = "active")
        return "已生效"
    return "待录音"
}

EnsureTermSampleGui()
{
    global termSampleGui, termSampleTermText, termSampleStatusText
    global termSampleList, termSampleStartBtn, termSampleDeleteBtn, termSamplePlayBtn
    if (IsObject(termSampleGui))
        return

    termSampleGui := Gui("+AlwaysOnTop", "词条录音样本")
    termSampleGui.SetFont("s10", "Microsoft YaHei UI")

    termSampleTermText := termSampleGui.AddText("xm ym w660", "词条: ")
    termSampleStatusText := termSampleGui.AddText("xm y+6 w660", "状态: 待录音")

    termSampleStartBtn := termSampleGui.AddButton("xm y+12 w110", "开始录音")
    termSamplePlayBtn := termSampleGui.AddButton("x+10 yp w90", "试听样本")
    termSampleDeleteBtn := termSampleGui.AddButton("x+10 yp w110", "删除样本")
    closeBtn := termSampleGui.AddButton("x+10 yp w90", "关闭")

    termSampleList := termSampleGui.AddListView("xm y+12 w660 h280", ["ID", "时长(ms)", "创建时间", "文件路径"])
    termSampleList.ModifyCol(1, 70)
    termSampleList.ModifyCol(2, 100)
    termSampleList.ModifyCol(3, 220)
    termSampleList.ModifyCol(4, 250)

    termSampleStartBtn.OnEvent("Click", OnTermSampleStartStopClick)
    termSamplePlayBtn.OnEvent("Click", OnTermSamplePlayClick)
    termSampleDeleteBtn.OnEvent("Click", OnTermSampleDeleteClick)
    termSampleList.OnEvent("DoubleClick", OnTermSampleListDoubleClick)
    closeBtn.OnEvent("Click", HideTermSampleDialog)
    termSampleGui.OnEvent("Close", HideTermSampleDialog)
}

OpenTermSamplesDialog(term)
{
    global termSampleCurrentTerm, termSampleGui, termSampleTermText
    global termSampleRecordingSessionId, termSampleRecordingTerm
    term := Trim(term)
    if (term = "")
        return
    if (termSampleRecordingSessionId != "" && termSampleRecordingTerm != "" && term != termSampleRecordingTerm)
    {
        MsgBox(
            "当前正在为词条 [" . termSampleRecordingTerm . "] 录音，请先停止后再切换词条。",
            "Voice Text Organizer",
            "Icon!"
        )
        return
    }

    EnsureTermSampleGui()
    termSampleCurrentTerm := term
    termSampleTermText.Value := "词条: " . termSampleCurrentTerm
    SetTermSampleRecordButton(termSampleRecordingSessionId != "")
    RefreshTermSamplesDialog()
    termSampleGui.Show("w700 h420 Center")
}

HideTermSampleDialog(*)
{
    global termSampleGui, termSampleRecordingSessionId
    if (!IsObject(termSampleGui))
        return
    if (termSampleRecordingSessionId != "")
    {
        MsgBox("请先停止当前样本录音。", "Voice Text Organizer", "Icon!")
        return
    }
    termSampleGui.Hide()
}

SetTermSampleRecordButton(isRecording)
{
    global termSampleStartBtn
    if (!IsObject(termSampleStartBtn))
        return
    termSampleStartBtn.Text := isRecording ? "停止录音" : "开始录音"
}

RefreshTermSamplesDialog()
{
    global termSampleCurrentTerm, termSampleList, termSampleStatusText, dashboardWordEntries
    if (!IsObject(termSampleList))
        return

    try
    {
        samplesBlob := ApiGetDashboardTermSamplesBlob(termSampleCurrentTerm)
        entries := ParseDashboardTermSamplesBlob(samplesBlob)
        LoadDashboardDataFromServer()
        RefreshDashboardDictionaryList()
    }
    catch Error as err
    {
        MsgBox("加载样本失败: " . err.Message, "Voice Text Organizer", "Iconx")
        return
    }

    statusLabel := "待录音"
    sampleCount := entries.Length
    if (sampleCount > 0)
        statusLabel := "已生效"
    for _, entry in dashboardWordEntries
    {
        if (entry["word"] = termSampleCurrentTerm)
        {
            if (sampleCount <= 0)
                sampleCount := entry["sample_count"]
            if (sampleCount <= 0)
                statusLabel := ConvertTermStatusLabel(entry["status"])
            break
        }
    }
    termSampleStatusText.Value := "状态: " . statusLabel . " | 样本数: " . sampleCount

    termSampleList.Delete()
    for _, entry in entries
    {
        termSampleList.Add("", entry["sample_id"], entry["duration_ms"], entry["created_at"], entry["sample_path"])
    }
}

OnTermSampleStartStopClick(*)
{
    global termSampleRecordingSessionId, termSampleBusy
    if (termSampleBusy)
        return
    termSampleBusy := true
    try
    {
    if (termSampleRecordingSessionId = "")
        StartTermSampleRecording()
    else
        StopTermSampleRecording()
    }
    finally
    {
        termSampleBusy := false
    }
}

StartTermSampleRecording()
{
    global termSampleCurrentTerm, termSampleRecordingSessionId, termSampleRecordingTerm
    if (termSampleCurrentTerm = "")
        return
    if (HasActiveRecording())
    {
        MsgBox("请先结束主录音会话。", "Voice Text Organizer", "Icon!")
        return
    }

    try
    {
        PausePlaybackForRecording()
        sessionId := ApiStartDashboardTermSample(termSampleCurrentTerm)
        if (sessionId = "")
            throw Error("empty session id")
        termSampleRecordingSessionId := sessionId
        termSampleRecordingTerm := termSampleCurrentTerm
        ShowWaveformIndicator()
        SetTermSampleRecordButton(true)
    }
    catch Error as err
    {
        ResumePlaybackAfterRecording()
        HideWaveformIndicator()
        termSampleRecordingSessionId := ""
        termSampleRecordingTerm := ""
        MsgBox("开始录音失败: " . FormatTermSampleErrorMessage("start", err.Message), "Voice Text Organizer", "Iconx")
    }
}

StopTermSampleRecording()
{
    global termSampleCurrentTerm, termSampleRecordingSessionId, termSampleRecordingTerm
    if (termSampleRecordingSessionId = "")
        return

    recordingTerm := termSampleRecordingTerm != "" ? termSampleRecordingTerm : termSampleCurrentTerm
    try
    {
        result := ApiStopDashboardTermSample(recordingTerm, termSampleRecordingSessionId)
        MsgBox(
            "录音样本已保存。`n样本数: " . result["sample_count"] . "`n状态: " . ConvertTermStatusLabel(result["status"]),
            "Voice Text Organizer",
            "Iconi"
        )
        termSampleCurrentTerm := recordingTerm
        termSampleRecordingSessionId := ""
        termSampleRecordingTerm := ""
        RefreshTermSamplesDialog()
    }
    catch Error as err
    {
        MsgBox("停止录音失败: " . FormatTermSampleErrorMessage("stop", err.Message), "Voice Text Organizer", "Iconx")
    }
    finally
    {
        ResumePlaybackAfterRecording()
        HideWaveformIndicator()
        SetTermSampleRecordButton(false)
        termSampleRecordingSessionId := ""
        termSampleRecordingTerm := ""
    }
}

OnTermSampleDeleteClick(*)
{
    global termSampleList, termSampleCurrentTerm
    if (!IsObject(termSampleList))
        return
    row := termSampleList.GetNext(0)
    if (!row)
    {
        MsgBox("请先选择要删除的样本。", "Voice Text Organizer", "Icon!")
        return
    }

    sampleId := 0
    try
        sampleId := Integer(termSampleList.GetText(row, 1))
    catch
        sampleId := 0
    if (sampleId <= 0)
        return

    try
    {
        ApiDeleteDashboardTermSample(termSampleCurrentTerm, sampleId)
    }
    catch Error as err
    {
        MsgBox("删除样本失败: " . err.Message, "Voice Text Organizer", "Iconx")
        return
    }

    RefreshTermSamplesDialog()
}

OnTermSamplePlayClick(*)
{
    global termSampleList
    if (!IsObject(termSampleList))
        return
    row := termSampleList.GetNext(0)
    if (!row)
    {
        MsgBox("请先选择要试听的样本。", "Voice Text Organizer", "Icon!")
        return
    }

    samplePath := Trim(termSampleList.GetText(row, 4))
    if (samplePath = "")
        return
    if !FileExist(samplePath)
    {
        MsgBox("样本文件不存在: " . samplePath, "Voice Text Organizer", "Icon!")
        return
    }

    try
        SoundPlay(samplePath)
    catch Error as err
        MsgBox("播放失败: " . err.Message, "Voice Text Organizer", "Iconx")
}

OnTermSampleListDoubleClick(*)
{
    OnTermSamplePlayClick()
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

GetFullTextSafe()
{
    clipSaved := ClipboardAll()
    fullText := ""
    try
    {
        A_Clipboard := ""
        Send("^a")
        Sleep(50)
        Send("^c")
        if (ClipWait(0.3))
            fullText := A_Clipboard
        Send("{End}")
    }
    finally
    {
        A_Clipboard := clipSaved
    }
    return fullText
}

InsertText(text, replaceSelection := false)
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
            . ", replaceSelection=" . (replaceSelection ? "true" : "false")
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
            LogLine(
                "insert via SendText fallback, length=" . StrLen(text)
                . ", replaceSelection=" . (replaceSelection ? "true" : "false")
            )
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

ApiStartRecord(selectedText, existingText := "")
{
    q := Chr(34)
    payload := "{" . q . "selected_text" . q . ":" . q . JsonEscape(selectedText) . q
    payload .= "," . q . "existing_text" . q . ":" . q . JsonEscape(existingText) . q . "}"
    response := HttpPost("/v1/record/start", payload)
    return ExtractJsonString(response, "session_id")
}

ApiStopRecord(sessionId)
{
    global defaultMode, defaultLanguageHint
    q := Chr(34)
    payload := "{" . q . "session_id" . q . ":" . q . JsonEscape(sessionId) . q
    payload .= "," . q . "mode" . q . ":" . q . JsonEscape(defaultMode) . q
    payload .= "," . q . "language_hint" . q . ":" . q . JsonEscape(defaultLanguageHint) . q . "}"
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

ApiGetAppVersion()
{
    response := HttpGet("/v1/app/version")
    result := Map()
    result["current_version"] := ExtractJsonString(response, "current_version")
    result["latest_version"] := ExtractJsonString(response, "latest_version")
    result["has_update"] := ExtractJsonBool(response, "has_update")
    result["release_url"] := ExtractJsonString(response, "release_url")
    result["checked_at"] := ExtractJsonString(response, "checked_at")
    return result
}

ApiUpdateSettings(apiKey, mode, personalizedEnabled)
{
    q := Chr(34)
    payload := "{" . q . "default_mode" . q . ":" . q . JsonEscape(mode) . q
    payload .= "," . q . "personalized_acoustic_enabled" . q . ":" . (personalizedEnabled ? "true" : "false")
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
    result["personalized_acoustic_enabled"] := ExtractJsonBool(response, "personalized_acoustic_enabled")
    return result
}

ApiGetDashboardSummary()
{
    response := HttpGet("/v1/dashboard/summary")
    result := Map()
    result["total_duration_seconds"] := ExtractJsonInt(response, "total_duration_seconds")
    result["total_chars"] := ExtractJsonInt(response, "total_chars")
    result["average_chars_per_minute"] := ExtractJsonInt(response, "average_chars_per_minute")
    result["saved_seconds"] := ExtractJsonInt(response, "saved_seconds")
    result["profile_score"] := ExtractJsonInt(response, "profile_score")
    return result
}

ApiGetDashboardTermsBlob()
{
    response := HttpGet("/v1/dashboard/terms/export?status=all&limit=600")
    return ExtractJsonString(response, "terms_blob")
}

ApiAddDashboardManualTerm(term)
{
    q := Chr(34)
    payload := "{" . q . "term" . q . ":" . q . JsonEscape(term) . q . "}"
    response := HttpPost("/v1/dashboard/terms/manual", payload)
    result := Map()
    result["ok"] := ExtractJsonBool(response, "ok")
    result["term"] := ExtractJsonString(response, "term")
    result["existed"] := ExtractJsonBool(response, "existed")
    result["sample_count"] := ExtractJsonInt(response, "sample_count")
    result["status"] := ExtractJsonString(response, "status")
    return result
}

ApiDeleteDashboardTerm(term)
{
    q := Chr(34)
    payload := "{" . q . "term" . q . ":" . q . JsonEscape(term) . q . "}"
    response := HttpPost("/v1/dashboard/terms/delete", payload)
    return ExtractJsonBool(response, "deleted")
}

ParseDashboardTermsBlob(blob)
{
    entries := []
    if (blob = "")
        return entries

    lines := StrSplit(blob, "`n", "`r")
    for _, line in lines
    {
        trimmed := Trim(line)
        if (trimmed = "")
            continue

        parts := StrSplit(trimmed, "`t")
        if (parts.Length < 3)
            continue

        sampleCount := 0
        try
            sampleCount := Integer(parts[2])
        catch
            sampleCount := 0

        entry := Map()
        entry["word"] := parts[1]
        entry["sample_count"] := sampleCount
        entry["status"] := parts[3]
        entries.Push(entry)
    }
    return entries
}

ApiStartDashboardTermSample(term)
{
    q := Chr(34)
    payload := "{" . q . "term" . q . ":" . q . JsonEscape(term) . q . "}"
    try
    {
        response := HttpPost("/v1/dashboard/terms/sample/start", payload)
    }
    catch Error as err
    {
        if (IsEndpointNotFoundError(err.Message) && ForceRestartBackendForApiUpgrade())
            response := HttpPost("/v1/dashboard/terms/sample/start", payload)
        else
            throw err
    }
    return ExtractJsonString(response, "session_id")
}

ApiStopDashboardTermSample(term, sessionId)
{
    q := Chr(34)
    payload := "{" . q . "term" . q . ":" . q . JsonEscape(term) . q
    payload .= "," . q . "session_id" . q . ":" . q . JsonEscape(sessionId) . q . "}"
    try
    {
        response := HttpPost("/v1/dashboard/terms/sample/stop", payload)
    }
    catch Error as err
    {
        if (IsEndpointNotFoundError(err.Message) && ForceRestartBackendForApiUpgrade())
            response := HttpPost("/v1/dashboard/terms/sample/stop", payload)
        else
            throw err
    }

    result := Map()
    result["ok"] := ExtractJsonBool(response, "ok")
    result["sample_id"] := ExtractJsonInt(response, "sample_id")
    result["sample_count"] := ExtractJsonInt(response, "sample_count")
    result["status"] := ExtractJsonString(response, "status")
    result["duration_ms"] := ExtractJsonInt(response, "duration_ms")
    result["quality_score"] := ExtractJsonNumber(response, "quality_score")
    result["sample_path"] := ExtractJsonString(response, "sample_path")
    return result
}

ApiGetDashboardTermSamplesBlob(term)
{
    q := Chr(34)
    payload := "{" . q . "term" . q . ":" . q . JsonEscape(term) . q . "}"
    try
    {
        response := HttpPost("/v1/dashboard/terms/samples/export", payload)
    }
    catch Error as err
    {
        if (InStr(err.Message, "HTTP 405") || InStr(err.Message, "HTTP 404"))
        {
            endpoint := "/v1/dashboard/terms/samples/export?term=" . UrlEncode(term)
            response := HttpGet(endpoint)
        }
        else
        {
            throw err
        }
    }
    return ExtractJsonString(response, "samples_blob")
}

ApiDeleteDashboardTermSample(term, sampleId)
{
    q := Chr(34)
    payload := "{" . q . "term" . q . ":" . q . JsonEscape(term) . q
    payload .= "," . q . "sample_id" . q . ":" . sampleId . "}"
    response := HttpPost("/v1/dashboard/terms/sample/delete", payload)
    result := Map()
    result["ok"] := ExtractJsonBool(response, "ok")
    result["sample_count"] := ExtractJsonInt(response, "sample_count")
    result["status"] := ExtractJsonString(response, "status")
    return result
}

ParseDashboardTermSamplesBlob(blob)
{
    entries := []
    if (blob = "")
        return entries

    lines := StrSplit(blob, "`n", "`r")
    for _, line in lines
    {
        trimmed := Trim(line)
        if (trimmed = "")
            continue

        parts := StrSplit(trimmed, "`t")
        if (parts.Length < 4)
            continue

        sampleId := 0
        durationMs := 0
        try
            sampleId := Integer(parts[1])
        catch
            sampleId := 0
        try
            durationMs := Integer(parts[2])
        catch
            durationMs := 0

        entry := Map()
        entry["sample_id"] := sampleId
        entry["duration_ms"] := durationMs
        entry["created_at"] := parts[3]
        entry["sample_path"] := parts[4]
        entries.Push(entry)
    }
    return entries
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
    global baseUrl, httpResolveTimeoutMs, httpConnectTimeoutMs, httpSendTimeoutMs, httpReceiveTimeoutMs
    req := ComObject("WinHttp.WinHttpRequest.5.1")
    try
    {
        req.Open(method, baseUrl endpoint, false)
        req.SetTimeouts(httpResolveTimeoutMs, httpConnectTimeoutMs, httpSendTimeoutMs, httpReceiveTimeoutMs)
        if (method = "POST" || method = "PUT")
            req.SetRequestHeader("Content-Type", "application/json; charset=utf-8")
        req.Send(body)
    }
    catch Error as err
    {
        if (IsHttpTimeoutError(err.Message))
        {
            LogLine("http timeout, method=" . method . ", endpoint=" . endpoint . ", err=" . err.Message)
            throw Error("Backend processing timeout. Please retry this recording.")
        }
        if (allowRetry && TryStartBackend())
            return HttpRequest(method, endpoint, body, false)
        throw Error("Cannot connect to backend: " err.Message)
    }

    responseText := GetUtf8ResponseText(req)
    if (req.Status < 200 || req.Status >= 300)
        throw Error("HTTP " req.Status " " responseText)
    return responseText
}

IsHttpTimeoutError(message)
{
    text := StrLower(message)
    return InStr(text, "12002")
        || InStr(text, "timeout")
        || InStr(text, "timed out")
        || InStr(text, "瓒呮椂")
}

IsEndpointNotFoundError(message)
{
    text := StrLower(message)
    return InStr(text, "http 404") && InStr(text, "not found")
}

TryStartBackend()
{
    serviceScript := A_ScriptDir . "\..\scripts\run-service.ps1"
    if FileExist(serviceScript)
    {
        quoted := Chr(34) . serviceScript . Chr(34)
        LogLine("starting backend via " . serviceScript)
        Run("powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File " . quoted,, "Hide")
        return WaitBackendReady(15000)
    }

    serviceExe := A_ScriptDir . "\TypelessService.exe"
    if FileExist(serviceExe)
    {
        quotedExe := Chr(34) . serviceExe . Chr(34)
        LogLine("starting backend exe via " . serviceExe)
        Run(quotedExe, A_ScriptDir, "Hide")
        return WaitBackendReady(15000)
    }

    if !FileExist(serviceScript)
    {
        LogLine("backend start skipped: missing service exe and script (" . serviceScript . ")")
        return false
    }
}

ForceRestartBackendForApiUpgrade()
{
    global baseUrl
    LogLine("backend api mismatch detected, forcing restart")
    try
    {
        killCmd := "$conn = Get-NetTCPConnection -LocalPort 8775 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if($conn){ Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue }"
        RunWait("powershell -NoProfile -ExecutionPolicy Bypass -Command " . Chr(34) . killCmd . Chr(34),, "Hide")
    }
    catch Error as err
    {
        LogLine("force restart kill step failed: " . err.Message)
    }
    return TryStartBackend()
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
    ; JSON unescape: handle \\ first via placeholder to avoid double-processing
    val := StrReplace(val, "\\", Chr(1))
    val := StrReplace(val, "\n", "`n")
    val := StrReplace(val, "\r", "`r")
    val := StrReplace(val, "\t", "`t")
    val := StrReplace(val, "\" . Chr(34), Chr(34))
    val := StrReplace(val, Chr(1), "\")
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

ExtractJsonInt(json, key)
{
    q := Chr(34)
    pattern := q . key . q . "\s*:\s*(-?\d+)"
    if !RegExMatch(json, pattern, &m)
        return 0
    try
        return Integer(m[1])
    catch
        return 0
}

ExtractJsonNumber(json, key)
{
    q := Chr(34)
    pattern := q . key . q . "\s*:\s*(-?\d+(?:\.\d+)?)"
    if !RegExMatch(json, pattern, &m)
        return 0.0
    try
        return Number(m[1])
    catch
        return 0.0
}

JsonEscape(text)
{
    text := StrReplace(text, Chr(92), "\\")
    text := StrReplace(text, Chr(34), Chr(92) . Chr(34))
    text := StrReplace(text, "`r", "")
    text := StrReplace(text, "`n", "\n")
    return text
}

UrlEncode(text)
{
    utf8Size := StrPut(text, "UTF-8")
    buf := Buffer(utf8Size, 0)
    StrPut(text, buf, "UTF-8")
    encoded := ""

    Loop (utf8Size - 1)
    {
        b := NumGet(buf, A_Index - 1, "UChar")
        isAlphaNum := (b >= 0x30 && b <= 0x39) || (b >= 0x41 && b <= 0x5A) || (b >= 0x61 && b <= 0x7A)
        isUnreserved := isAlphaNum || b = 0x2D || b = 0x5F || b = 0x2E || b = 0x7E
        if (isUnreserved)
            encoded .= Chr(b)
        else
            encoded .= "%" . Format("{:02X}", b)
    }
    return encoded
}

FormatTermSampleErrorMessage(action, message)
{
    text := Trim(message)
    if (InStr(text, "sample volume too low"))
        return "音量太小，请靠近麦克风并提高音量后重试。"
    if (InStr(text, "too much silence in sample"))
        return "录音中静音过多，请在说完词条后再点击停止。"
    if (InStr(text, "sample duration must be > 0.3s"))
        return "录音时间太短，请至少说 0.3 秒。"
    if (InStr(text, "sample duration must be <= 15s"))
        return "录音时间过长，请控制在 15 秒以内。"
    if (InStr(text, "sample clipping is too high"))
        return "录音过爆，请稍微远离麦克风后重试。"
    if (InStr(text, "sample recording session not found") || InStr(text, "recording session not found"))
        return "录音会话已失效，请重新开始录音。"
    if (InStr(text, "term does not match recording session"))
        return "当前词条与录音会话不一致，请重新打开该词条后录音。"
    if (InStr(text, "HTTP 404") && InStr(text, "Not Found"))
        return action = "start" ? "后端接口未就绪，请稍后重试。" : "停止接口未就绪，请先重新开始一条样本录音。"
    return text
}

NormalizeOutputText(text)
{
    ; Convert literal slash-n tokens to real line breaks before insertion.
    text := StrReplace(text, "\\r\\n", "`n")
    text := StrReplace(text, "\\n", "`n")
    text := StrReplace(text, "\\r", "`n")
    text := StrReplace(text, "\r\n", "`n")
    text := StrReplace(text, "\n", "`n")
    text := StrReplace(text, "\r", "`n")
    return text
}

