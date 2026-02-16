#Requires AutoHotkey v2.0
#SingleInstance Force
#Warn

global baseUrl := "http://127.0.0.1:8775"
global defaultMode := "cloud"
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
    localAppData := EnvGet("LOCALAPPDATA")
    if (localAppData != "")
        runtimeDir := localAppData . "\Typeless\runtime"
    else
        runtimeDir := A_ScriptDir . "\..\service\runtime"
}
global logFile := runtimeDir . "\hotkey.log"

global settingsGui := 0
global settingsStatusText := 0
global settingsApiKeyEdit := 0
global settingsModeDDL := 0

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
global dashboardFilterAll := 0
global dashboardFilterAuto := 0
global dashboardFilterManual := 0
global dashboardFilterMode := "all"
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
        existingText := ""
        if (selectedText = "")
            existingText := GetFullTextSafe()
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
            TrayTip("Voice Text Organizer", "发现新版本 v" . latestReleaseVersion . "，可在面板中点击更新入口。", 3)
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
    global dashboardDictSearch, dashboardDictList
    global dashboardFilterAll, dashboardFilterAuto, dashboardFilterManual
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

    homeSubTitle := dashboardGui.AddText("x306 y106 w760 h24 c666666 +BackgroundTrans", "按 Alt + 空格 键，开始/结束录音并自动插入语音文本。")
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
    leftLabel := dashboardGui.AddText("x350 y260 w220 h24 c6D6D6D +BackgroundTrans", "整体个性化")
    leftLabel.SetFont("s14")
    AddDashboardControl("home", leftLabel)

    cardTimeBg := dashboardGui.AddText("x876 y166 w240 h104 BackgroundFFFFFF")
    AddDashboardControl("home", cardTimeBg)
    dashboardMetricTotalTime := dashboardGui.AddText("x896 y186 w220 h36 c161616 +BackgroundTrans", "0 min")
    dashboardMetricTotalTime.SetFont("s22 w700")
    AddDashboardControl("home", dashboardMetricTotalTime)
    cardTimeLabel := dashboardGui.AddText("x896 y226 w220 h22 c666666 +BackgroundTrans", "总口述时间")
    cardTimeLabel.SetFont("s11")
    AddDashboardControl("home", cardTimeLabel)

    cardCharsBg := dashboardGui.AddText("x1124 y166 w240 h104 BackgroundFFFFFF")
    AddDashboardControl("home", cardCharsBg)
    dashboardMetricChars := dashboardGui.AddText("x1144 y186 w210 h36 c161616 +BackgroundTrans", "0 字")
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
    dashboardMetricSpeed := dashboardGui.AddText("x1144 y300 w210 h34 c161616 +BackgroundTrans", "0 每分钟字数")
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

    dashboardDictDeleteBtn := dashboardGui.AddText("x1148 y66 w96 h34 +0x100 +0x200 +Center BackgroundFFFFFF c1B1D22", "删除选中")
    dashboardDictDeleteBtn.SetFont("s10 w700")
    dashboardDictDeleteBtn.OnEvent("Click", OnDashboardDeleteSelectedClick)
    AddDashboardControl("dict", dashboardDictDeleteBtn)

    dashboardFilterAll := dashboardGui.AddText("x306 y124 w66 h34 +0x100 +0x200 +Center BackgroundFFFFFF c171717", "所有")
    dashboardFilterAll.SetFont("s11 w500")
    dashboardFilterAll.OnEvent("Click", OnDashboardFilterAllClick)
    AddDashboardControl("dict", dashboardFilterAll)

    dashboardFilterAuto := dashboardGui.AddText("x378 y124 w104 h34 +0x100 +0x200 +Center BackgroundE8E8EA c3B3B3B", "自动添加")
    dashboardFilterAuto.SetFont("s11 w500")
    dashboardFilterAuto.OnEvent("Click", OnDashboardFilterAutoClick)
    AddDashboardControl("dict", dashboardFilterAuto)

    dashboardFilterManual := dashboardGui.AddText("x486 y124 w104 h34 +0x100 +0x200 +Center BackgroundE8E8EA c3B3B3B", "手动添加")
    dashboardFilterManual.SetFont("s11 w500")
    dashboardFilterManual.OnEvent("Click", OnDashboardFilterManualClick)
    AddDashboardControl("dict", dashboardFilterManual)

    dashboardDictSearch := dashboardGui.AddEdit("x306 y172 w470 h36 -VScroll")
    dashboardDictSearch.SetFont("s11", "Microsoft YaHei UI")
    dashboardDictSearch.OnEvent("Change", OnDashboardSearchChange)
    AddDashboardControl("dict", dashboardDictSearch)

    dictListBg := dashboardGui.AddText("x306 y220 w1056 h628 BackgroundFFFFFF")
    AddDashboardControl("dict", dictListBg)

    dashboardDictList := dashboardGui.AddListView("x318 y232 w1032 h604", ["词", "来源", "次数"])
    dashboardDictList.SetFont("s11", "Microsoft YaHei UI")
    dashboardDictList.ModifyCol(1, 640)
    dashboardDictList.ModifyCol(2, 220)
    dashboardDictList.ModifyCol(3, 100)
    AddDashboardControl("dict", dashboardDictList)

    dashboardGui.OnEvent("Close", HideDashboard)
    dashboardGui.OnEvent("Escape", HideDashboard)
    SetDashboardPage("home")
    SetDashboardFilterMode("all")
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
    ExtractAutoDictionaryWords(text)
    RefreshDashboardHomeMetrics()
    RefreshDashboardDictionaryList()
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
    dashboardMetricSpeed.Value := speed . " 每分钟字数"

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
        return totalChars . " 字"

    k := Round(totalChars / 1000.0, 1)
    if (Mod(k, 1) = 0)
        k := Round(k)
    return k . "K 字"
}

