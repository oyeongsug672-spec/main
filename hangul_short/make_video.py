"""15초 한글 자음+모음 쇼츠 영상 생성기 (1080x1920, 30fps).

사용법:  python3 hangul_short/make_video.py
필요:    pip install pillow numpy imageio-ffmpeg
폰트:    hangul_short/fonts/ 에 Jua-Regular.ttf, BlackHanSans-Regular.ttf
"""
import math
import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PHOTO = ROOT / "핑크사진.png"
FONT_ROUND = HERE / "fonts" / "Jua-Regular.ttf"
FONT_BOLD = HERE / "fonts" / "BlackHanSans-Regular.ttf"
OUT = HERE / "hangul_short.mp4"
AUDIO = HERE / "music.wav"
VOICE = ROOT / "자음모음음성.m4a"
# 녹음 파일에서 잘라 쓸 구간: (원본 시작, 원본 끝, 영상에서 재생할 시각)
VOICE_CLIPS = [
    (0.30, 3.10, 0.30),                     # 인트로 인사
    (3.45, 4.10, 3.68),                     # 가
    (5.05, 5.95, 5.68),                     # 나
    (6.95, 7.60, 7.63),                     # 다
    (8.85, 9.45, 9.71),                     # 라
    (10.80, 11.60, 11.69),                  # 마
    (11.60, 13.60, 12.90),                  # 마무리 인사
]

W, H, FPS, DUR = 1080, 1920, 30, 15.0
BPM = 120
BEAT = 60 / BPM  # 0.5초

INTRO_END = 2.5
SEG = 2.0  # 한 글자당 2초 (= 1마디)
LESSONS = [
    ("ㄱ", "ㅏ", "가", "g", "a", "ga"),
    ("ㄴ", "ㅏ", "나", "n", "a", "na"),
    ("ㄷ", "ㅏ", "다", "d", "a", "da"),
    ("ㄹ", "ㅏ", "라", "r", "a", "ra"),
    ("ㅁ", "ㅏ", "마", "m", "a", "ma"),
]
OUTRO_START = INTRO_END + SEG * len(LESSONS)  # 12.5초

PINK = (249, 168, 201)
PINK_DARK = (231, 84, 148)
WHITE = (255, 255, 255)
INK = (45, 30, 60)
BLUE = (43, 99, 214)     # 자음 색
ORANGE = (255, 122, 0)   # 모음 색
PURPLE = (120, 40, 170)  # 합쳐진 글자 색


# ---------------------------------------------------------------- helpers
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out_back(t):
    t = clamp(t)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def ease_out_cubic(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


_font_cache = {}


def font(path, size):
    size = max(8, int(size))
    key = (path, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(str(path), size)
    return _font_cache[key]


def draw_text(img, text, cx, cy, size, fill, fpath=FONT_ROUND, stroke=0,
              stroke_fill=WHITE, alpha=1.0):
    if alpha <= 0 or size < 8:
        return
    f = font(fpath, size)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.text((cx, cy), text, font=f, fill=fill, anchor="mm",
           stroke_width=stroke, stroke_fill=stroke_fill)
    if alpha < 1:
        a = layer.getchannel("A").point(lambda v: int(v * alpha))
        layer.putalpha(a)
    img.alpha_composite(layer)


def rounded_card(img, cx, cy, w, h, r, fill, border=None, bw=0, alpha=1.0,
                 shadow=True):
    if alpha <= 0 or w < 2 or h < 2:
        return
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    box = [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle(
            [box[0], box[1] + 14, box[2], box[3] + 14], r, fill=(120, 20, 70, 70))
        layer.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)))
    d.rounded_rectangle(box, r, fill=fill, outline=border, width=bw)
    if alpha < 1:
        a = layer.getchannel("A").point(lambda v: int(v * alpha))
        layer.putalpha(a)
    img.alpha_composite(layer)


# ---------------------------------------------------------------- assets
photo = Image.open(PHOTO).convert("RGB")

# 전체 화면용 (세로 9:16 채우기)
_s = H / photo.height
FULL = photo.resize((int(photo.width * _s), H), Image.LANCZOS)

