from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path
import os
import re

from PIL import Image, ImageDraw, ImageFont, JpegImagePlugin  # noqa: F401


ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"


def load_local_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def resolve_secret(name: str, env_values: dict[str, str]) -> str | None:
    return os.environ.get(name) or env_values.get(name)


def ensure_hebrew(text: str) -> None:
    if "?" in text:
        raise ValueError("Hebrew source contains question marks.")
    if not re.search(r"[\u0590-\u05FF]", text):
        raise ValueError("Hebrew source does not contain Hebrew letters.")


def report_payload(report_date: date) -> tuple[dict[str, str | list[str]], dict[str, str | list[str]], list[str]]:
    english: dict[str, str | list[str]] = {
        "title": "Israel Youth Team Weekly BuzzerBeater Report",
        "dek": "Pool boss energy, playoff smoke, and one loud reminder that Israel's youth team is still very much in the mix.",
        "latest_heading": "Latest Verified Result",
        "latest_body": (
            "Israel's most recently verified completed result remains the 126-64 blowout over Hayastan on "
            "June 1, 2026. That is the result that replaced the older Cymru/Wales snapshot from earlier public "
            "standings pages, and it still stands as the latest fully verified match this run."
        ),
        "leaders_heading": "Boxscore Spotlight",
        "leaders_body": (
            "Using the last verified authenticated boxscore pull available in this workspace, Israel's leaders in that "
            "win were G. Avidar with 34 points, M. Azrieli with 13 rebounds, and N. Wolf with 13 assists. "
            "That boxscore was not re-fetchable from the current restricted environment, so these names are carried "
            "forward from the last verified pull rather than newly scraped today."
        ),
        "standings_heading": "Where Israel Stands",
        "standings_body": (
            "The freshest public standings snapshot available this run still shows Israel on top of Europe U21 Championship "
            "Pool B at 3-0 with a +90 point differential, alongside Rossiya and Polska at 3-0. A newer public competition "
            "overview, however, already lists Israel among the four World Cup playoff survivors together with Lietuva, USA, "
            "and Italia. That strongly suggests Israel finished the remaining qualifying work successfully and is now in the "
            "title-stage conversation."
        ),
        "scenario_heading": "Advancement Math, Minus the Spreadsheet Headache",
        "scenario_body": (
            "The practical read is simple: Israel is no longer fighting just to escape the group. The available public trail "
            "points to advancement already achieved. From here, every next result is about ceiling, not survival: win the "
            "playoff opener and the team moves into the championship game; lose it and the path likely shifts to a bronze-medal fight."
        ),
        "next_heading": "Next Games Watch",
        "next_body": (
            "The exact live bracket order was not exposed by the public indexed pages available in this run, but the most recent "
            "competition overview places Israel in a final four with Lietuva, USA, and Italia. Those are heavyweight opponents, "
            "so the next swing game is the kind that can rewrite the whole season's mood in one afternoon."
        ),
        "style_heading": "Social Feed Version",
        "style_body": (
            "Translation for the timeline: Israel didn't just win a pool game, it built momentum, kept the rankings heat, and "
            "apparently turned a qualification race into a playoff launch. If the next step is really the world-stage semifinal, "
            "the vibes are no longer 'maybe.' They're 'bring the cameras.'"
        ),
        "caveat_heading": "Source Note",
        "caveat_items": [
            "Current shell/network restrictions prevented a fresh BBAPI login during this run.",
            "Season 72 and the 3-0 Pool B snapshot came from public BuzzerBeater standings pages.",
            "The four-team playoff state came from a newer public BuzzerBeater international overview page.",
            "Latest-match boxscore leaders came from the last verified authenticated workspace pull because the live boxscore could not be re-fetched here.",
        ],
    }

    hebrew: dict[str, str | list[str]] = {
        "title": "דו\"ח שבועי: נבחרת הנוער של ישראל בבאזרביטר",
        "dek": "קצת כתבת ספורט, קצת פוסט לרשת, והרבה תחושה שהחבורה בכחול-לבן עדיין עמוק בתמונה.",
        "latest_heading": "התוצאה האחרונה שאומתה",
        "latest_body": (
            "התוצאה האחרונה שאומתה באופן מלא עבור נבחרת הנוער של ישראל היא הניצחון 126:64 על ארמניה "
            "מ-1 ביוני 2026. זו התוצאה שהחליפה את תמונת ה-110:66 הישנה מול וויילס, והיא עדיין התוצאה "
            "המאומתת האחרונה שהצלחתי לבסס בריצה הזו."
        ),
        "leaders_heading": "פינת המצטיינים מהבוקס סקור",
        "leaders_body": (
            "לפי שליפת הבוקס סקור המאומתת האחרונה שנשמרה בסביבת העבודה, ג׳ אבידר הוביל עם 34 נקודות, "
            "מ׳ עזריאלי לקח 13 ריבאונדים, ונ׳ וולף חילק 13 אסיסטים. בריצה הנוכחית לא הייתה גישה חיה לאותו "
            "עמוד, ולכן הנתונים האלה נשענים על האימות האחרון ולא על שליפה חדשה מהאתר."
        ),
        "standings_heading": "איפה ישראל עומדת עכשיו",
        "standings_body": (
            "תמונת הדירוג הציבורית הטרייה ביותר שהייתה זמינה כאן עדיין מציגה את ישראל במקום הראשון בבית ב׳ "
            "באליפות אירופה לנבחרות נוער עם מאזן 0:3 ופלוס 90, יחד עם רוסיה ופולין שגם הן על 0:3. אבל עמוד "
            "ציבורי חדש יותר של התחרויות הבינלאומיות כבר מציב את ישראל בין ארבע האחרונות בפלייאוף גביע העולם "
            "יחד עם ליטא, ארצות הברית ואיטליה. במילים פשוטות: נראה שהעלייה כבר הושגה, ועכשיו מדברים על תקרה גבוהה יותר."
        ),
        "scenario_heading": "מה המשמעות להמשך",
        "scenario_body": (
            "הקרב כבר לא נראה כמו מאבק הישרדות בבית. לפי שרשרת המקורות הציבוריים שעמדה לרשותי, ישראל כבר "
            "עברה את שלב ההעפלה. מכאן כל משחק הבא משנה לא את השאלה אם עולים, אלא לאן אפשר להגיע: ניצחון במשחק "
            "הפלייאוף הבא ישלח את הנבחרת לקרב על התואר, והפסד כנראה יוריד אותה למשחק על הארד."
        ),
        "next_heading": "מבט קדימה",
        "next_body": (
            "סדר המשחקים המדויק בברקט לא נחשף במקורות הציבוריים שהיו זמינים בריצה הזו, אבל תמונת המצב האחרונה "
            "שמה את ישראל באותה רביעייה עם ליטא, ארצות הברית ואיטליה. כלומר, מכאן אין משחקי חימום; כל יריבה היא "
            "כוח על, וכל תוצאה יכולה לשנות את כל הטון של העונה."
        ),
        "style_heading": "גרסת הפוסט לרשת",
        "style_body": (
            "אם לתמצת את זה לפיד: נבחרת הנוער של ישראל לא רק ניצחה, היא צברה מומנטום, שמרה על האש בדירוגים, "
            "וכנראה הפכה מרדיפה אחרי עלייה לכניסה אמיתית למאבק על העולם. בקיצור: פחות 'נראה מה יהיה', יותר "
            "'תדליקו מצלמות'."
        ),
        "caveat_heading": "הערת מקורות",
        "caveat_items": [
            "מגבלות הרשת בסביבת ההרצה מנעו התחברות חיה ל-BBAPI בריצה הזו.",
            "עונה 72 ותמונת המאזן 0:3 בבית ב׳ נשענות על עמודי דירוג ציבוריים של BuzzerBeater.",
            "מצב ארבע האחרונות בפלייאוף נשען על עמוד ציבורי חדש יותר של התחרויות הבינלאומיות.",
            "נתוני המצטיינים מהבוקס סקור נשענים על שליפת אימות קודמת ששמורה בסביבת העבודה, כי לא הייתה גישה חיה לעמוד עצמו בריצה הזו.",
        ],
    }

    source_chips = [
        "Verified latest match used in report: Israel 126-64 Hayastan",
        "Public standings snapshot: Europe U21 Championship Season 72 Pool B",
        "Newer public overview snapshot: World Cup playoffs include Israel, Lietuva, USA, Italia",
        f"Report date: {report_date.isoformat()}",
    ]
    return english, hebrew, source_chips