ExtractAutoDictionaryWords(text)
{
    pos := 1
    found := 0
    while (found < 10)
    {
        matchPos := RegExMatch(text, "[\x{4E00}-\x{9FFF}]{2,8}", &m, pos)
        if (!matchPos)
            break
        token := Trim(m[0])
        pos := matchPos + StrLen(token)
        if (StrLen(token) > 6)
            continue
        UpsertDictionaryEntry(token, "auto")
        found += 1
    }

    pos := 1
    while (found < 18)
    {
        matchPos := RegExMatch(text, "[A-Za-z][A-Za-z'-]{3,20}", &m, pos)
        if (!matchPos)
            break
        token := Trim(m[0])
        pos := matchPos + StrLen(token)
        UpsertDictionaryEntry(token, "auto")
        found += 1
    }
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
        ok := ApiAddDashboardManualTerm(word)
        if (!ok)
            throw Error("save failed")
    }
    catch Error as err
    {
        MsgBox("添加失败: " . err.Message, "Voice Text Organizer", "Iconx")
        return
    }

    LoadDashboardDataFromServer()
    RefreshDashboardDictionaryList()
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
        "确认删除选中的 " . selectedTerms.Length . " 个词吗？`n删除后不会在词典中显示。",
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

OnDashboardFilterAllClick(*)
{
    SetDashboardFilterMode("all")
}

OnDashboardFilterAutoClick(*)
{
    SetDashboardFilterMode("auto")
}

OnDashboardFilterManualClick(*)
{
    SetDashboardFilterMode("manual")
}

