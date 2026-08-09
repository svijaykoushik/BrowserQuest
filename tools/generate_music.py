#!/usr/bin/env python3
"""
Ultimate 8-Bit Chiptune RPG Soundtrack Generator for BrowserQuest
Features:
- Multi-waveform synthesis (sine, triangle, sawtooth, pulse with variable duty, noise)
- Instrument modeling (flute, pulse, triangle, chime, brass, saw)
- 12dB/octave low-pass 2-pole IIR filtering
- Stereo ping-pong delay (echo) and bitcrushing
- Constant-power stereo panning across lead, chords, bass, and percussion
- Full 6-voice retro drum engine (Kick, Snare, Closed Hat, Open Hat, Tom, Crash)
- Anti-clipping soft-clip limiter with guaranteed encoder headroom (zero clipping)
"""

import os
import math
import struct
import wave
import subprocess

SAMPLE_RATE = 44100
PI2 = math.pi * 2.0
HEADROOM_PEAK = 0.80  # Guarantees ~ -1.94 dBFS headroom to prevent lossy MP3/OGG inter-sample clipping

# Waveform Library
class Wave:
    @staticmethod
    def sine(phase):
        return math.sin(phase)

    @staticmethod
    def triangle(phase):
        t = phase / PI2
        f = t - math.floor(t)
        return -1.0 + 4.0 * f if f < 0.5 else 3.0 - 4.0 * f

    @staticmethod
    def sawtooth(phase):
        t = phase / PI2
        return 2.0 * (t - math.floor(t)) - 1.0

    @staticmethod
    def pulse(phase, duty=0.25):
        t = phase / PI2
        return 1.0 if (t - math.floor(t)) < duty else -1.0

    @staticmethod
    def noise(seed):
        seed = (seed * 1103515245 + 12345) & 0x7fffffff
        val = (seed / 0x40000000) - 1.0
        return val, seed

def note_freq(note, cents=0.0):
    """Converts note string like 'C4', 'D#5', 'Ab3' to frequency in Hz."""
    if not note:
        return 0.0
    notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    flat_map = {'Db': 'C#', 'Eb': 'D#', 'Gb': 'F#', 'Ab': 'G#', 'Bb': 'A#'}
    
    if len(note) >= 3 and (note[1] == '#' or note[1] == 'b'):
        n = note[:2]
        octave = int(note[2:])
    else:
        n = note[0]
        octave = int(note[1:])
        
    n = flat_map.get(n, n)
    if n not in notes:
        return 0.0
    semi = notes.index(n)
    midi = 12 * (octave + 1) + semi
    return 440.0 * (2.0 ** ((midi - 69.0 + cents / 100.0) / 12.0))

def adsr(t, dur, a=0.03, d=0.06, s=0.7, r=0.05):
    """
    Smooth ADSR envelope with cosine curve transitions to eliminate clicks and pops.
    """
    a = max(0.01, a)
    r = max(0.02, r)
    if t < 0 or t >= dur:
        return 0.0
    if dur < a + r:
        a = dur * 0.3
        r = dur * 0.4
        d = max(0.005, dur - a - r)
    if t >= dur - r:
        p = (t - (dur - r)) / r
        return s * 0.5 * (1.0 + math.cos(math.pi * p))
    if t < a:
        return 0.5 * (1.0 - math.cos(math.pi * (t / a)))
    if t < a + d:
        p = (t - a) / d
        return 1.0 - (1.0 - s) * p
    return s

def lowpass(buf, cutoff, sample_rate=SAMPLE_RATE):
    """12dB/octave Lowpass filter (2-pass IIR forward)."""
    if cutoff <= 0 or cutoff >= sample_rate / 2.0:
        return buf[:]
    dt = 1.0 / sample_rate
    rc = 1.0 / (PI2 * cutoff)
    alpha = dt / (rc + dt)
    out = [0.0] * len(buf)
    y1 = 0.0
    y2 = 0.0
    for i in range(len(buf)):
        y1 += alpha * (buf[i] - y1)
        y2 += alpha * (y1 - y2)
        out[i] = y2
    return out

def stereo_delay(input_l, input_r, delay_sec, feedback=0.4, mix=0.2, sample_rate=SAMPLE_RATE):
    """Stereo Ping-Pong Delay / Echo."""
    delay_samples = int(delay_sec * sample_rate)
    if delay_samples < 1:
        return input_l[:], input_r[:]
    length = len(input_l)
    out_l = [0.0] * length
    out_r = [0.0] * length
    buf_l = [0.0] * delay_samples
    buf_r = [0.0] * delay_samples
    write_idx = 0

    for i in range(length):
        delayed_l = buf_l[write_idx]
        delayed_r = buf_r[write_idx]

        buf_l[write_idx] = input_l[i] + delayed_r * feedback
        buf_r[write_idx] = input_r[i] + delayed_l * feedback

        out_l[i] = input_l[i] + delayed_l * mix
        out_r[i] = input_r[i] + delayed_r * mix

        write_idx = (write_idx + 1) % delay_samples

    return out_l, out_r

