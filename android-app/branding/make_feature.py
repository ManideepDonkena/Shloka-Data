"""Generate the Google Play Store Feature Graphic (1024 x 500).

Outputs android-app/branding/out/feature_1024x500.png
"""
import os, subprocess, tempfile
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)

HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
  
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    width: 1024px;
    height: 500px;
    overflow: hidden;
    background: radial-gradient(circle at 75% 45%, #f6a247 0%, #d85c22 45%, #8c2010 85%, #5a1107 100%);
    font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
    color: #fff;
    position: relative;
    user-select: none;
  }
  
  /* Background decorative geometry */
  .circle-bg {
    position: absolute;
    right: 40px;
    top: 50%;
    transform: translateY(-50%);
    width: 440px;
    height: 440px;
    border-radius: 50%;
    border: 2px dashed rgba(255, 235, 195, 0.25);
  }
  .circle-bg-inner {
    position: absolute;
    right: 70px;
    top: 50%;
    transform: translateY(-50%);
    width: 380px;
    height: 380px;
    border-radius: 50%;
    border: 1px solid rgba(255, 235, 195, 0.2);
  }
  
  /* Conch image */
  .conch {
    position: absolute;
    right: 40px;
    top: 50%;
    transform: translateY(-48%);
    width: 410px;
    height: 410px;
    filter: drop-shadow(0 16px 36px rgba(0,0,0,0.45));
  }
  
  /* Left branding column */
  .brand {
    position: absolute;
    left: 72px;
    top: 50%;
    transform: translateY(-50%);
    max-width: 500px;
  }
  
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: rgba(0, 0, 0, 0.24);
    border: 1px solid rgba(255, 220, 160, 0.35);
    padding: 6px 14px;
    border-radius: 30px;
    font-size: 13px;
    font-weight: 600;
    color: #ffdeb0;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    margin-bottom: 16px;
    backdrop-filter: blur(8px);
  }
  
  h1 {
    font-family: 'Cinzel', Georgia, serif;
    font-size: 54px;
    font-weight: 700;
    line-height: 1.08;
    color: #fff9ed;
    text-shadow: 0 4px 14px rgba(0,0,0,0.4);
    letter-spacing: -0.5px;
    margin-bottom: 10px;
  }
  
  .sub {
    font-size: 21px;
    font-weight: 500;
    color: #ffe6c2;
    margin-bottom: 24px;
    letter-spacing: 0.2px;
  }
  
  .pills {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
  }
  
  .pill {
    background: rgba(255, 255, 255, 0.12);
    border: 1px solid rgba(255, 255, 255, 0.2);
    padding: 7px 14px;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 600;
    color: #fff;
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .accent-line {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 4px;
    background: linear-gradient(90deg, #ffcc70 0%, #ff8838 50%, #d83a18 100%);
  }
</style>
</head>
<body>
  <div class="circle-bg"></div>
  <div class="circle-bg-inner"></div>
  <img class="conch" src="fg_1000.png" alt="Pāñcajanya Conch">
  
  <div class="brand">
    <div class="badge"> श्रीमद्भगवद्गीता · Shloka Memorizer</div>
    <h1>Shloka Learn</h1>
    <div class="sub">Learn Bhagavad-gītā by Heart</div>
    <div class="pills">
      <div class="pill">Listen & Repeat</div>
      <div class="pill">Word Meanings</div>
      <div class="pill">Mic Feedback</div>
      <div class="pill">100% Offline</div>
    </div>
  </div>
  <div class="accent-line"></div>
</body>
</html>
"""

def main():
    d = tempfile.mkdtemp()
    fg_src = os.path.join(OUT, "fg_1000.png")
    # Copy fg_1000.png to temp directory
    Image.open(fg_src).save(os.path.join(d, "fg_1000.png"))
    html_path = os.path.join(d, "feature.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(HTML)
    
    shot_path = os.path.join(d, "shot.png")
    out_path = os.path.join(OUT, "feature_1024x500.png")
    
    cmd = [
        "google-chrome",
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--hide-scrollbars",
        "--window-size=1024,500",
        "--virtual-time-budget=4000",
        f"--screenshot={shot_path}",
        f"file://{html_path}"
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    
    im = Image.open(shot_path).convert("RGB")
    im = im.crop((0, 0, 1024, 500))
    im.save(out_path, "PNG", optimize=True)
    print(f"Feature graphic generated: {out_path} ({im.size[0]}x{im.size[1]})")

if __name__ == "__main__":
    main()