SetDashboardFilterMode(mode)
{
    global dashboardFilterMode, dashboardFilterAll, dashboardFilterAuto, dashboardFilterManual
    dashboardFilterMode := mode

    if (IsObject(dashboardFilterAll))
    {
        dashboardFilterAll.Opt("+BackgroundE8E8EA c3B3B3B")
        dashboardFilterAuto.Opt("+BackgroundE8E8EA c3B3B3B")
        dashboardFilterManual.Opt("+BackgroundE8E8EA c3B3B3B")

        if (mode = "all")
            dashboardFilterAll.Opt("+BackgroundFFFFFF c171717")
        else if (mode = "auto")
            dashboardFilterAuto.Opt("+BackgroundFFFFFF c171717")
        else
            dashboardFilterManual.Opt("+BackgroundFFFFFF c171717")
    }

    RefreshDashboardDictionaryList()
}

OnDashboardSearchChange(*)
{
    RefreshDashboardDictionaryList()
}

RefreshDashboardDictionaryList()
{
    global dashboardDictList, dashboardDictSearch, dashboardFilterMode, dashboardWordEntries
    if (!IsObject(dashboardDictList))
        return

    query := ""
    if (IsObject(dashboardDictSearch))
        query := Trim(StrLower(dashboardDictSearch.Value))

    dashboardDictList.Delete()
    for _, entry in dashboardWordEntries
    {
        source := entry["type"]
        if (dashboardFilterMode != "all" && source != dashboardFilterMode)
            continue

        word := entry["word"]
        if (query != "" && !InStr(StrLower(word), query))
            continue

        sourceLabel := (source = "manual") ? "手动添加" : "自动添加"
        dashboardDictList.Add("", word, sourceLabel, entry["count"])
    }
}

UpsertDictionaryEntry(word, source)
{
    global dashboardWordEntries
    word := Trim(word)
    if (word = "")
        return
    if (RegExMatch(word, "^\d+$"))
        return

    idx := FindDictionaryWordIndex(word)
    if (idx > 0)
    {
        dashboardWordEntries[idx]["count"] := dashboardWordEntries[idx]["count"] + 1
        if (source = "manual")
            dashboardWordEntries[idx]["type"] := "manual"
        return
    }

    dashboardWordEntries.Push(Map("word", word, "type", source, "count", 1))
}

FindDictionaryWordIndex(word)
{
    global dashboardWordEntries
    for idx, entry in dashboardWordEntries
    {
        if (entry["word"] = word)
            return idx
    }
    return 0
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
    if (!replaceSelection)
    {
        ; For normal append mode, clear any auto-selection to avoid replacing content.
        Send("{End}")
        Sleep(50)
    }

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
    response := HttpGet("/v1/dashboard/terms/export?filter_mode=all&min_auto_count=3&limit=600")
    return ExtractJsonString(response, "terms_blob")
}

ApiAddDashboardManualTerm(term)
{
    q := Chr(34)
    payload := "{" . q . "term" . q . ":" . q . JsonEscape(term) . q . "}"
    response := HttpPost("/v1/dashboard/terms/manual", payload)
    return ExtractJsonBool(response, "ok")
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

        count := 1
        try
            count := Integer(parts[3])
        catch
            count := 1

        entry := Map()
        entry["word"] := parts[1]
        entry["type"] := parts[2]
        entry["count"] := count
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
        || InStr(text, "超时")
}

TryStartBackend()
{
    serviceExe := A_ScriptDir . "\TypelessService.exe"
    if FileExist(serviceExe)
    {
        quotedExe := Chr(34) . serviceExe . Chr(34)
        LogLine("starting backend exe via " . serviceExe)
        Run(quotedExe, A_ScriptDir, "Hide")
        return WaitBackendReady(15000)
    }

    serviceScript := A_ScriptDir . "\..\scripts\run-service.ps1"
    if !FileExist(serviceScript)
    {
        LogLine("backend start skipped: missing service exe and script (" . serviceScript . ")")
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

JsonEscape(text)
{
    text := StrReplace(text, Chr(92), "\\")
    text := StrReplace(text, Chr(34), Chr(92) . Chr(34))
    text := StrReplace(text, "`r", "")
    text := StrReplace(text, "`n", "\n")
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
