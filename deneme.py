# -*- coding: utf-8 -*-
"""Self-test ve ekran görüntüsü için Türkçe deneme kaydı üretir (Windows konuşma sentezi)."""
import os
import subprocess

DENEME_METNI = (
    "Merhaba, bu bir deneme kaydıdır. Video transkript uygulaması Türkçe konuşmayı yazıya döküyor. "
    "Her cümlenin başladığı ve bittiği saniye ekranda canlı olarak görünüyor. "
    "İşlem bilgisayarın üzerinde yapılır, internete ses gönderilmez. "
    "Sonuçlar düz metin, zaman damgalı metin ve altyazı dosyası olarak kaydedilir."
)

_PS_TTS = r"""
$ErrorActionPreference = 'Stop'
$out = $args[0]; $metin = [IO.File]::ReadAllText($args[1], [Text.Encoding]::UTF8)
try {
  Add-Type -AssemblyName System.Runtime.WindowsRuntime
  $null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media, ContentType = WindowsRuntime]
  $null = [Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime]
  $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
  function Await($op, $t) { $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $task.Wait(-1) | Out-Null; $task.Result }
  $synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
  $v = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | Where-Object { $_.Language -eq 'tr-TR' } | Select-Object -First 1
  if ($v) { $synth.Voice = $v }
  $stream = Await ($synth.SynthesizeTextToStreamAsync($metin)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
  $size = [uint32]$stream.Size
  $reader = New-Object Windows.Storage.Streams.DataReader($stream.GetInputStreamAt(0))
  $null = Await ($reader.LoadAsync($size)) ([uint32])
  $bytes = New-Object byte[] $size; $reader.ReadBytes($bytes)
  [IO.File]::WriteAllBytes($out, $bytes)
  "OneCore: " + $(if ($v) { $v.DisplayName } else { 'varsayilan' })
} catch {
  Add-Type -AssemblyName System.Speech
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $s.SetOutputToWaveFile($out); $s.Speak($metin); $s.Dispose()
  "SAPI"
}
"""


def ornek_ses_uret(hedef_wav, metin=DENEME_METNI):
    """Windows'un Türkçe sesiyle (Tolga) deneme kaydı üretir."""
    klasor = os.path.dirname(hedef_wav)
    ps = os.path.join(klasor, "_tts.ps1")
    txt = os.path.join(klasor, "_tts.txt")
    with open(ps, "w", encoding="utf-8-sig") as f:
        f.write(_PS_TTS)
    with open(txt, "w", encoding="utf-8") as f:
        f.write(metin)
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps, hedef_wav, txt],
        capture_output=True, text=True, timeout=120,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if not os.path.isfile(hedef_wav) or os.path.getsize(hedef_wav) < 1000:
        raise RuntimeError("Deneme sesi üretilemedi: " + (r.stderr or r.stdout).strip()[:400])
    return (r.stdout or "").strip()
