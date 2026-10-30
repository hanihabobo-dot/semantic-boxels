# The console's sound on Windows.  console_audio.py (in WSL) starts this in
# Windows PowerShell through the interop: one process loops the music, one
# plays the effects (-Mode play, System.Media.SoundPlayer) and, when asked,
# one speaks (-Mode say, Windows' own voices through System.Speech).  Lines
# on stdin, one command each:
#   play <path>     play a WAV once (asynchronous); 'ok' at once
#   loop <path>     play a WAV in a loop until the next loop, stop or exit
#   stop            stop the loop
#   say <text>      speak the text; 'ok' when it has been spoken
#   rate <n>        the voice's rate, -10 to 10
#   quit            exit (so does the end of stdin, after the current line)
# 'ready' on stdout once set up.  Nothing here touches the run.
param([string]$Mode = 'play', [string]$VoiceName = '', [int]$Rate = 0)
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Continue'
$synth = $null
if ($Mode -eq 'say') {
    Add-Type -AssemblyName System.Speech
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $synth.SetOutputToDefaultAudioDevice()
    # An English voice: the one named, else the first English one, else the
    # machine's default (the default here is a German one).
    $voices = @($synth.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object { $_.VoiceInfo })
    $pick = $null
    if ($VoiceName) { $pick = $voices | Where-Object { $_.Name -like "*$VoiceName*" } | Select-Object -First 1 }
    if (-not $pick) { $pick = $voices | Where-Object { $_.Culture.Name -like 'en-*' } | Select-Object -First 1 }
    if ($pick) { try { $synth.SelectVoice($pick.Name) } catch { } }
    $synth.Rate = [Math]::Max(-10, [Math]::Min(10, $Rate))
    $synth.Volume = 100
}
$player = New-Object System.Media.SoundPlayer
[Console]::Out.WriteLine('ready')
[Console]::Out.Flush()
while ($true) {
    $line = [Console]::In.ReadLine()
    if ($null -eq $line) { break }
    $line = $line.Trim()
    if ($line -eq '') { continue }
    if ($line -eq 'quit') { break }
    $sp = $line.IndexOf(' ')
    if ($sp -lt 0) { $cmd = $line; $arg = '' } else { $cmd = $line.Substring(0, $sp); $arg = $line.Substring($sp + 1) }
    try {
        switch ($cmd) {
            'play' { if ($arg) { $player.SoundLocation = $arg; $player.Load(); $player.Play() } }
            'loop' { if ($arg) { $player.SoundLocation = $arg; $player.Load(); $player.PlayLooping() } }
            'stop' { $player.Stop() }
            'say'  { if ($synth -and $arg) { $synth.Speak($arg) } }
            'rate' { if ($synth) { $synth.Rate = [Math]::Max(-10, [Math]::Min(10, [int]$arg)) } }
        }
    } catch { }
    [Console]::Out.WriteLine('ok')
    [Console]::Out.Flush()
}
$player.Stop()
if ($synth) { $synth.Dispose() }