def bitcrush(buf, bits=16, downsample=1):
    """Bitcrush and sample-rate reduction effect."""
    if bits >= 16 and downsample <= 1:
        return buf[:]
    levels = 2.0 ** (bits - 1)
    length = len(buf)
    out = [0.0] * length
    hold = 0.0
    for i in range(length):
        if i % downsample == 0:
            hold = round(buf[i] * levels) / levels
        out[i] = hold
    return out

def soft_clip(buf, threshold=0.80):
    """Rational smooth soft-clipping limiter: guaranteed output strictly bounded by threshold."""
    out = [0.0] * len(buf)
    for i in range(len(buf)):
        x = buf[i] / threshold
        out[i] = threshold * (x / (1.0 + abs(x)))
    return out

def pan_gain(pan):
    """Constant-power stereo panning law."""
    angle = (pan + 1.0) * math.pi / 4.0
    return math.cos(angle), math.sin(angle)

# Master Synthesizer Track Renderer
def render_track(config):
    bpm = config.get('bpm', 120)
    num_bars = config.get('numBars', 8)
    beats_per_bar = config.get('beatsPerBar', 4)
    lead = config.get('lead', [])
    chords = config.get('chords', [])
    bass = config.get('bass', [])
    drums = config.get('drums', [])
    
    lead_type = config.get('leadType', 'triangle')
    lead_cutoff = config.get('leadCutoff', 2400.0)
    chord_cutoff = config.get('chordCutoff', 2000.0)
    bass_cutoff = config.get('bassCutoff', 1000.0)
    
    lead_pan = config.get('leadPan', 0.0)
    chord_pan = config.get('chordPan', 0.0)
    bass_pan = config.get('bassPan', 0.0)
    drum_pan = config.get('drumPan', 0.0)
    
    echo_delay = config.get('echoDelay', 0.0)
    echo_mix = config.get('echoMix', 0.0)
    bit_depth = config.get('bitDepth', 16)
    downsample = config.get('downsample', 1)

    beat_dur = 60.0 / bpm
    bar_dur = beat_dur * beats_per_bar
    total_dur = num_bars * bar_dur
    total_samples = int(total_dur * SAMPLE_RATE)

    lead_l = [0.0] * total_samples
    lead_r = [0.0] * total_samples
    chord_l = [0.0] * total_samples
    chord_r = [0.0] * total_samples
    bass_l = [0.0] * total_samples
    bass_r = [0.0] * total_samples
    drum_l = [0.0] * total_samples
    drum_r = [0.0] * total_samples

    noise_seed = 42

    # 1. Lead Melody Channel
    lp_l, lp_r = pan_gain(lead_pan)
    for note, start_beat, dur_beats in lead:
        if not note: continue
        freq = note_freq(note)
        start_time = start_beat * beat_dur
        dur_time = dur_beats * beat_dur
        start_idx = int(start_time * SAMPLE_RATE)
        end_idx = min(total_samples, int((start_time + dur_time) * SAMPLE_RATE))

        for i in range(start_idx, end_idx):
            t = (i - start_idx) / SAMPLE_RATE
            env = adsr(t, dur_time, 0.08, 0.12, 0.80, 0.15)
            vib = 1.0 + 0.005 * math.sin(PI2 * 5.0 * t)
            phase = PI2 * freq * vib * t

            if lead_type == 'triangle':
                s = Wave.triangle(phase)
            elif lead_type == 'flute':
                s = Wave.sine(phase) * 0.85 + Wave.triangle(phase) * 0.15
            elif lead_type == 'pulse':
                s = Wave.pulse(phase, 0.25)
            elif lead_type == 'saw':
                s = Wave.sawtooth(phase)
            elif lead_type == 'chime':
                s = Wave.sine(phase) * 0.80 + Wave.triangle(phase * 2.0) * 0.20
            elif lead_type == 'brass':
                s = Wave.sawtooth(phase) * 0.60 + Wave.pulse(phase, 0.30) * 0.40
            else:
                s = Wave.triangle(phase) * 0.70 + Wave.pulse(phase, 0.25) * 0.30

            lead_l[i] += s * env * 0.30 * lp_l
            lead_r[i] += s * env * 0.30 * lp_r

    # 2. Chords & Arpeggio Channel
    cp_l, cp_r = pan_gain(chord_pan)
    for start_bar, chord_prog in chords:
        for c_idx, chord in enumerate(chord_prog):
            c_start = (start_bar + c_idx) * bar_dur
            c_samples = int(bar_dur * SAMPLE_RATE)
            arp_speed = beat_dur / 4.0  # 16th-note arpeggio

            for i in range(c_samples):
                idx = int(c_start * SAMPLE_RATE) + i
                if idx >= total_samples: break
                t_chord = i / SAMPLE_RATE
                t_arp = t_chord % arp_speed
                note_idx = int(t_chord / arp_speed) % len(chord)
                freq = note_freq(chord[note_idx])
                env = adsr(t_arp, arp_speed, 0.02, 0.04, 0.60, 0.04)
                phase = PI2 * freq * t_arp
                sample = Wave.pulse(phase, 0.20) * 0.50 + Wave.triangle(phase) * 0.50

                chord_l[idx] += sample * env * 0.15 * cp_l
                chord_r[idx] += sample * env * 0.15 * cp_r

    # 3. Bass Line Channel
    bp_l, bp_r = pan_gain(bass_pan)
    for note, start_beat, dur_beats in bass:
        if not note: continue
        freq = note_freq(note)
        start_time = start_beat * beat_dur
        dur_time = dur_beats * beat_dur
        start_idx = int(start_time * SAMPLE_RATE)
        end_idx = min(total_samples, int((start_time + dur_time) * SAMPLE_RATE))

        for i in range(start_idx, end_idx):
            t = (i - start_idx) / SAMPLE_RATE
            env = adsr(t, dur_time, 0.03, 0.08, 0.75, 0.05)
            phase = PI2 * freq * t
            s = Wave.sine(phase) * 0.90 + Wave.triangle(phase) * 0.10

            bass_l[i] += s * env * 0.35 * bp_l
            bass_r[i] += s * env * 0.35 * bp_r

    # 4. Multi-Voice Drum Channel
    dp_l, dp_r = pan_gain(drum_pan)
    if drums:
        total_steps = num_bars * beats_per_bar * 4
        step_dur = beat_dur / 4.0
        for step in range(total_steps):
            d_type = drums[step % len(drums)]
            if not d_type: continue
            start_time = step * step_dur
            start_idx = int(start_time * SAMPLE_RATE)

            if d_type == 'K':  # Kick
                dur = 0.10
                end_idx = min(total_samples, start_idx + int(dur * SAMPLE_RATE))
                for i in range(start_idx, end_idx):
                    t = (i - start_idx) / SAMPLE_RATE
                    f = max(30.0, 120.0 * ((1.0 - t / dur) ** 2.5))
                    env = (1.0 - t / dur) ** 2.0
                    s = Wave.sine(PI2 * f * t) * env * 0.50
                    drum_l[i] += s * dp_l
                    drum_r[i] += s * dp_r
            elif d_type == 'S':  # Snare
                dur = 0.12
                end_idx = min(total_samples, start_idx + int(dur * SAMPLE_RATE))
                for i in range(start_idx, end_idx):
                    t = (i - start_idx) / SAMPLE_RATE
                    env = (1.0 - t / dur) ** 1.5
                    tone = Wave.sine(PI2 * 180.0 * t) * 0.30
                    n_val, noise_seed = Wave.noise(noise_seed)
                    s = (tone + n_val * 0.70) * env * 0.25
                    drum_l[i] += s * dp_l
                    drum_r[i] += s * dp_r
            elif d_type == 'H':  # Closed Hat
                dur = 0.04
                end_idx = min(total_samples, start_idx + int(dur * SAMPLE_RATE))
                for i in range(start_idx, end_idx):
                    t = (i - start_idx) / SAMPLE_RATE
                    env = (1.0 - t / dur) ** 3.0
                    n_val, noise_seed = Wave.noise(noise_seed)
                    s = n_val * env * 0.12
                    drum_l[i] += s * dp_l
                    drum_r[i] += s * dp_r
            elif d_type == 'O':  # Open Hat
                dur = 0.15
                end_idx = min(total_samples, start_idx + int(dur * SAMPLE_RATE))
                for i in range(start_idx, end_idx):
                    t = (i - start_idx) / SAMPLE_RATE
                    env = (1.0 - t / dur) ** 2.0
                    n_val, noise_seed = Wave.noise(noise_seed)
                    s = n_val * env * 0.10
                    drum_l[i] += s * dp_l
                    drum_r[i] += s * dp_r
            elif d_type == 'T':  # Tom
                dur = 0.10
                end_idx = min(total_samples, start_idx + int(dur * SAMPLE_RATE))
                for i in range(start_idx, end_idx):
                    t = (i - start_idx) / SAMPLE_RATE
                    f = max(40.0, 80.0 * ((1.0 - t / dur) ** 2.0))
                    env = (1.0 - t / dur) ** 1.5
                    s = Wave.sine(PI2 * f * t) * env * 0.35
                    drum_l[i] += s * dp_l
                    drum_r[i] += s * dp_r
            elif d_type == 'C':  # Crash / Cymbal
                dur = 0.08
                end_idx = min(total_samples, start_idx + int(dur * SAMPLE_RATE))
                for i in range(start_idx, end_idx):
                    t = (i - start_idx) / SAMPLE_RATE
                    env = (1.0 - t / dur) ** 1.2
                    n_val, noise_seed = Wave.noise(noise_seed)
                    s = n_val * env * 0.20
                    drum_l[i] += s * dp_l
                    drum_r[i] += s * dp_r

    # Channel Filtering
    lead_fl = lowpass(lead_l, lead_cutoff)
    lead_fr = lowpass(lead_r, lead_cutoff)
    chord_fl = lowpass(chord_l, chord_cutoff)
    chord_fr = lowpass(chord_r, chord_cutoff)
    bass_fl = lowpass(bass_l, bass_cutoff)
    bass_fr = lowpass(bass_r, bass_cutoff)
    drum_fl = lowpass(drum_l, 4000.0)
    drum_fr = lowpass(drum_r, 4000.0)

    # Master Mixing
    vol_lead = 0.90
    vol_chord = 0.70
    vol_bass = 0.85
    vol_drum = 0.80

    mix_l = [0.0] * total_samples
    mix_r = [0.0] * total_samples
    for i in range(total_samples):
        mix_l[i] = lead_fl[i] * vol_lead + chord_fl[i] * vol_chord + bass_fl[i] * vol_bass + drum_fl[i] * vol_drum
        mix_r[i] = lead_fr[i] * vol_lead + chord_fr[i] * vol_chord + bass_fr[i] * vol_bass + drum_fr[i] * vol_drum

    # Stereo Ping-Pong Delay
    if echo_delay > 0.0 and echo_mix > 0.0:
        mix_l, mix_r = stereo_delay(mix_l, mix_r, echo_delay, 0.40, echo_mix)

    # Bitcrusher
    if bit_depth < 16 or downsample > 1:
        mix_l = bitcrush(mix_l, bit_depth, downsample)
        mix_r = bitcrush(mix_r, bit_depth, downsample)

    # Master Peak Limiting & Headroom Protection (Eliminates clipping)
    peak = 0.0
    for i in range(total_samples):
        peak = max(peak, abs(mix_l[i]), abs(mix_r[i]))

    if peak > 0.85:
        scale = 0.85 / peak
        for i in range(total_samples):
            mix_l[i] *= scale
            mix_r[i] *= scale

    final_l = soft_clip(mix_l, HEADROOM_PEAK)
    final_r = soft_clip(mix_r, HEADROOM_PEAK)

    return final_l, final_r

