#!/usr/bin/env python3
"""
정반식당 주간 메뉴표 이미지에서 오늘의 메뉴를 OCR로 추출합니다.

사용법:
  python scripts/ocr-menu.py <image_path_or_url> [weekday] [--debug]
  weekday: 0=월, 1=화, 2=수, 3=목, 4=금 (생략 시 오늘 요일 자동 감지)
  --debug: 감지된 텍스트 전체, 컬럼 bbox, 필터링 과정을 stderr로 출력

출력: JSON (stdout)
  성공: {"success": true, "weekday": "월", "special": "특선메뉴", "menu": [...], "is_holiday": false}
  공휴일: {"success": true, "weekday": "월", "special": null, "menu": [], "is_holiday": true}
  실패: {"success": false, "error": "..."}
"""

import sys
import json
import os
import tempfile
import urllib.request
from datetime import datetime

EXCLUDED_ROW_KEYWORDS = [
    "프레시 박스", "헬시밀 박스", "프레시박스", "헬시밀박스",
    "프레시", "프레쉬", "헬시밀",
    "TAKE OUT", "TAKE", "테이크아웃",
]

# 구분 열에서 이 키워드가 나오면 해당 y 이후를 제외 (TAKE OUT / 프레쉬 / 헬시밀 박스 시작점)
EXCLUDED_SECTION_KEYWORDS = ["프레시", "프레쉬", "헬시밀", "TAKE OUT", "TAKE"]
WEEKDAY_NAMES = ["월", "화", "수", "목", "금"]

# 하단 안내문구 시작 키워드 (이후 텍스트 전부 제거)
FOOTER_KEYWORDS = ["문의사항", "* 문의", "* 메뉴", "* 해당", "* 특정", "※", "* 문"]

# 노이즈 텍스트 패턴 (정규식)
NOISE_PATTERNS = [
    r"^[-–—=_*·•<>/]+$",                    # 대시/구분선/기호만 있는 텍스트
    r"^<[^>]+>",                             # HTML 태그
    r"^[^\uAC00-\uD7A3a-zA-Z0-9]+$",        # 한글/영숫자 없는 기호만
    r"^[A-Z0-9\s]{1,10}$",                  # 한글 없는 짧은 대문자/숫자 조합 (브랜드 로고 오인식 방지)
]

# 공휴일 이미지에 자주 등장하는 키워드 (메뉴 텍스트와 구분되는 명확한 키워드만)
HOLIDAY_IMAGE_KEYWORDS = [
    "Happy New Year",
    "새해 복 많이",
    "새해복 많이",
    "명절 연휴",
    "설날 연휴",
    "추석 연휴",
    "행복하세요!",
    "붉은 말의 해",
    "병오년 행복",
]

# 공휴일 판단: 유의미한 메뉴 텍스트 수가 이 미만이면 공휴일로 간주
HOLIDAY_TEXT_THRESHOLD = 3

UPSCALE_WIDTH_THRESHOLD = 1200  # 이 너비 미만이면 저화질로 판단해 2배 업스케일링

# 디버그 출력 여부 (--debug 플래그로 활성화)
_DEBUG = False


def debug(*args, **kwargs):
    """디버그 메시지를 stderr로 출력합니다."""
    if _DEBUG:
        print("[DEBUG]", *args, file=sys.stderr, **kwargs)


def download_image(source: str):
    """URL 또는 로컬 경로에서 이미지를 로드합니다. 저화질(너비 1200px 미만)이면 2배 업스케일링합니다."""
    from PIL import Image

    if source.startswith("http://") or source.startswith("https://"):
        with urllib.request.urlopen(source) as resp:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                f.write(resp.read())
                tmp_path = f.name
        try:
            img = Image.open(tmp_path).convert("RGB")
        finally:
            os.unlink(tmp_path)
    else:
        img = Image.open(source).convert("RGB")

    w, h = img.size
    if w < UPSCALE_WIDTH_THRESHOLD:
        img = img.resize((w * 2, h * 2), Image.LANCZOS)
    return img


def run_ocr(image):
    """Surya로 텍스트 라인 검출 + 인식을 수행합니다."""
    from surya.detection import DetectionPredictor
    from surya.recognition import RecognitionPredictor
    from surya.foundation import FoundationPredictor

    det_predictor = DetectionPredictor()
    foundation = FoundationPredictor()
    rec_predictor = RecognitionPredictor(foundation)

    ocr_results = rec_predictor([image], det_predictor=det_predictor)
    result = ocr_results[0]

    debug(f"OCR 감지 텍스트 라인 ({len(result.text_lines)}개):")
    for i, line in enumerate(result.text_lines):
        debug(f"  [{i:02d}] bbox={[round(v) for v in line.bbox]}  text={line.text!r}")

    return result