def build_html(report_date: date) -> str:
    english, hebrew, source_chips = report_payload(report_date)

    english_items = "".join(f"<li>{escape(item)}</li>" for item in english["caveat_items"])  # type: ignore[index]
    hebrew_items = "".join(f"<li>{escape(item)}</li>" for item in hebrew["caveat_items"])  # type: ignore[index]
    chips = "".join(f"<span class='chip'>{escape(item)}</span>" for item in source_chips)

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(english["title"])}</title>
  <style>
    :root {{
      --bg: #f5efe5;
      --paper: #fffdfa;
      --ink: #1d1d1d;
      --muted: #5f564b;
      --line: #d9c9ae;
      --blue: #1d4ed8;
      --navy: #0f2247;
      --gold: #c58f22;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at top right, rgba(29,78,216,0.12), transparent 30%),
        radial-gradient(circle at top left, rgba(197,143,34,0.15), transparent 28%),
        linear-gradient(180deg, #f8f4ec 0%, var(--bg) 100%);
      color: var(--ink);
      font-family: Arial, Helvetica, sans-serif;
    }}
    .page {{
      max-width: 980px;
      margin: 0 auto;
      padding: 34px 30px 40px;
    }}
    .hero {{
      background: linear-gradient(135deg, rgba(15,34,71,0.96), rgba(29,78,216,0.88));
      color: #fff;
      border-radius: 24px;
      padding: 28px 30px;
      box-shadow: 0 20px 50px rgba(15,34,71,0.18);
    }}
    .eyebrow {{
      font-size: 12px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      opacity: 0.82;
    }}
    h1 {{
      margin: 10px 0 8px;
      font-size: 34px;
      line-height: 1.08;
    }}
    .dek {{
      margin: 0;
      max-width: 760px;
      font-size: 17px;
      line-height: 1.5;
    }}
    .chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    .chip {{
      border: 1px solid rgba(255,255,255,0.22);
      border-radius: 999px;
      padding: 8px 12px;
      font-size: 12px;
      background: rgba(255,255,255,0.09);
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 22px;
      margin-top: 24px;
    }}
    .card {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 22px 22px 18px;
      box-shadow: 0 10px 24px rgba(20, 25, 38, 0.05);
    }}
    h2 {{
      margin: 0 0 14px;
      color: var(--navy);
      font-size: 24px;
    }}
    h3 {{
      margin: 18px 0 8px;
      color: var(--navy);
      font-size: 17px;
    }}
    p, li {{
      font-size: 14px;
      line-height: 1.65;
    }}
    ul {{
      margin: 8px 0 0 18px;
      padding: 0;
    }}
    .hebrew {{
      direction: rtl;
      text-align: right;
    }}
    .section-tag {{
      display: inline-block;
      margin-bottom: 8px;
      color: var(--gold);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}
    .footer-note {{
      margin-top: 18px;
      padding-top: 14px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
    }}
    @page {{
      size: A4;
      margin: 14mm;
    }}
    @media print {{
      body {{
        background: #fff;
      }}
      .page {{
        padding: 0;
      }}
      .hero {{
        box-shadow: none;
      }}
      .card {{
        box-shadow: none;
        break-inside: avoid;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <div class="eyebrow">Weekly Report · Israel Youth Team · BuzzerBeater</div>
      <h1>{escape(english["title"])}</h1>
      <p class="dek">{escape(english["dek"])}</p>
      <div class="chips">{chips}</div>
    </section>
    <div class="grid">
      <section class="card">
        <div class="section-tag">English</div>
        <h2>{escape(english["title"])}</h2>
        <p>{escape(english["dek"])}</p>
        <h3>{escape(english["latest_heading"])}</h3>
        <p>{escape(english["latest_body"])}</p>
        <h3>{escape(english["leaders_heading"])}</h3>
        <p>{escape(english["leaders_body"])}</p>
        <h3>{escape(english["standings_heading"])}</h3>
        <p>{escape(english["standings_body"])}</p>
        <h3>{escape(english["scenario_heading"])}</h3>
        <p>{escape(english["scenario_body"])}</p>
        <h3>{escape(english["next_heading"])}</h3>
        <p>{escape(english["next_body"])}</p>
        <h3>{escape(english["style_heading"])}</h3>
        <p>{escape(english["style_body"])}</p>
        <h3>{escape(english["caveat_heading"])}</h3>
        <ul>{english_items}</ul>
      </section>
      <section class="card hebrew">
        <div class="section-tag">עברית</div>
        <h2>{escape(hebrew["title"])}</h2>
        <p>{escape(hebrew["dek"])}</p>
        <h3>{escape(hebrew["latest_heading"])}</h3>
        <p>{escape(hebrew["latest_body"])}</p>
        <h3>{escape(hebrew["leaders_heading"])}</h3>
        <p>{escape(hebrew["leaders_body"])}</p>
        <h3>{escape(hebrew["standings_heading"])}</h3>
        <p>{escape(hebrew["standings_body"])}</p>
        <h3>{escape(hebrew["scenario_heading"])}</h3>
        <p>{escape(hebrew["scenario_body"])}</p>
        <h3>{escape(hebrew["next_heading"])}</h3>
        <p>{escape(hebrew["next_body"])}</p>
        <h3>{escape(hebrew["style_heading"])}</h3>
        <p>{escape(hebrew["style_body"])}</p>
        <h3>{escape(hebrew["caveat_heading"])}</h3>
        <ul>{hebrew_items}</ul>
      </section>
    </div>
    <div class="footer-note">
      Generated locally for {report_date.isoformat()}. This report avoids exposing credentials and uses only non-secret source notes in its text.
    </div>
  </div>
</body>
</html>
"""
    ensure_hebrew(str(hebrew["title"]) + "\n" + str(hebrew["dek"]) + "\n" + str(hebrew["latest_body"]))
    return html


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def measure_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    return right - left


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            attempt = f"{current} {word}"
            if measure_text(draw, attempt, font) <= width:
                current = attempt
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def rtl_visual(line: str) -> str:
    reversed_line = line[::-1]
    return re.sub(
        r"[A-Za-z0-9:/\-\+\.\(\),]+",
        lambda match: match.group(0)[::-1],
        reversed_line,
    )


def draw_paragraph(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    width: int,
    font: ImageFont.ImageFont,
    fill: str,
    *,
    rtl: bool = False,
    line_gap: int = 10,
) -> int:
    lines = wrap_text(draw, text, font, width)
    _, _, _, line_height = draw.textbbox((0, 0), "Ag", font=font)
    for line in lines:
        visual = rtl_visual(line) if rtl else line
        text_width = measure_text(draw, visual, font)
        line_x = x + width - text_width if rtl else x
        draw.text((line_x, y), visual, font=font, fill=fill)
        y += line_height + line_gap
    return y


def render_pdf(report_date: date, pdf_path: Path) -> None:
    english, hebrew, chips = report_payload(report_date)
    page_size = (1240, 1754)
    background = "#fffdfa"
    navy = "#0f2247"
    blue = "#1d4ed8"
    gold = "#c58f22"
    ink = "#1d1d1d"
    muted = "#5f564b"
    margin = 90
    content_width = page_size[0] - margin * 2
    title_font = load_font(44, bold=True)
    section_font = load_font(24, bold=True)
    body_font = load_font(24)
    small_font = load_font(18)

    def new_page() -> tuple[Image.Image, ImageDraw.ImageDraw]:
        image = Image.new("RGB", page_size, background)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((margin, 55, page_size[0] - margin, 255), radius=34, fill=navy)
        return image, draw

    pages: list[Image.Image] = []

    english_page, draw = new_page()
    draw.text((margin + 32, 88), str(english["title"]), font=title_font, fill="white")
    draw.text((margin + 32, 154), str(english["dek"]), font=body_font, fill="white")
    chip_y = 214
    chip_x = margin + 32
    for chip in chips:
        chip_width = measure_text(draw, chip, small_font) + 28
        draw.rounded_rectangle((chip_x, chip_y, chip_x + chip_width, chip_y + 34), radius=17, outline="#d9c9ae", width=1)
        draw.text((chip_x + 14, chip_y + 7), chip, font=small_font, fill="white")
        chip_x += chip_width + 10
    y = 320
    english_sections = [
        (str(english["latest_heading"]), str(english["latest_body"])),
        (str(english["leaders_heading"]), str(english["leaders_body"])),
        (str(english["standings_heading"]), str(english["standings_body"])),
        (str(english["scenario_heading"]), str(english["scenario_body"])),
        (str(english["next_heading"]), str(english["next_body"])),
        (str(english["style_heading"]), str(english["style_body"])),
    ]
    for heading, body in english_sections:
        draw.text((margin, y), heading, font=section_font, fill=blue)
        y += 44
        y = draw_paragraph(draw, body, margin, y, content_width, body_font, ink)
        y += 18
    draw.text((margin, y), str(english["caveat_heading"]), font=section_font, fill=gold)
    y += 44
    for item in english["caveat_items"]:  # type: ignore[index]
        y = draw_paragraph(draw, f"- {item}", margin, y, content_width, body_font, muted)
        y += 4
    pages.append(english_page)

    hebrew_page, draw = new_page()
    hebrew_title = rtl_visual(str(hebrew["title"]))
    hebrew_dek = rtl_visual(str(hebrew["dek"]))
    title_width = measure_text(draw, hebrew_title, title_font)
    draw.text((page_size[0] - margin - 32 - title_width, 88), hebrew_title, font=title_font, fill="white")
    dek_width = measure_text(draw, hebrew_dek, body_font)
    draw.text((page_size[0] - margin - 32 - dek_width, 154), hebrew_dek, font=body_font, fill="white")
    y = 320
    hebrew_sections = [
        (str(hebrew["latest_heading"]), str(hebrew["latest_body"])),
        (str(hebrew["leaders_heading"]), str(hebrew["leaders_body"])),
        (str(hebrew["standings_heading"]), str(hebrew["standings_body"])),
        (str(hebrew["scenario_heading"]), str(hebrew["scenario_body"])),
        (str(hebrew["next_heading"]), str(hebrew["next_body"])),
        (str(hebrew["style_heading"]), str(hebrew["style_body"])),
    ]
    for heading, body in hebrew_sections:
        visual_heading = rtl_visual(heading)
        heading_width = measure_text(draw, visual_heading, section_font)
        draw.text((page_size[0] - margin - heading_width, y), visual_heading, font=section_font, fill=blue)
        y += 44
        y = draw_paragraph(draw, body, margin, y, content_width, body_font, ink, rtl=True)
        y += 18
    visual_caveat = rtl_visual(str(hebrew["caveat_heading"]))
    caveat_width = measure_text(draw, visual_caveat, section_font)
    draw.text((page_size[0] - margin - caveat_width, y), visual_caveat, font=section_font, fill=gold)
    y += 44
    for item in hebrew["caveat_items"]:  # type: ignore[index]
        y = draw_paragraph(draw, f"- {item}", margin, y, content_width, body_font, muted, rtl=True)
        y += 4
    pages.append(hebrew_page)

    rgb_pages = [page.convert("RGB") for page in pages]
    rgb_pages[0].save(pdf_path, save_all=True, append_images=rgb_pages[1:], resolution=150.0)


def main() -> None:
    report_date = date.today()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    env_values = load_local_env(ROOT / ".env")
    _ = resolve_secret("BBAPI_USERNAME", env_values)
    _ = resolve_secret("BBAPI_SECURITY_CODE", env_values)
    _ = resolve_secret("BB_SITE_PASSWORD", env_values)

    html_path = REPORTS_DIR / f"israel-youth-weekly-{report_date.isoformat()}.html"
    pdf_path = REPORTS_DIR / f"israel-youth-weekly-{report_date.isoformat()}.pdf"
    html_path.write_text(build_html(report_date), encoding="utf-8")
    render_pdf(report_date, pdf_path)
    print(html_path)
    print(pdf_path)


if __name__ == "__main__":
    main()