def save_wav_stereo(left, right, filename):
    """Writes 16-bit PCM Stereo WAV file."""
    with wave.open(filename, 'w') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        frames = bytearray()
        length = min(len(left), len(right))
        for i in range(length):
            vl = int(left[i] * 32767.0)
            vr = int(right[i] * 32767.0)
            vl = max(-32767, min(32767, vl))
            vr = max(-32767, min(32767, vr))
            frames.extend(struct.pack('<hh', vl, vr))
        wf.writeframes(frames)

# ==================== TRACK DATABASE ====================

TRACK_DB = {
    'title': {
        'name': "Title Theme",
        'meta': "128 BPM, C Major • Heroic",
        'bpm': 128, 'numBars': 8, 'beatsPerBar': 4,
        'leadType': 'pulse', 'leadCutoff': 3000.0, 'bassCutoff': 1200.0, 'chordCutoff': 2200.0,
        'leadPan': 0.2, 'bassPan': 0.0, 'chordPan': -0.1, 'drumPan': 0.0,
        'echoDelay': 0.30, 'echoMix': 0.15,
        'lead': [
            ('C5',0,0.5),('E5',0.5,0.5),('G5',1,0.5),('C6',1.5,1),('G5',2.5,0.5),('E5',3,0.5),('C5',3.5,0.5),
            ('D5',4,0.5),('F5',4.5,0.5),('A5',5,0.5),('D6',5.5,1),('A5',6.5,0.5),('F5',7,0.5),('D5',7.5,0.5),
            ('E5',8,0.5),('G5',8.5,0.5),('C6',9,0.5),('E6',9.5,1),('C6',10.5,0.5),('G5',11,0.5),('E5',11.5,0.5),
            ('F5',12,0.5),('A5',12.5,0.5),('C6',13,0.5),('F6',13.5,1),('C6',14.5,0.5),('A5',15,0.5),('F5',15.5,0.5),
            ('C5',16,0.5),('E5',16.5,0.5),('G5',17,0.5),('C6',17.5,1),('G5',18.5,0.5),('E5',19,0.5),('C5',19.5,0.5),
            ('A4',20,0.5),('C5',20.5,0.5),('E5',21,0.5),('A5',21.5,1),('E5',22.5,0.5),('C5',23,0.5),('A4',23.5,0.5),
            ('G4',24,0.5),('B4',24.5,0.5),('D5',25,0.5),('G5',25.5,1),('D5',26.5,0.5),('B4',27,0.5),('G4',27.5,0.5),
            ('C5',28,1),('E5',29,1),('G5',30,1),('C6',31,1)
        ],
        'chords': [
            (0, [
                ['C4','E4','G4','C5'],
                ['G3','B3','D4','G4'],
                ['A3','C4','E4','A4'],
                ['F3','A3','C4','F4'],
                ['C4','E4','G4','C5'],
                ['G3','B3','D4','G4'],
                ['D3','F3','A3','D4'],
                ['C4','E4','G4','C5']
            ])
        ],
        'bass': [
            ('C2',0,2),('C3',2,1),('G2',3,1),('D2',4,2),('D3',6,1),('A2',7,1),
            ('E2',8,2),('E3',10,1),('B2',11,1),('F2',12,2),('F3',14,1),('C3',15,1),
            ('C2',16,2),('C3',18,1),('G2',19,1),('A2',20,2),('A3',22,1),('E3',23,1),
            ('G2',24,2),('G3',26,1),('D3',27,1),('C2',28,4)
        ],
        'drums': ['K',None,'H',None,'S',None,'H',None,'K','H','K',None,'S',None,'H',None]
    },
    'village': {
        'name': "Village",
        'meta': "100 BPM, C Major • Peaceful",
        'bpm': 100, 'numBars': 8, 'beatsPerBar': 4,
        'leadType': 'flute', 'leadCutoff': 2500.0, 'bassCutoff': 1000.0, 'chordCutoff': 2000.0,
        'leadPan': 0.0, 'bassPan': 0.0, 'chordPan': -0.2, 'drumPan': 0.0,
        'echoDelay': 0.40, 'echoMix': 0.20,
        'lead': [
            ('E4',0,1),('G4',1,1),('A4',2,0.5),('G4',2.5,0.5),('E4',3,1),
            ('D4',4,1),('E4',5,1),('C4',6,2),
            ('G4',8,1),('A4',9,1),('C5',10,0.5),('A4',10.5,0.5),('G4',11,1),
            ('F4',12,1),('G4',13,1),('E4',14,2),
            ('E4',16,1),('G4',17,1),('C5',18,1.5),('D5',19.5,0.5),
            ('E5',20,1),('D5',21,1),('C5',22,2),
            ('A4',24,1),('C5',25,1),('G4',26,1.5),('E4',27.5,0.5),
            ('F4',28,1),('G4',29,1),('C5',30,2)
        ],
        'chords': [
            (0, [
                ['C4','E4','G4','C5'],
                ['F3','A3','C4','F4'],
                ['G3','B3','D4','G4'],
                ['C4','E4','G4','C5'],
                ['C4','E4','G4','C5'],
                ['F3','A3','C4','F4'],
                ['G3','B3','D4','G4'],
                ['C4','E4','G4','C5']
            ])
        ],
        'bass': [
            ('C2',0,2),('G2',2,2),('A2',4,2),('F2',6,2),
            ('C2',8,2),('G2',10,2),('A2',12,2),('F2',14,2),
            ('C2',16,2),('G2',18,2),('A2',20,2),('F2',22,2),
            ('C2',24,2),('G2',26,2),('F2',28,2),('C2',30,2)
        ],
        'drums': ['K',None,None,None,None,None,'H',None,'K',None,None,None,None,None,'H',None]
    },
    'forest': {
        'name': "Forest",
        'meta': "112 BPM, E Minor • Mysterious",
        'bpm': 112, 'numBars': 8, 'beatsPerBar': 4,
        'leadType': 'triangle', 'leadCutoff': 2400.0, 'bassCutoff': 900.0, 'chordCutoff': 2000.0,
        'leadPan': -0.1, 'bassPan': 0.0, 'chordPan': 0.1, 'drumPan': 0.0,
        'echoDelay': 0.35, 'echoMix': 0.25,
        'lead': [
            ('E4',0,1),('B4',1,1),('A4',2,1),('G4',3,1),('F#4',4,1),('E4',5,1),('D4',6,1),('E4',7,1),
            ('B4',8,1),('C5',9,1),('B4',10,1),('A4',11,1),('G4',12,1),('F#4',13,1),('E4',14,2),
            ('E4',16,1),('G4',17,1),('A4',18,1),('B4',19,1),('C5',20,1),('B4',21,1),('A4',22,1),('G4',23,1),
            ('F#4',24,1),('G4',25,1),('A4',26,1),('B4',27,1),('C5',28,2),('B4',30,2)
        ],
        'chords': [
            (0, [
                ['E3','G3','B3','E4'],
                ['C3','E3','G3','C4'],
                ['D3','F#3','A3','D4'],
                ['B2','D3','F#3','B3'],
                ['E3','G3','B3','E4'],
                ['A2','C3','E3','A3'],
                ['D3','F#3','A3','D4'],
                ['E3','G3','B3','E4']
            ])
        ],
        'bass': [
            ('E2',0,2),('B2',2,2),('C2',4,2),('G2',6,2),
            ('A2',8,2),('E2',10,2),('D2',12,2),('E2',14,2),
            ('E2',16,2),('B2',18,2),('C2',20,2),('G2',22,2),
            ('A2',24,2),('E2',26,2),('D2',28,2),('E2',30,2)
        ],
        'drums': ['T',None,None,None,'T',None,None,None,'T',None,'T',None,'T',None,None,None]
    },
    'beach': {
        'name': "Beach",
        'meta': "96 BPM, G Major • Tropical",
        'bpm': 96, 'numBars': 8, 'beatsPerBar': 4,
        'leadType': 'pulse', 'leadCutoff': 2200.0, 'bassCutoff': 900.0, 'chordCutoff': 2000.0,
        'leadPan': 0.2, 'bassPan': 0.0, 'chordPan': -0.1, 'drumPan': 0.0,
        'echoDelay': 0.50, 'echoMix': 0.20,
        'lead': [
            ('B4',0,1.5),('D5',1.5,0.5),('E5',2,1),('D5',3,1),('B4',4,1.5),('A4',5.5,0.5),('G4',6,2),
            ('D5',8,1.5),('E5',9.5,0.5),('G5',10,1),('E5',11,1),('D5',12,1.5),('B4',13.5,0.5),('G4',14,2),
            ('B4',16,1),('D5',17,1),('G5',18,1),('A5',19,1),('B5',20,1),('A5',21,1),('G5',22,1),('E5',23,1),
            ('D5',24,1),('E5',25,1),('G5',26,1),('B5',27,1),('G5',28,4)
        ],
        'chords': [
            (0, [
                ['G3','B3','D4','G4'],
                ['C4','E4','G4','C5'],
                ['D3','F#3','A3','D4'],
                ['E3','G3','B3','E4'],
                ['C4','E4','G4','C5'],
                ['G3','B3','D4','G4'],
                ['D3','F#3','A3','D4'],
                ['G3','B3','D4','G4']
            ])
        ],
        'bass': [
            ('G2',0,1.5),('G2',1.5,0.5),('C2',2,1.5),('C2',3.5,0.5),('D2',4,1.5),('D2',5.5,0.5),('G2',6,2),
            ('G2',8,1.5),('G2',9.5,0.5),('C2',10,1.5),('C2',11.5,0.5),('D2',12,1.5),('D2',13.5,0.5),('G2',14,2),
            ('G2',16,1),('B2',17,1),('D3',18,1),('G3',19,1),('F#3',20,1),('E3',21,1),('D3',22,1),('C3',23,1),
            ('B2',24,1),('C3',25,1),('D3',26,1),('F#3',27,1),('G3',28,4)
        ],
        'drums': ['K',None,None,'H',None,None,'K','H',None,None,'K',None,'H',None,None,None]
    },
    'cave': {
        'name': "Cave",
        'meta': "88 BPM, D Minor • Dark & Echoing",
        'bpm': 88, 'numBars': 8, 'beatsPerBar': 4,
        'leadType': 'pulse', 'leadCutoff': 2000.0, 'bassCutoff': 800.0, 'chordCutoff': 1800.0,
        'leadPan': 0.0, 'bassPan': 0.0, 'chordPan': 0.0, 'drumPan': 0.0,
        'echoDelay': 0.60, 'echoMix': 0.30, 'bitDepth': 12, 'downsample': 1,
        'lead': [
            ('D4',0,1),('F4',1,1),('E4',2,1),('D4',3,1),('C4',4,1),('D4',5,1),('A3',6,2),
            ('D4',8,1),('F4',9,1),('G4',10,1),('A4',11,1),('G4',12,1),('F4',13,1),('E4',14,2),
            ('D4',16,1),('A4',17,1),('G4',18,1),('F4',19,1),('E4',20,1),('D4',21,1),('C4',22,1),('D4',23,1),
            ('F4',24,1),('E4',25,1),('D4',26,1),('C4',27,1),('D4',28,4)
        ],
        'chords': [
            (0, [
                ['D3','F3','A3','D4'],
                ['Bb2','D3','F3','Bb3'],
                ['F2','A2','C3','F3'],
                ['C3','E3','G3','C4'],
                ['D3','F3','A3','D4'],
                ['Bb2','D3','F3','Bb3'],
                ['C3','E3','G3','C4'],
                ['D3','F3','A3','D4']
            ])
        ],
        'bass': [
            ('D2',0,4),('A2',4,4),('D2',8,4),('G2',12,4),
            ('D2',16,4),('A2',20,4),('C2',24,4),('D2',28,4)
        ],
        'drums': ['K',None,None,None,'K',None,'S',None,'K',None,'K',None,'S',None,'H','H']
    },
    'desert': {
        'name': "Desert",
        'meta': "110 BPM, E Harmonic Minor • Exotic",
        'bpm': 110, 'numBars': 8, 'beatsPerBar': 4,
        'leadType': 'pulse', 'leadCutoff': 2600.0, 'bassCutoff': 1100.0, 'chordCutoff': 2200.0,
        'leadPan': 0.15, 'bassPan': 0.0, 'chordPan': -0.15, 'drumPan': 0.0,
        'echoDelay': 0.35, 'echoMix': 0.20,
        'lead': [
            ('E4',0,1.0),('F4',1.0,1.0),('G#4',2.0,1.0),('A4',3.0,1.0),
            ('B4',4.0,1.5),('C5',5.5,0.5),('B4',6.0,1.0),('A4',7.0,1.0),
            ('G#4',8.0,1.5),('F4',9.5,0.5),('E4',10.0,2.0),
            ('F4',12.0,1.0),('G#4',13.0,1.0),('E4',14.0,2.0),
            ('E5',16.0,1.0),('F5',17.0,1.0),('E5',18.0,1.0),('D5',19.0,1.0),
            ('C5',20.0,1.5),('B4',21.5,0.5),('A4',22.0,2.0),
            ('G#4',24.0,1.0),('A4',25.0,1.0),('B4',26.0,1.0),('G#4',27.0,1.0),
            ('E4',28.0,4.0)
        ],
        'chords': [
            (0, [
                ['E3','G#3','B3','E4'],
                ['F3','A3','C4','F4'],
                ['E3','G#3','B3','E4'],
                ['D3','F3','A3','D4'],
                ['A3','C4','E4','A4'],
                ['F3','A3','C4','F4'],
                ['G#3','B3','D4','E4'],
                ['E3','G#3','B3','E4']
            ])
        ],
        'bass': [
            ('E2',0,1.5),('E2',1.5,0.5),('B2',2,1),('E3',3,1),
            ('F2',4,1.5),('F2',5.5,0.5),('C3',6,1),('F3',7,1),
            ('E2',8,1.5),('E2',9.5,0.5),('B2',10,1),('E3',11,1),
            ('D2',12,1.5),('D2',13.5,0.5),('A2',14,1),('D3',15,1),
            ('A2',16,1.5),('A2',17.5,0.5),('E3',18,1),('A3',19,1),
            ('F2',20,1.5),('F2',21.5,0.5),('C3',22,1),('F3',23,1),
            ('E2',24,1.5),('E2',25.5,0.5),('G#2',26,1),('B2',27,1),
            ('E2',28,4)
        ],
        'drums': ['K','H','H','K','S','H','K','H','K','H','H','K','S','H','H','H']
    },
    'lavaland': {
        'name': "Lavaland",
        'meta': "120 BPM, C Chromatic • Intense & Dark",
        'bpm': 120, 'numBars': 8, 'beatsPerBar': 4,
        'leadType': 'pulse', 'leadCutoff': 2400.0, 'bassCutoff': 950.0, 'chordCutoff': 2000.0,
        'leadPan': -0.15, 'bassPan': 0.0, 'chordPan': 0.15, 'drumPan': 0.0,
        'echoDelay': 0.28, 'echoMix': 0.22, 'bitDepth': 12, 'downsample': 1,
        'lead': [
            ('C4',0,1.0),('Eb4',1.0,1.0),('F#4',2.0,1.0),('G4',3.0,1.0),
            ('Ab4',4.0,1.5),('G4',5.5,0.5),('Eb4',6.0,2.0),
            ('D4',8.0,1.0),('F#4',9.0,1.0),('Ab4',10.0,1.5),('G4',11.5,0.5),
            ('Eb4',12.0,2.0),('C4',14.0,2.0),
            ('G4',16.0,1.0),('Bb4',17.0,1.0),('Db5',18.0,1.5),('D5',19.5,0.5),
            ('C5',20.0,1.5),('Ab4',21.5,0.5),('G4',22.0,2.0),
            ('Eb4',24.0,1.0),('G4',25.0,1.0),('F#4',26.0,1.0),('D4',27.0,1.0),
            ('C4',28.0,4.0)
        ],
        'chords': [
            (0, [
                ['C3','Eb3','G3','C4'],
                ['D3','F#3','A3','D4'],
                ['C3','Eb3','G3','C4'],
                ['Ab2','C3','Eb3','Ab3'],
                ['Eb3','G3','Bb3','Eb4'],
                ['D3','F#3','A3','D4'],
                ['Db3','F3','Ab3','Db4'],
                ['C3','Eb3','G3','C4']
            ])
        ],
        'bass': [
            ('C2',0,1),('C2',1,1),('G2',2,1),('C3',3,1),
            ('D2',4,1),('D2',5,1),('A2',6,1),('D3',7,1),
            ('C2',8,1),('C2',9,1),('G2',10,1),('C3',11,1),
            ('Ab1',12,1),('Ab1',13,1),('Eb2',14,1),('Ab2',15,1),
            ('Eb2',16,1),('Eb2',17,1),('Bb2',18,1),('Eb3',19,1),
            ('D2',20,1),('D2',21,1),('A2',22,1),('D3',23,1),
            ('Db2',24,1),('Db2',25,1),('Ab2',26,1),('Db3',27,1),
            ('C2',28,4)
        ],
        'drums': ['K','H','S','H','K','K','S','H','K','H','S','H','K','H','S','K']
    },
    'boss': {
        'name': "Boss",
        'meta': "145 BPM, A Minor • Intense",
        'bpm': 145, 'numBars': 8, 'beatsPerBar': 4,
        'leadType': 'pulse', 'leadCutoff': 3500.0, 'bassCutoff': 1200.0, 'chordCutoff': 2500.0,
        'leadPan': 0.0, 'bassPan': 0.1, 'chordPan': -0.2, 'drumPan': 0.0,
        'echoDelay': 0.20, 'echoMix': 0.10,
        'lead': [
            ('A4',0,0.5),('A4',0.5,0.25),('A4',0.75,0.25),('C5',1,0.5),('E5',1.5,0.5),('A5',2,0.5),('G#5',2.5,0.5),('E5',3,1),
            ('B5',4,0.5),('C6',4.5,0.5),('B5',5,0.5),('A5',5.5,0.5),('G5',6,0.5),('F5',6.5,0.5),('E5',7,1),
            ('A5',8,0.5),('C6',8.5,0.5),('E6',9,0.5),('D6',9.5,0.5),('C6',10,0.5),('B5',10.5,0.5),('A5',11,1),
            ('G5',12,0.5),('A5',12.5,0.5),('G5',13,0.5),('F5',13.5,0.5),('E5',14,0.5),('D5',14.5,0.5),('C5',15,1),
            ('A4',16,0.5),('C5',16.5,0.5),('E5',17,0.5),('A5',17.5,0.5),('C6',18,1),('B5',19,1),
            ('A5',20,0.5),('B5',20.5,0.5),('C6',21,0.5),('D6',21.5,0.5),('E6',22,1),('C6',23,1),
            ('B5',24,0.5),('C6',24.5,0.5),('B5',25,0.5),('A5',25.5,0.5),('G#5',26,0.5),('A5',26.5,0.5),('B5',27,1),
            ('C6',28,0.5),('B5',28.5,0.5),('A5',29,1),('E5',30,1),('A5',31,1)
        ],
        'chords': [
            (0, [
                ['A3','C4','E4','A4'],
                ['E3','G#3','B3','E4'],
                ['F3','A3','C4','F4'],
                ['D3','F3','A3','D4'],
                ['A3','C4','E4','A4'],
                ['C4','E4','G4','C5'],
                ['E3','G#3','B3','E4'],
                ['A3','C4','E4','A4']
            ])
        ],
        'bass': [
            ('A1',0,0.5),('A1',0.5,0.5),('A1',1,0.5),('A1',1.5,0.5),('E1',2,0.5),('E1',2.5,0.5),('E1',3,0.5),('E1',3.5,0.5),
            ('F1',4,0.5),('F1',4.5,0.5),('F1',5,0.5),('F1',5.5,0.5),('D1',6,0.5),('D1',6.5,0.5),('D1',7,0.5),('D1',7.5,0.5),
            ('A1',8,0.5),('A1',8.5,0.5),('A1',9,0.5),('A1',9.5,0.5),('C2',10,0.5),('C2',10.5,0.5),('C2',11,0.5),('C2',11.5,0.5),
            ('E1',12,0.5),('E1',12.5,0.5),('E1',13,0.5),('E1',13.5,0.5),('A1',14,0.5),('A1',14.5,0.5),('A1',15,0.5),('A1',15.5,0.5),
            ('A1',16,0.5),('A1',16.5,0.5),('A1',17,0.5),('A1',17.5,0.5),('C2',18,0.5),('C2',18.5,0.5),('C2',19,0.5),('C2',19.5,0.5),
            ('E1',20,0.5),('E1',20.5,0.5),('E1',21,0.5),('E1',21.5,0.5),('A1',22,0.5),('A1',22.5,0.5),('A1',23,0.5),('A1',23.5,0.5),
            ('F1',24,0.5),('F1',24.5,0.5),('F1',25,0.5),('F1',25.5,0.5),('D1',26,0.5),('D1',26.5,0.5),('D1',27,0.5),('D1',27.5,0.5),
            ('A1',28,0.5),('A1',28.5,0.5),('A1',29,0.5),('A1',29.5,0.5),('A1',30,1),('A1',31,1)
        ],
        'drums': ['K','H','S','H','K','K','S','H','K','H','S','K','K','H','S','H']
    }
}