def run_table_rec(image):
    """Surya로 표 구조(행/열/셀)를 인식합니다."""
    from surya.table_rec import TableRecPredictor

    predictor = TableRecPredictor()
    results = predictor([image])
    result = results[0]

    if hasattr(result, "cols") and result.cols:
        debug(f"표 컬럼 ({len(result.cols)}개):")
        for i, col in enumerate(sorted(result.cols, key=lambda c: c.bbox[0])):
            debug(f"  col[{i}] bbox={[round(v) for v in col.bbox]}")

    return result


def bbox_center_x(bbox):
    return (bbox[0] + bbox[2]) / 2


def bbox_center_y(bbox):
    return (bbox[1] + bbox[3]) / 2


def overlap_ratio(a, b):
    """두 bbox의 x축 겹침 비율 (a 기준)."""
    ax1, _, ax2, _ = a
    bx1, _, bx2, _ = b
    inter = max(0, min(ax2, bx2) - max(ax1, bx1))
    width_a = ax2 - ax1
    if width_a == 0:
        return 0
    return inter / width_a


def assign_text_to_columns(text_lines, col_bboxes, img_width):
    """각 텍스트 라인을 컬럼에 배정합니다."""
    col_texts = [[] for _ in col_bboxes]

    for line in text_lines:
        text = line.text.strip()
        if not text:
            continue
        lbbox = line.bbox
        best_col = -1
        best_ratio = 0.0
        for ci, cbbox in enumerate(col_bboxes):
            r = overlap_ratio(lbbox, cbbox)
            if r > best_ratio:
                best_ratio = r
                best_col = ci
        if best_col >= 0 and best_ratio > 0.3:
            col_texts[best_col].append((bbox_center_y(lbbox), text))
            debug(f"  배정: col[{best_col}] ratio={best_ratio:.2f}  {text!r}")
        else:
            debug(f"  미배정(ratio={best_ratio:.2f}): {text!r}")

    # y 좌표 기준으로 정렬
    for ci in range(len(col_texts)):
        col_texts[ci].sort(key=lambda x: x[0])

    if _DEBUG:
        for ci, items in enumerate(col_texts):
            debug(f"  col[{ci}] 텍스트 목록: {[t for _, t in items]}")

    return col_texts


def is_excluded_row_start(text: str) -> bool:
    """프레시 박스, 헬시밀 박스 등 제외 시작 키워드 확인."""
    for kw in EXCLUDED_ROW_KEYWORDS:
        if kw in text:
            return True
    return False


def is_footer(text: str) -> bool:
    """하단 안내문구 여부 확인."""
    for kw in FOOTER_KEYWORDS:
        if text.startswith(kw):
            return True
    # '* 문의사항', '* 메뉴' 등 * 로 시작하는 안내문
    if text.startswith("*") and any(kw in text for kw in ["문의", "메뉴", "해당", "특정", "알러지"]):
        return True
    return False


def is_header_noise(text: str) -> bool:
    """날짜, 요일명, 브랜드명, 노이즈 텍스트 여부 확인."""
    import re
    t = text.strip()
    # '02월 09일', '월', '화' 등 날짜/요일 단독 텍스트
    if re.fullmatch(r"\d{2}월\s*\d{2}일", t):
        return True
    if t in ["월", "화", "수", "목", "금", "토", "일", "호"]:
        return True
    # 브랜드명/헤더 노이즈 (부분 포함 여부 확인)
    BRAND_KEYWORDS = [
        "正바를", "주간메뉴표", "[ 중식 ]", "[중식]",
        "Weekly Menu", "고메드갤러리아", "GOURMET", "GALLERIA",
        "정반식당", "PLUS",
    ]
    if any(kw in t for kw in BRAND_KEYWORDS):
        return True
    # "정반" 단독 텍스트 (브랜드명, 메뉴와 혼동 방지를 위해 단독 매칭)
    if re.fullmatch(r"정반", t):
        return True
    if re.match(r"\[?\s*중식\s*\]?\s*\d+:\d+", t):
        return True
    # 숫자만 단독 (1~3자리)
    if re.fullmatch(r"\d{1,3}", t):
        return True
    # 노이즈 패턴
    for pattern in NOISE_PATTERNS:
        if re.search(pattern, t):
            return True
    return False


