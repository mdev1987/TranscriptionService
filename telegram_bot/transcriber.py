import wave
import json
import os
from vosk import Model, KaldiRecognizer

def format_timestamp(seconds):
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    millis = int(seconds * 1000)
    hours = millis // 3600000
    minutes = (millis % 3600000) // 60000
    seconds = (millis % 60000) // 1000
    milliseconds = millis % 1000
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

def transcribe_audio(model_path, audio_path):
    # Load the Vosk model
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model path '{model_path}' does not exist.")
    model = Model(model_path)

    # Open the audio file
    wf = wave.open(audio_path, "rb")

    # Check audio format
    if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 16000:
        raise ValueError("Audio file must be WAV format mono PCM with a sample rate of 16kHz.")

    # Initialize the recognizer
    rec = KaldiRecognizer(model, wf.getframerate())
    rec.SetWords(True)

    # Process the audio file
    results = []
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            results.append(json.loads(rec.Result()))
    results.append(json.loads(rec.FinalResult()))

    return results

def write_transcripts(results, txt_filename, srt_filename, max_words=10, max_duration=5.0):
    with open(txt_filename, "w", encoding="utf-8") as txt_file, open(srt_filename, "w", encoding="utf-8") as srt_file:
        srt_counter = 1
        segment = []
        segment_start = None
        segment_end = None

        for res in results:
            if 'result' in res:
                for word_info in res['result']:
                    if segment_start is None:
                        segment_start = word_info['start']
                    segment_end = word_info['end']
                    segment.append(word_info['word'])

                    # Check if the segment meets criteria for splitting
                    if len(segment) >= max_words or (segment_end - segment_start) >= max_duration:
                        start_time = format_timestamp(segment_start)
                        end_time = format_timestamp(segment_end)
                        srt_file.write(f"{srt_counter}\n{start_time} --> {end_time}\n{' '.join(segment)}\n\n")
                        txt_file.write(' '.join(segment) + ' ')
                        srt_counter += 1
                        segment = []
                        segment_start = None

        # Write any remaining words as the last segment
        if segment:
            start_time = format_timestamp(segment_start)
            end_time = format_timestamp(segment_end)
            srt_file.write(f"{srt_counter}\n{start_time} --> {end_time}\n{' '.join(segment)}\n\n")
            txt_file.write(' '.join(segment) + ' ')