def main():
    out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'client', 'audio', 'music')
    os.makedirs(out_dir, exist_ok=True)
    
    # 7 core game biomes used by BrowserQuest audio manager
    active_tracks = ['village', 'beach', 'forest', 'cave', 'desert', 'lavaland', 'boss']
    
    print("=" * 80)
    print("BROWSERQUEST CHIPTUNE SYNTHESIZER & MASTERING ENGINE")
    print("=" * 80)
    print(f"Sampling Rate     : {SAMPLE_RATE} Hz (16-bit PCM Stereo -> 128k MP3/OGG)")
    print(f"Master Limiter    : Soft-Clip Headroom Target = {HEADROOM_PEAK:.2f} (~ -1.94 dBFS)")
    print("Anti-Clipping     : Zero inter-sample clip / Full lossy codec protection")
    print("-" * 80)
    print(f"{'Track Key':<12} | {'Name & Meta':<35} | {'Lead Type':<10} | {'Echo Delay':<10}")
    print("-" * 80)
    for key in active_tracks:
        cfg = TRACK_DB[key]
        print(f"{key:<12} | {cfg['name'] + ' (' + cfg['meta'] + ')':<35} | {cfg.get('leadType',''):<10} | {str(cfg.get('echoDelay',0))+'s':<10}")
    print("=" * 80)
    print("\nSynthesizing tracks...\n")
    
    for key in active_tracks:
        cfg = TRACK_DB[key]
        print(f"--> Rendering [{key}] ({cfg['name']})...")
        left, right = render_track(cfg)
        
        peak_l = max(abs(s) for s in left) if left else 0.0
        peak_r = max(abs(s) for s in right) if right else 0.0
        peak = max(peak_l, peak_r)
        peak_dbfs = 20.0 * math.log10(peak) if peak > 0 else -99.0
        
        wav_path = os.path.join(out_dir, f"{key}.wav")
        mp3_path = os.path.join(out_dir, f"{key}.mp3")
        ogg_path = os.path.join(out_dir, f"{key}.ogg")
        
        save_wav_stereo(left, right, wav_path)
        
        # Convert to high-quality MP3 and OGG with FFmpeg
        subprocess.run(['ffmpeg', '-y', '-i', wav_path, '-b:a', '128k', mp3_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['ffmpeg', '-y', '-i', wav_path, '-b:a', '128k', ogg_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        os.remove(wav_path)
        print(f"    [OK] Generated {key}.mp3 and {key}.ogg (Stereo) | Peak: {peak_dbfs:.2f} dBFS ({peak:.4f}) [NO CLIPPING]\n")
        
    print("=" * 80)
    print("All soundtrack audio files generated successfully with rich stereo synthesis!")
    print("=" * 80)

if __name__ == '__main__':
    main()