def find_excluded_y_threshold(text_lines, col_bboxes):
    """
    구분 열(col[0])에서 PLUS / 프레시 / 헬시밀 등 섹션 구분 키워드를 찾아
    해당 행 시작 y 좌표를 반환합니다. 이 y 이상의 텍스트는 모든 열에서 제외합니다.

    OCR이 "프레쉬" + "박스" 처럼 단어를 분리해서 인식하는 경우에도 동작합니다.
    PLUS 행의 y 좌표를 찾아 그 이후(프레시박스, 헬시밀박스)를 모두 제외합니다.
    """
    if not col_bboxes:
        return float("inf")

    label_col_bbox = col_bboxes[0]
    threshold = float("inf")

    for line in text_lines:
        text = line.text.strip()
        if not text:
            continue
        matched = any(kw in text for kw in EXCLUDED_SECTION_KEYWORDS)
        if matched:
            r = overlap_ratio(line.bbox, label_col_bbox)
            if r > 0.2:
                y = line.bbox[1]  # 행 상단 y 좌표
                if y < threshold:
                    threshold = y

    return threshold


def find_special_row_y_range(table_result, image):
    """
    표 행(row)의 배경색을 실제 이미지 픽셀에서 측정하여
    특선 행(붉은/핑크 배경)의 y 범위 (y_start, y_end)를 반환합니다.

    R 채널 평균이 G·B 채널보다 현저히 높은 행(R - avg(G,B) > 30)을 특선 행으로 판단합니다.
    특선 행이 없으면 (None, None)을 반환합니다.
    """
    import numpy as np

    if not hasattr(table_result, "rows") or not table_result.rows:
        return None, None

    arr = np.array(image)
    img_h, img_w = arr.shape[:2]

    special_y_start = None
    special_y_end = None

    for row in table_result.rows:
        y1 = max(0, int(row.bbox[1]))
        y2 = min(img_h, int(row.bbox[3]))
        x1 = max(0, int(row.bbox[0]))
        x2 = min(img_w, int(row.bbox[2]))
        region = arr[y1:y2, x1:x2]
        if region.size == 0:
            continue
        mean = region.mean(axis=(0, 1))
        r, g, b = mean[0], mean[1], mean[2]
        redness = r - (g + b) / 2
        debug(f"  row_id={row.row_id} y=[{y1},{y2}] RGB=({r:.0f},{g:.0f},{b:.0f}) redness={redness:.1f}")
        if redness > 30:
            if special_y_start is None or y1 < special_y_start:
                special_y_start = y1
            if special_y_end is None or y2 > special_y_end:
                special_y_end = y2

    return special_y_start, special_y_end


def extract_menu_for_weekday(text_lines, col_bboxes, table_result, weekday_idx: int, img_width: int, image=None):
    """
    지정된 요일(컬럼 인덱스)의 메뉴 텍스트를 추출합니다.

    표 구조: 0번 컬럼 = '구분' 레이블, 1~5번 컬럼 = 월~금
    weekday_idx: 0=월, 1=화, 2=수, 3=목, 4=금

    반환값: (special: str | None, menu_texts: list[str], is_holiday: bool)
      special: 특선 메뉴 한 줄 문자열 - 배경색이 붉은 행의 텍스트를 공백으로 합침 (없으면 None)
    """
    # 구분 열에서 제외 행 y 기준 먼저 계산
    excluded_y = find_excluded_y_threshold(text_lines, col_bboxes)

    # 특선 행 y 범위: 이미지 배경색 기반
    special_y_start, special_y_end = None, None
    if image is not None:
        debug("--- 특선 행 배경색 탐지 ---")
        special_y_start, special_y_end = find_special_row_y_range(table_result, image)
        debug(f"  특선 행 y 범위: [{special_y_start}, {special_y_end}]")

    col_texts = assign_text_to_columns(text_lines, col_bboxes, img_width)

    # 컬럼 수가 6개 미만이면 구분 컬럼 없이 1~5 직접 매핑
    target_col_idx = weekday_idx + 1 if len(col_bboxes) >= 6 else weekday_idx

    if target_col_idx >= len(col_texts):
        return None, [], False

    # y 기준 이하 텍스트 사전 제거 (y, text) 형태 유지
    raw_items = [(y, t) for y, t in col_texts[target_col_idx] if y < excluded_y]
    debug(f"[col {target_col_idx}] excluded_y={round(excluded_y)}, raw_items ({len(raw_items)}개): {[t for _, t in raw_items]}")

    # 노이즈·푸터·중복 필터링 (y 좌표 유지)
    special_items = []
    menu_items = []
    seen = set()
    for y, text in raw_items:
        if is_footer(text):
            debug(f"  FOOTER 중단: {text!r}")
            break
        if is_excluded_row_start(text):
            debug(f"  EXCLUDED_ROW 중단: {text!r}")
            break
        if is_header_noise(text):
            debug(f"  NOISE 제거: {text!r}")
            continue
        if text in seen:
            debug(f"  중복 제거: {text!r}")
            continue
        seen.add(text)
        # 배경색 기반 특선 행 분류
        if special_y_start is not None and special_y_end is not None and special_y_start <= y <= special_y_end:
            special_items.append(text)
            debug(f"  [특선] 포함: {text!r}")
        else:
            menu_items.append(text)
            debug(f"  [메뉴] 포함: {text!r}")

    special = " ".join(special_items) if special_items else None
    debug(f"  special={special!r}, menu_texts={menu_items}")

    # 공휴일 감지: 유의미한 메뉴 텍스트 수가 임계값 미만
    is_holiday = (len(special_items) + len(menu_items)) < HOLIDAY_TEXT_THRESHOLD

    return special, menu_items, is_holiday