# 얼굴 동그라미용 (얼굴 중심 부근 정사각형 크롭)
_face = photo.crop((243, 230, 843, 830))
FACE_D = 380
_mask = Image.new("L", (FACE_D * 4, FACE_D * 4), 0)
ImageDraw.Draw(_mask).ellipse([0, 0, FACE_D * 4, FACE_D * 4], fill=255)
_mask = _mask.resize((FACE_D, FACE_D), Image.LANCZOS)
FACE = _face.resize((FACE_D, FACE_D), Image.LANCZOS).convert("RGBA")
FACE.putalpha(_mask)

# 배경 (핑크 그라데이션 + 물방울 무늬)
BG = Image.new("RGBA", (W, H))
_g = np.linspace(0, 1, H)[:, None]
_top, _bot = np.array((252, 190, 215)), np.array((246, 150, 190))
_arr = (_top * (1 - _g) + _bot * _g)[:, None, :].repeat(W, axis=1)
BG = Image.fromarray(_arr.squeeze().astype(np.uint8)).convert("RGBA")
_dots = ImageDraw.Draw(BG)
for yy in range(0, H + 120, 120):
    for xx in range(0 if (yy // 120) % 2 else 60, W + 120, 120):
        _dots.ellipse([xx - 9, yy - 9, xx + 9, yy + 9], fill=(255, 255, 255, 60))


def full_photo(t_local, zoom_from, zoom_to, dur):
    """켄 번스(천천히 확대) 효과가 들어간 전체 화면 사진."""
    z = zoom_from + (zoom_to - zoom_from) * ease_out_cubic(t_local / dur)
    fw, fh = int(FULL.width * z), int(FULL.height * z)
    im = FULL.resize((fw, fh), Image.BILINEAR)
    # 얼굴이 가운데 오도록 약간 왼쪽 기준
    cx = int(fw * 0.47)
    left = clamp(cx - W // 2, 0, fw - W)
    top = (fh - H) // 2
    return im.crop((int(left), top, int(left) + W, top + H)).convert("RGBA")


# ---------------------------------------------------------------- scenes
def scene_intro(t):
    img = full_photo(t, 1.0, 1.10, INTRO_END)
    # 아래쪽 어둡게 (자막 가독성)
    grad = Image.new("L", (1, H))
    for y in range(H):
        grad.putpixel((0, y), int(200 * clamp((y - H * 0.55) / (H * 0.45))))
    shade = Image.new("RGBA", (W, H), (60, 10, 40, 255))
    shade.putalpha(grad.resize((W, H)))
    img.alpha_composite(shade)

    p1 = ease_out_back((t - 0.2) / 0.5)
    rounded_card(img, W / 2, 1380, 900 * p1, 150 * p1, 40, PINK_DARK)
    draw_text(img, "Learn Hangul!", W / 2, 1380, 100 * p1, WHITE, FONT_BOLD)

    p2 = ease_out_back((t - 0.7) / 0.5)
    draw_text(img, "Consonant + Vowel", W / 2, 1540, 78 * p2, WHITE,
              stroke=6, stroke_fill=INK)
    p3 = ease_out_back((t - 1.2) / 0.5)
    draw_text(img, "자음 + 모음 = 글자", W / 2, 1650, 74 * p3, (255, 230, 120),
              stroke=6, stroke_fill=INK)
    p4 = ease_out_back((t - 1.7) / 0.4)
    rounded_card(img, W / 2, 1790, 380 * p4, 90 * p4, 45, WHITE, shadow=False)
    draw_text(img, "in 15 seconds", W / 2, 1790, 52 * p4, PINK_DARK)
    return img


def scene_lesson(t, idx):
    c, v, syl, rc, rv, rom = LESSONS[idx]
    img = BG.copy()

    # 상단 제목
    draw_text(img, "Korean Alphabet  한글", W / 2, 110, 64, WHITE, FONT_BOLD,
              stroke=6, stroke_fill=PINK_DARK)

    # 얼굴 (박자에 맞춰 통통)
    beat_phase = (t % BEAT) / BEAT
    bounce = 1 + 0.05 * math.exp(-beat_phase * 6)
    d = int(FACE_D * bounce)
    face = FACE.resize((d, d), Image.BILINEAR)
    ring = Image.new("RGBA", (d + 24, d + 24), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse([0, 0, d + 23, d + 23], fill=WHITE)
    fx, fy = W // 2, 430
    img.alpha_composite(ring, (fx - (d + 24) // 2, fy - (d + 24) // 2))
    img.alpha_composite(face, (fx - d // 2, fy - d // 2))

    # 말풍선
    bp = ease_out_back(t / 0.35)
    rounded_card(img, 830, 250, 300 * bp, 100 * bp, 50, WHITE, PINK_DARK, 5)
    draw_text(img, f"{idx + 1} / {len(LESSONS)}", 830, 250, 54 * bp, PINK_DARK)

    # 자음 + 모음 (타일)
    row_y = 900
    tile = 250
    pc = ease_out_back(t / 0.4)
    rounded_card(img, 230, row_y, tile * pc, tile * pc, 40, WHITE, BLUE, 8)
    draw_text(img, c, 230, row_y - 10, 170 * pc, BLUE, FONT_BOLD)
    draw_text(img, f"[{rc}]", 230, row_y + 175, 56 * pc, BLUE, alpha=clamp(pc))

    pp = ease_out_back((t - 0.35) / 0.3)
    draw_text(img, "+", W / 2, row_y, 140 * pp, WHITE, FONT_BOLD, 6, PINK_DARK)

    pv = ease_out_back((t - 0.5) / 0.4)
    rounded_card(img, 850, row_y, tile * pv, tile * pv, 40, WHITE, ORANGE, 8)
    draw_text(img, v, 850, row_y - 10, 170 * pv, ORANGE, FONT_BOLD)
    draw_text(img, f"[{rv}]", 850, row_y + 175, 56 * pv, ORANGE, alpha=clamp(pv))

    # 아래로 합쳐지는 화살표
    pa = ease_out_cubic((t - 0.9) / 0.25)
    if pa > 0:
        ad = ImageDraw.Draw(img)
        y0, y1 = 1120, 1120 + 90 * pa
        ad.line([(W / 2, y0), (W / 2, y1)], fill=WHITE, width=14)
        if pa > 0.9:
            ad.polygon([(W / 2 - 34, y1 - 10), (W / 2 + 34, y1 - 10),
                        (W / 2, y1 + 30)], fill=WHITE)

    # 합쳐진 글자
    ps = ease_out_back((t - 1.0) / 0.4)
    card = 360 * ps
    rounded_card(img, W / 2, 1450, card, card, 60, WHITE, PURPLE, 10)
    # 글자 안 자음/모음 색 나누기 대신, 전체 보라색 + 반짝임
    draw_text(img, syl, W / 2, 1440, 260 * ps, PURPLE, FONT_BOLD)

    pr = ease_out_back((t - 1.25) / 0.35)
    rounded_card(img, W / 2, 1745, 460 * pr, 130 * pr, 65, PURPLE, shadow=False)
    draw_text(img, f"{rc} + {rv} = {rom}", W / 2, 1745, 76 * pr, WHITE)

    # 반짝이 효과
    if 1.0 <= t < 1.6:
        sd = ImageDraw.Draw(img)
        k = (t - 1.0) / 0.6
        for i in range(10):
            ang = i * math.pi / 5
            r = 200 + 160 * k
            x = W / 2 + r * math.cos(ang)
            y = 1450 + r * math.sin(ang)
            s = 16 * (1 - k)
            sd.ellipse([x - s, y - s, x + s, y + s], fill=(255, 235, 120))
    return img


def scene_outro(t):
    dur = DUR - OUTRO_START
    img = full_photo(t, 1.08, 1.0, dur)
    grad = Image.new("L", (1, H))
    for y in range(H):
        grad.putpixel((0, y), int(210 * clamp((y - H * 0.5) / (H * 0.5))))
    shade = Image.new("RGBA", (W, H), (60, 10, 40, 255))
    shade.putalpha(grad.resize((W, H)))
    img.alpha_composite(shade)

    p1 = ease_out_back(t / 0.4)
    draw_text(img, "Now you can read:", W / 2, 1230, 72 * p1, WHITE,
              stroke=6, stroke_fill=INK)
    for i, les in enumerate(LESSONS):
        pi = ease_out_back((t - 0.2 - i * 0.12) / 0.35)
        x = 140 + i * 200
        rounded_card(img, x, 1400, 170 * pi, 170 * pi, 34, WHITE, PURPLE, 6)
        draw_text(img, les[2], x, 1392, 120 * pi, PURPLE, FONT_BOLD)
        draw_text(img, les[5], x, 1530, 50 * pi, WHITE, stroke=4, stroke_fill=INK)

    p3 = ease_out_back((t - 0.4) / 0.4)
    draw_text(img, "쉽죠? Easy, right?", W / 2, 1660, 80 * p3, (255, 230, 120),
              FONT_BOLD, 7, INK)
    p4 = ease_out_back((t - 1.2) / 0.4)
    rounded_card(img, W / 2, 1810, 620 * p4, 110 * p4, 55, PINK_DARK, WHITE, 5)
    draw_text(img, "Follow for more!", W / 2, 1810, 64 * p4, WHITE)
    return img


def render_frame(t):
    if t < INTRO_END:
        return scene_intro(t)
    if t < OUTRO_START:
        k = int((t - INTRO_END) // SEG)
        return scene_lesson(t - INTRO_END - k * SEG, k)
    return scene_outro(t - OUTRO_START)


# ---------------------------------------------------------------- music
SR = 44100


def note_freq(n):
    """MIDI 번호 -> Hz"""
    return 440.0 * 2 ** ((n - 69) / 12)


def load_voice(n):
    """녹음 파일을 잡음 제거·음량 정리 후 VOICE_CLIPS 위치에 배치."""
    track = np.zeros(n)
    if not VOICE.exists():
        return track
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    raw = subprocess.run(
        [ff, "-loglevel", "error", "-i", str(VOICE),
         "-af", "highpass=f=90,afftdn=nf=-30,acompressor=threshold=-20dB:ratio=3:"
                "attack=5:release=80,equalizer=f=3000:t=q:w=1:g=3",
         "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
        capture_output=True, check=True).stdout
    v = np.frombuffer(raw, dtype=np.float32).astype(float)
    v /= np.max(np.abs(v)) + 1e-9
    fade = int(0.03 * SR)
    for a, b, dst in VOICE_CLIPS:
        clip = v[int(a * SR):int(b * SR)].copy()
        clip[:fade] *= np.linspace(0, 1, fade)
        clip[-fade:] *= np.linspace(1, 0, fade)
        i = int(dst * SR)
        clip = clip[: max(0, n - i)]
        track[i:i + len(clip)] += clip * 0.95
    return track


def make_music():
    n = int(SR * DUR)
    out = np.zeros(n)

    def add(sig, start):
        i = int(start * SR)
        if i >= n:
            return
        sig = sig[: n - i]
        out[i:i + len(sig)] += sig

    def tone(freq, length, kind="bell", vol=0.3):
        t = np.arange(int(length * SR)) / SR
        if kind == "bell":  # 마림바/벨 느낌
            s = (np.sin(2 * np.pi * freq * t)
                 + 0.35 * np.sin(2 * np.pi * freq * 4 * t) * np.exp(-t * 18))
            env = np.exp(-t * 5.5)
        elif kind == "bass":
            s = np.sign(np.sin(2 * np.pi * freq * t)) * 0.4 + np.sin(2 * np.pi * freq * t)
            env = np.exp(-t * 4)
        else:  # pad
            s = sum(np.sin(2 * np.pi * freq * m * t) / m for m in (1, 2, 3))
            env = np.minimum(1, t * 8) * np.exp(-t * 0.8)
        atk = np.minimum(1, t / 0.005)
        return s * env * atk * vol

    def kick():
        t = np.arange(int(0.25 * SR)) / SR
        f = 120 * np.exp(-t * 25) + 45
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 12) * 0.9

    rng = np.random.default_rng(7)

    def clap():
        t = np.arange(int(0.18 * SR)) / SR
        return rng.uniform(-1, 1, len(t)) * np.exp(-t * 22) * 0.35

    def hat():
        t = np.arange(int(0.05 * SR)) / SR
        s = rng.uniform(-1, 1, len(t))
        s = np.diff(s, prepend=0)  # 고역만 남기기
        return s * np.exp(-t * 80) * 0.12

    def pop(freq=700):
        t = np.arange(int(0.12 * SR)) / SR
        f = freq * (1 + 2.5 * t / 0.12)
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 30) * 0.45

    def sparkle():
        s = np.zeros(int(0.6 * SR))
        for k, m in enumerate((84, 88, 91, 96)):
            tt = tone(note_freq(m), 0.45, "bell", 0.18)
            i = int(k * 0.05 * SR)
            s[i:i + len(tt)] += tt[: len(s) - i]
        return s

    # 코드 진행: C - Am - F - G (마디당 2초)
    chords = [(60, 64, 67), (57, 60, 64), (53, 57, 60), (55, 59, 62)]
    roots = [36, 33, 29, 31]
    # 귀에 쏙 들어오는 5음계 멜로디 (8분음표 8개 = 1마디)
    hook = [
        [72, 76, 79, 76, 81, 79, 76, None],
        [72, 76, 79, 76, 74, 72, 74, None],
        [69, 72, 76, 72, 77, 76, 72, None],
        [71, 74, 79, 74, 76, 74, 71, 74],
    ]

    bars = int(math.ceil(DUR / SEG))
    for b in range(bars):
        t0 = b * SEG
        ci = b % 4
        for m in chords[ci]:
            add(tone(note_freq(m), SEG, "pad", 0.05), t0)
        for e in range(8):  # 8분음표 베이스
            add(tone(note_freq(roots[ci] + (12 if e % 2 else 0)), 0.24, "bass", 0.16),
                t0 + e * BEAT / 2)
        if b >= 1:  # 첫 마디 뒤부터 멜로디
            for e, m in enumerate(hook[ci]):
                if m is not None:
                    add(tone(note_freq(m), 0.4, "bell", 0.22), t0 + e * BEAT / 2)
        for q in range(4):
            tq = t0 + q * BEAT
            if q in (0, 2):
                add(kick(), tq)
            else:
                add(clap(), tq)
            add(hat(), tq + BEAT / 2)

    # 화면 효과음
    add(sparkle(), 0.2)
    for k in range(len(LESSONS)):
        s = INTRO_END + k * SEG
        add(pop(650), s)
        add(pop(900), s + 0.5)
        add(sparkle(), s + 1.0)
    add(sparkle(), OUTRO_START + 0.4)

    # 목소리 트랙 + 목소리가 나올 때 음악 줄이기(더킹)
    out /= np.max(np.abs(out)) + 1e-9
    voice = load_voice(n)
    active = np.convolve((np.abs(voice) > 0.02).astype(float),
                         np.ones(int(0.25 * SR)) / int(0.25 * SR), mode="same")
    duck = 1 - 0.6 * np.clip(active * 4, 0, 1)
    out = out * 0.55 * duck + voice

    # 끝부분 페이드아웃 + 정규화
    fade = int(0.6 * SR)
    out[-fade:] *= np.linspace(1, 0, fade)
    out = np.tanh(out * 1.1)
    out /= np.max(np.abs(out)) + 1e-9
    out *= 0.89
    pcm = (out * 32767).astype(np.int16)
    stereo = np.stack([pcm, pcm], axis=1)
    with wave.open(str(AUDIO), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())


# ---------------------------------------------------------------- main
def main():
    make_music()
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ff, "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-i", str(AUDIO),
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
           str(OUT)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    total = int(DUR * FPS)
    for i in range(total):
        frame = render_frame(i / FPS).convert("RGB")
        proc.stdin.write(frame.tobytes())
        if i % 60 == 0:
            print(f"frame {i}/{total}")
    proc.stdin.close()
    proc.wait()
    print("done:", OUT)


if __name__ == "__main__":
    main()