def sort_col_bboxes(table_result):
    """TableRecPredictor 결과에서 컬럼 bbox를 x 순서로 정렬하여 반환합니다."""
    if not hasattr(table_result, "cols") or not table_result.cols:
        return []
    cols = sorted(table_result.cols, key=lambda c: c.bbox[0])
    return [c.bbox for c in cols]


def main():
    global _DEBUG

    args = sys.argv[1:]

    # --debug 플래그 파싱
    if "--debug" in args:
        _DEBUG = True
        args = [a for a in args if a != "--debug"]

    if not args:
        print(json.dumps({"success": False, "error": "이미지 경로 또는 URL을 인자로 전달하세요."}))
        sys.exit(1)

    source = args[0]

    # 요일 결정 (CLI 인자 > FORCE_WEEKDAY 환경변수 > 오늘 날짜 순)
    if len(args) >= 2:
        try:
            weekday_idx = int(args[1])
        except ValueError:
            weekday_idx = datetime.today().weekday()
    elif os.environ.get("FORCE_WEEKDAY") is not None:
        try:
            weekday_idx = int(os.environ["FORCE_WEEKDAY"])
        except ValueError:
            weekday_idx = datetime.today().weekday()
    else:
        weekday_idx = datetime.today().weekday()

    # 평일(0~4)이 아니면 운영 안 함
    if weekday_idx > 4:
        print(json.dumps({
            "success": True,
            "weekday": WEEKDAY_NAMES[0],
            "menu": [],
            "is_holiday": True,
            "reason": "주말에는 식당을 운영하지 않습니다."
        }))
        return

    weekday_name = WEEKDAY_NAMES[weekday_idx]
    debug(f"대상 요일: {weekday_name} (idx={weekday_idx}), 이미지 소스: {source}")

    try:
        image = download_image(source)
        debug(f"이미지 로드 완료: {image.size[0]}x{image.size[1]}")
    except Exception as e:
        print(json.dumps({"success": False, "error": f"이미지 로드 실패: {e}"}))
        sys.exit(1)

    try:
        table_result = run_table_rec(image)
        col_bboxes = sort_col_bboxes(table_result)
        debug(f"컬럼 bbox 목록 ({len(col_bboxes)}개): {[[round(v) for v in b] for b in col_bboxes]}")
    except Exception as e:
        print(json.dumps({"success": False, "error": f"표 인식 실패: {e}"}))
        sys.exit(1)

    try:
        ocr_result = run_ocr(image)
        text_lines = ocr_result.text_lines
    except Exception as e:
        print(json.dumps({"success": False, "error": f"OCR 실패: {e}"}))
        sys.exit(1)

    debug("--- 텍스트 컬럼 배정 시작 ---")
    special, menu_texts, is_holiday = extract_menu_for_weekday(
        text_lines, col_bboxes, table_result, weekday_idx, image.width, image
    )

    # 공휴일 이미지 키워드 감지 (추가 체크)
    if not is_holiday:
        combined = " ".join([special or ""] + menu_texts)
        for kw in HOLIDAY_IMAGE_KEYWORDS:
            if kw in combined:
                is_holiday = True
                special = None
                menu_texts = []
                break

    if is_holiday:
        print(json.dumps({
            "success": True,
            "weekday": weekday_name,
            "special": None,
            "menu": [],
            "is_holiday": True,
            "reason": f"공휴일로 인해 식당을 운영하지 않습니다."
        }, ensure_ascii=False))
    else:
        print(json.dumps({
            "success": True,
            "weekday": weekday_name,
            "special": special,
            "menu": menu_texts,
            "is_holiday": False
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
